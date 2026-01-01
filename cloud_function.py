import functions_framework
import logging
import time
from typing import Dict, Optional
from config import SYMBOLS, INTERVAL
from exchange import BybitFuturesAPI
from indicators import calculate_indicators
from entry_strategies import check_long_entry, check_short_entry
from position_manager import PositionManager

# Cloud Logging için yapılandırma (dosyaya yazmaz, Cloud Console'a gider)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self, testnet: bool = False):
        self.api = BybitFuturesAPI(testnet=testnet)
        self.position_manager = PositionManager(self.api.session)
        self.symbols = SYMBOLS
        self.interval = INTERVAL
        self._initialize_account()
        self._load_existing_positions()

    def _initialize_account(self):
        """ByBit için hesap ayarlarını yapılandır"""
        from config import LEVERAGE
        for symbol in self.symbols:
            try:
                self.api.session.set_leverage(
                    category="linear",
                    symbol=symbol,
                    buyLeverage=str(LEVERAGE),
                    sellLeverage=str(LEVERAGE)
                )
                logger.info(f"{symbol} kaldıraç ayarlandı: {LEVERAGE}x")
            except Exception as e:
                if "leverage not modified" in str(e):
                    logger.debug(f"{symbol} kaldıraç zaten {LEVERAGE}x olarak ayarlı")
                else:
                    logger.warning(f"{symbol} kaldıraç ayarlama uyarısı: {str(e)}")

    def _load_existing_positions(self):
        """Bybit'teki mevcut pozisyonları bot hafızasına yükle"""
        try:
            positions = self.api.session.get_positions(category='linear', settleCoin='USDT')
            if positions['retCode'] == 0:
                for pos in positions['result']['list']:
                    if float(pos.get('size', 0)) > 0:
                        symbol = pos['symbol']
                        direction = 'LONG' if pos['side'] == 'Buy' else 'SHORT'
                        quantity = float(pos['size'])
                        
                        oco_pair = self._find_tp_sl_orders(symbol, direction, quantity)
                        
                        position_data = {
                            'symbol': symbol,
                            'direction': direction,
                            'entry_price': float(pos['avgPrice']),
                            'quantity': quantity,
                            'take_profit': float(pos['takeProfit']) if pos['takeProfit'] else None,
                            'stop_loss': float(pos['stopLoss']) if pos['stopLoss'] else None,
                            'order_id': None
                        }
                        
                        if oco_pair:
                            position_data['oco_pair'] = oco_pair
                            logger.info(f"{symbol} pozisyon + TP/SL emirleri yüklendi: {direction}")
                        else:
                            logger.warning(f"{symbol} pozisyon yüklendi ama TP/SL emirleri bulunamadı")
                        
                        self.position_manager.active_positions[symbol] = position_data
                        
        except Exception as e:
            logger.error(f"Mevcut pozisyonlar yüklenirken hata: {e}")
    
    def _find_tp_sl_orders(self, symbol: str, direction: str, quantity: float) -> Optional[Dict]:
        """Belirli bir pozisyon için açık TP/SL emirlerini bulur"""
        try:
            orders = self.api.session.get_open_orders(category='linear', symbol=symbol)
            
            if orders['retCode'] != 0:
                return None
            
            tp_order_id = None
            sl_order_id = None
            expected_side = "Sell" if direction == "LONG" else "Buy"
            
            for order in orders['result']['list']:
                if order['side'] != expected_side:
                    continue
                
                order_qty = float(order['qty'])
                if abs(order_qty - quantity) > quantity * 0.01:
                    continue
                
                if order['orderType'] == 'Limit' and order.get('reduceOnly'):
                    tp_order_id = order['orderId']
                elif order['orderType'] == 'Market' and order.get('triggerPrice'):
                    sl_order_id = order['orderId']
            
            if tp_order_id and sl_order_id:
                return {
                    'symbol': symbol,
                    'tp_order_id': tp_order_id,
                    'sl_order_id': sl_order_id,
                    'active': True
                }
            else:
                logger.warning(f"{symbol} TP/SL emirleri eksik - TP: {tp_order_id}, SL: {sl_order_id}")
                return None
                
        except Exception as e:
            logger.error(f"{symbol} TP/SL emirleri aranırken hata: {e}")
            return None

    def _get_market_data_batch(self) -> Dict[str, Optional[Dict]]:
        """Tüm sembollerin verilerini tek seferde al"""
        all_data = self.api.get_multiple_ohlcv(self.symbols, self.interval)
        results = {}
        
        for symbol, df in all_data.items():
            if df is not None and not df.empty:
                try:
                    df = calculate_indicators(df, symbol)
                    results[symbol] = df.iloc[-1].to_dict()
                except Exception as e:
                    logger.error(f"{symbol} indicator hatası: {str(e)}")
                    results[symbol] = None
            else:
                results[symbol] = None
        return results

    def _generate_signals(self, all_data: Dict[str, Optional[Dict]]) -> Dict[str, Optional[str]]:
        """Toplu veriden sinyal oluştur"""
        signals = {}
        for symbol, data in all_data.items():
            if not data:
                signals[symbol] = None
                continue

            if check_long_entry(data, symbol):
                signals[symbol] = 'LONG'
            elif check_short_entry(data, symbol):
                signals[symbol] = 'SHORT'
            else:
                signals[symbol] = None
        return signals

    def _execute_trades(self, signals: Dict[str, Optional[str]], all_data: Dict[str, Optional[Dict]]):
        """Sinyallere göre işlem aç"""
        for symbol, signal in signals.items():
            if not signal or not all_data.get(symbol):
                continue
    
            data = all_data[symbol]
            
            self.position_manager.open_position(
                symbol=symbol,
                direction=signal,
                entry_price=data['close'],
                atr_value=data['atr'],
                pct_atr=data['pct_atr']
            )
    
    def run_once(self):
        """Tek seferlik çalıştırma (Cloud Functions için)"""
        try:
            start_time = time.time()
            
            # Toplu veri çekme ve işleme
            all_data = self._get_market_data_batch()
            signals = self._generate_signals(all_data)
            
            # 1. Pozisyon yönetimi
            self.position_manager.manage_positions(signals, all_data)
            
            # 2. Yeni pozisyonlar veya güncellemeler
            self._execute_trades(signals, all_data)
            
            elapsed = time.time() - start_time
            logger.info(f"✅ İşlem turu tamamlandı | Süre: {elapsed:.2f}s")
            
            return {
                'success': True,
                'elapsed_time': elapsed,
                'symbols_processed': len(self.symbols),
                'signals': {k: v for k, v in signals.items() if v}
            }
            
        except Exception as e:
            logger.error(f"❌ Hata: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }


# Cloud Functions entry point
@functions_framework.http
def trading_bot_trigger(request):
    """
    Cloud Functions için HTTP trigger
    Cloud Scheduler tarafından her 15 dakikada bir çağrılır
    """
    try:
        logger.info("🚀 Trading bot başlatıldı (Cloud Functions)")
        
        # Bot instance oluştur
        bot = TradingBot(testnet=False)
        
        # Tek sefer çalıştır
        result = bot.run_once()
        
        # Sonucu döndür
        if result['success']:
            return {
                'status': 'success',
                'message': 'Trading bot başarıyla çalıştı',
                'data': result
            }, 200
        else:
            return {
                'status': 'error',
                'message': result.get('error', 'Bilinmeyen hata'),
            }, 500
            
    except Exception as e:
        logger.error(f"❌ Critical error: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'message': str(e)
        }, 500
