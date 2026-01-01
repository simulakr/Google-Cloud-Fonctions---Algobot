
from typing import Dict, Optional, Any
from pybit.unified_trading import HTTP
from exit_strategies import ExitStrategy
import logging
from config import LEVERAGE, RISK_PER_TRADE_USDT, ROUND_NUMBERS, DEFAULT_LEVERAGE, SYMBOL_SETTINGS
import time

logger = logging.getLogger(__name__)

class PositionManager:
    def __init__(self, client: HTTP):
        self.client = client
        self.exit_strategy = ExitStrategy(client)
        self.active_positions: Dict[str, Dict] = {}  # {symbol: position_data}
        self.logger = logging.getLogger(__name__)

    def open_position(self, symbol: str, direction: str, entry_price: float, atr_value: float, pct_atr: float) -> Optional[Dict]:
        """
        Yeni pozisyon açar ve limit TP/SL emirlerini yerleştirir (OCO mantığıyla)
        """
        try:
            # Eğer zaten pozisyon varsa kontrol et
            if symbol in self.active_positions:
                existing_direction = self.active_positions[symbol]['direction']
                
                # Aynı yönde sinyal (Senaryo 2a)
                if existing_direction == direction:
                    logger.info(f"{symbol} zaten {direction} pozisyonda - TP/SL güncelleniyor")
                    return self._update_tp_sl_only(symbol, direction, entry_price, atr_value, pct_atr)
                
                # Ters yönde sinyal (Senaryo 2b)
                else:
                    logger.info(f"{symbol} ters sinyal alındı ({existing_direction} → {direction}) - Pozisyon tersine dönüyor")
                    self.close_position(symbol, "REVERSE_SIGNAL")
                    # Devam et ve yeni pozisyon aç
            
            # Pozisyon büyüklüğünü hesapla
            quantity = self._calculate_position_size(symbol, atr_value, entry_price)
            logger.info(f"{symbol} {direction} pozisyon hesaplandı | Miktar: {quantity}")
            
            # Market emri ile pozisyon aç
            order = self.client.place_order(
                category="linear",
                symbol=symbol,
                side="Buy" if direction == "LONG" else "Sell",
                orderType="Market",
                qty=quantity,
                reduceOnly=False
            )
    
            if order['retCode'] != 0:
                raise Exception(f"Pozisyon açma hatası: {order['retMsg']}")
    
            logger.info(f"{symbol} {direction} pozisyon açıldı | Miktar: {quantity} | Entry: {entry_price}")

            # ⭐ POZİSYON DOĞRULAMA ⭐
            # ============================================
            time.sleep(1)  # ← YENİ: 1 saniye bekle (Bybit'in execute etmesi için)
            
            if not self._verify_position_opened(symbol, direction, float(quantity)):
                logger.warning(f"{symbol} pozisyon doğrulanamadı, TP/SL ayarlanamayacak")
                return None
            # ============================================
            
            # TP/SL seviyelerini hesapla
            tp_price, sl_price = self.exit_strategy.calculate_levels(entry_price, atr_value, direction, symbol)
            logger.info(f"{symbol} TP/SL hesaplandı | TP: {tp_price} | SL: {sl_price}")
            
            # Limit TP/SL emirlerini gönder (YENİ)
            tp_sl_result = self.exit_strategy.set_limit_tp_sl(
                symbol=symbol,
                direction=direction,
                tp_price=tp_price,
                sl_price=sl_price,
                quantity=quantity
            )
    
            if tp_sl_result.get('success'):
                logger.info(f"{symbol} Limit TP/SL başarıyla ayarlandı")
                
                # Pozisyon bilgilerini kaydet (OCO pair dahil)
                position = {
                    'symbol': symbol,
                    'direction': direction,
                    'entry_price': entry_price,
                    'quantity': quantity,
                    'take_profit': tp_price,
                    'stop_loss': sl_price,
                    'current_pct_atr': pct_atr,
                    'order_id': order['result']['orderId'],
                    'oco_pair': tp_sl_result['oco_pair']  # YENİ: OCO tracking
                }
                self.active_positions[symbol] = position
                return position
            else:
                logger.warning(f"{symbol} TP/SL ayarlanamadı - Pozisyon kapatılıyor")
                self.close_position(symbol, "TP_SL_FAILED")
                return None
    
        except Exception as e:
            logger.error(f"{symbol} pozisyon açma hatası: {str(e)}")
            return None
    
    
    def _update_tp_sl_only(self, symbol: str, direction: str, entry_price: float, atr_value: float, pct_atr: float) -> Optional[Dict]:
        """
        Mevcut pozisyonun sadece TP/SL'sini günceller (Senaryo 2a)
        """
        try:
            position = self.active_positions[symbol]
            
            # Eski TP/SL emirlerini iptal et
            if 'oco_pair' in position:
                logger.info(f"{symbol} eski TP/SL emirleri iptal ediliyor...")
                self.exit_strategy.cancel_order(symbol, position['oco_pair']['tp_order_id'])
                self.exit_strategy.cancel_order(symbol, position['oco_pair']['sl_order_id'])
            
            # Yeni TP/SL seviyelerini hesapla
            tp_price, sl_price = self.exit_strategy.calculate_levels(entry_price, atr_value, direction, symbol)
            logger.info(f"{symbol} Yeni TP/SL hesaplandı | TP: {tp_price} | SL: {sl_price}")
            
            # Yeni limit TP/SL emirlerini gönder
            tp_sl_result = self.exit_strategy.set_limit_tp_sl(
                symbol=symbol,
                direction=direction,
                tp_price=tp_price,
                sl_price=sl_price,
                quantity=position['quantity']
            )
            
            if tp_sl_result.get('success'):
                # Pozisyon bilgilerini güncelle
                position['take_profit'] = tp_price
                position['stop_loss'] = sl_price
                position['current_pct_atr'] = pct_atr
                position['oco_pair'] = tp_sl_result['oco_pair']
                
                logger.info(f"{symbol} TP/SL başarıyla güncellendi")
                return position
            else:
                logger.error(f"{symbol} TP/SL güncellenemedi")
                return None
                
        except Exception as e:
            logger.error(f"{symbol} TP/SL güncelleme hatası: {str(e)}")
            return None
    
    
    def close_position(self, symbol: str, reason: str = "MANUAL") -> bool:
        """
        Pozisyonu kapatır ve TP/SL emirlerini iptal eder
        """
        try:
            if symbol not in self.active_positions:
                logger.warning(f"{symbol} kapatılacak pozisyon bulunamadı")
                return False
            
            position = self.active_positions[symbol]
            
            # TP/SL emirlerini iptal et
            if 'oco_pair' in position:
                logger.info(f"{symbol} TP/SL emirleri iptal ediliyor...")
                try:
                    self.exit_strategy.cancel_order(symbol, position['oco_pair']['tp_order_id'])
                    self.exit_strategy.cancel_order(symbol, position['oco_pair']['sl_order_id'])
                except Exception as e:
                    logger.warning(f"{symbol} TP/SL iptal hatası (zaten tetiklenmiş olabilir): {e}")
            
            # Pozisyonu market ile kapat
            close_side = "Sell" if position['direction'] == "LONG" else "Buy"
            
            order = self.client.place_order(
                category="linear",
                symbol=symbol,
                side=close_side,
                orderType="Market",
                qty=position['quantity'],
                reduceOnly=True
            )
            
            if order['retCode'] == 0:
                logger.info(f"{symbol} pozisyon kapatıldı | Sebep: {reason}")
                del self.active_positions[symbol]
                return True
            else:
                logger.error(f"{symbol} pozisyon kapatma hatası: {order['retMsg']}")
                return False
                
        except Exception as e:
            logger.error(f"{symbol} pozisyon kapatma hatası: {str(e)}")
            return False

    def _verify_position_opened(self, symbol: str, direction: str, expected_qty: float) -> bool:
        """
        Pozisyonun gerçekten açıldığını doğrular (timing sorunu önleme)
        Maksimum 5 saniye boyunca 0.5 saniye aralıklarla kontrol eder
        """
        try:
            expected_side = 'Buy' if direction == 'LONG' else 'Sell'
            
            # Maksimum 10 deneme (10 x 0.5 saniye = 5 saniye)
            for attempt in range(10):
                positions = self.client.get_positions(
                    category='linear',
                    symbol=symbol
                )
                
                if positions['retCode'] == 0:
                    for pos in positions['result']['list']:
                        pos_size = float(pos.get('size', 0))
                        pos_side = pos.get('side', '')
                        
                        # Pozisyon var mı ve doğru yönde mi?
                        if pos_size > 0 and pos_side == expected_side:
                            # Miktar uyuşuyor mu? (%5 tolerans)
                            if abs(pos_size - expected_qty) < expected_qty * 0.05:
                                logger.info(f"{symbol} pozisyon doğrulandı (deneme {attempt + 1}/10)")
                                return True
                
                # 0.5 saniye bekle ve tekrar dene
                time.sleep(0.5)
            
            # 5 saniye sonunda hala bulunamadı
            logger.error(f"{symbol} pozisyon 5 saniye içinde doğrulanamadı")
            return False
            
        except Exception as e:
            logger.error(f"{symbol} pozisyon doğrulama hatası: {e}")
            return False
            
    def _calculate_position_size(self, symbol: str, atr_value: float ,entry_price: float, sl_multiplier=3) -> str:
        """
        Sembol bazlı risk ve kaldıraç ayarlarına göre pozisyon büyüklüğü hesaplar
        """
        # Sembol ayarlarını al, yoksa default değerleri kullan
        symbol_config = SYMBOL_SETTINGS.get(symbol, {})
        risk_amount = symbol_config.get('risk', RISK_PER_TRADE_USDT)  # Fallback için
        leverage = symbol_config.get('leverage', DEFAULT_LEVERAGE)
        
        # Pozisyon büyüklüğünü hesapla
        raw_quantity = risk_amount / (sl_multiplier * atr_value)
        
        # Sembole göre yuvarlama hassasiyeti
        quantity = round(raw_quantity, ROUND_NUMBERS[symbol])
        
        self.logger.info(
            f"{symbol} pozisyon hesaplandı | "
            f"Risk: ${risk_amount} | Leverage: {leverage}x | "
            f"Entry: ${entry_price:.2f} | Quantity: {quantity}"
        )
        
        return str(quantity)
        
    def manage_positions(self, signals: Dict[str, Optional[str]], all_data: Dict[str, Optional[Dict]]) -> None:
        """
        Tüm aktif pozisyonları yönetir
        - OCO kontrolü yapar (TP/SL tetiklenmesi)
        - Ters sinyal gelirse pozisyonu kapatır
        - Aynı yönde sinyal gelirse TP/SL günceller
        """
        # 1. OCO kontrolü - TP/SL tetiklenmeleri (Senaryo 3)
        self.monitor_oco_orders()
        
        # 2. Sinyal bazlı kontroller
        for symbol, position in list(self.active_positions.items()):
            current_signal = signals.get(symbol)
            current_data = all_data.get(symbol)
            current_direction = position['direction']
            
            # Ters sinyal geldi mi? (Senaryo 2b)
            if current_signal and current_signal != current_direction:
                logger.info(f"{symbol} ters sinyal alındı ({current_direction} → {current_signal})")
                # open_position içinde zaten hallediliyor, buradan sadece kapatıyoruz
                # Yeni pozisyon open_position'da açılacak
                continue  # open_position çağrılacak main loop'ta
            
            # Aynı yönde sinyal + yeni data var mı? (Senaryo 2a - TP/SL güncelleme)
            if current_signal and current_data and current_signal == current_direction:
                logger.info(f"{symbol} aynı yönde sinyal - TP/SL güncelleniyor")
                
                # Yeni TP/SL hesapla
                new_tp, new_sl = self.exit_strategy.calculate_levels(
                    current_data['close'],
                    current_data['atr'],
                    current_direction,
                    symbol
                )
                
                # Eski TP/SL'yi iptal et
                if 'oco_pair' in position:
                    self.exit_strategy.cancel_order(symbol, position['oco_pair']['tp_order_id'])
                    self.exit_strategy.cancel_order(symbol, position['oco_pair']['sl_order_id'])
                
                # Yeni TP/SL koy
                tp_sl_result = self.exit_strategy.set_limit_tp_sl(
                    symbol=symbol,
                    direction=current_direction,
                    tp_price=new_tp,
                    sl_price=new_sl,
                    quantity=position['quantity']
                )
                
                if tp_sl_result.get('success'):
                    # Pozisyonu güncelle
                    position['entry_price'] = current_data['close']
                    position['take_profit'] = new_tp
                    position['stop_loss'] = new_sl
                    position['oco_pair'] = tp_sl_result['oco_pair']
                    logger.info(f"{symbol} TP/SL güncellendi | TP: {new_tp} | SL: {new_sl}")


    def get_active_position(self, symbol: str) -> Optional[Dict]:
        return self.active_positions.get(symbol)

    def has_active_position(self, symbol: str) -> bool:
        return symbol in self.active_positions

    def monitor_oco_orders(self):
        """
        Tüm aktif pozisyonların OCO emirlerini kontrol eder
        """
        print(f"[DEBUG] monitor_oco_orders çalışıyor - Pozisyon sayısı: {len(self.active_positions)}")  # ← EKLE
        
        for symbol, position in list(self.active_positions.items()):
            print(f"[DEBUG] {symbol} kontrol ediliyor...")  # ← EKLE
            
            if 'oco_pair' not in position:
                print(f"[DEBUG] {symbol} - oco_pair yok, atlandı")  # ← EKLE
                continue
                
            oco_pair = position['oco_pair']
            
            if not oco_pair.get('active'):
                print(f"[DEBUG] {symbol} - oco_pair aktif değil, atlandı")  # ← EKLE
                continue
            
            print(f"[DEBUG] {symbol} - check_and_cancel_oco çağrılıyor...")  # ← EKLE
            result = self.exit_strategy.check_and_cancel_oco(oco_pair)
            print(f"[DEBUG] {symbol} - Sonuç: {result}")  # ← EKLE
            
            if result.get('triggered'):
                logger.info(f"{symbol} {result['triggered']} tetiklendi - Pozisyon otomatik kapatıldı")
                del self.active_positions[symbol]
