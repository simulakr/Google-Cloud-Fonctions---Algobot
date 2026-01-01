import os
import pandas as pd
from pybit.unified_trading import HTTP  # Değişti
from dotenv import load_dotenv
from typing import List, Optional, Dict
import logging

# Log ayarı
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

class BybitFuturesAPI:  # Sınıf adı değişti
    def __init__(self, testnet: bool = False):
        """Bybit Futures API bağlantısını başlatır."""
        self.session = HTTP(  # client -> session
            api_key=os.getenv('BYBIT_API_KEY'),  # BINANCE -> BYBIT
            api_secret=os.getenv('BYBIT_API_SECRET'),
            testnet=testnet
        )
        logger.info("Bybit Futures API bağlantısı başarılı (Testnet: %s)", testnet)

    def get_ohlcv(
        self,
        symbol: str = 'SOLUSDT',
        interval: str = '15',  # Bybit formatı (15m için '15')
        limit: int = 300,  # Bybit max limit 300
        convert_to_float: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        Bybit Futures'tan OHLCV verisi çeker.
        """
        try:
            response = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval=interval,
                limit=limit
            )

            if response['retCode'] != 0:
                raise Exception(response['retMsg'])

            klines = response['result']['list']
            
            df = pd.DataFrame(klines, columns=[
                'time', 'open', 'high', 'low', 'close', 'volume', 'turnover'
            ])

            df = df[['time', 'open', 'high', 'low', 'close', 'volume']].copy()
            df['time'] = pd.to_datetime(df['time'].astype(int), unit='ms')
            
            if convert_to_float:
                df[['open', 'high', 'low', 'close', 'volume']] = df[
                    ['open', 'high', 'low', 'close', 'volume']
                ].astype(float)

            df.set_index('time', inplace=True)
            return df.iloc[::-1]  # Bybit verileri ters gelir

        except Exception as e:
            logger.error("Veri çekme hatası (Sembol: %s): %s", symbol, str(e))
            return None

    def get_multiple_ohlcv(
        self,
        symbols: List[str],
        interval: str = '15',
        limit: int = 250
    ) -> Dict[str, pd.DataFrame]:
        """Birden fazla sembol için veri çeker"""
        return {sym: self.get_ohlcv(sym, interval, limit) for sym in symbols}
