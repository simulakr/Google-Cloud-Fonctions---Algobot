import os
from dotenv import load_dotenv

load_dotenv()  # .env dosyasındaki API anahtarlarını yükle

# ByBit API Ayarları
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")

# Sembol ve Zaman Aralığı Ayarları
SYMBOLS = ['BTCUSDT', 'ETHUSDT', "SOLUSDT",'XRPUSDT','DOGEUSDT']  # "SUIUSDT"
INTERVAL = "15"  # (15m-'15', 1h-'60')

# Percent ATR Ranges
atr_ranges = {'SOLUSDT':  (0.36, 1.03),
              'BTCUSDT': (0.14, 0.57),
               'ETHUSDT':  (0.28, 0.87),
              'DOGEUSDT':  (0.4, 1.17),
              'XRPUSDT':  (0.3, 1.25), 
              }

# Z: atr.quantile(0.25 - 0.75)
Z_RANGES = {
    'BTCUSDT': (0.188, 0.369),
    'ETHUSDT': (0.356, 0.620),
    'SOLUSDT': (0.446, 0.733),
    'DOGEUSDT': (0.495, 0.833),
    'XRPUSDT': (0.391, 0.763),
}

Z_INDICATOR_PARAMS = {
    'atr_period': 14,
    'atr_multiplier': 1  # minimum z
}

# Quantity for Position Size
ROUND_NUMBERS = {
    'BTCUSDT': 3,
    'ETHUSDT': 2,
    'BNBUSDT': 2,
    'SOLUSDT': 1,
    '1000PEPEUSDT': -2,
    'ARBUSDT': 1,
    'SUIUSDT': -1,
    'DOGEUSDT': 0,
    'XRPUSDT': 0,
    'OPUSDT': 1,
}

TP_ROUND_NUMBERS = {
    'BTCUSDT': 2,
    'ETHUSDT': 2,
    'BNBUSDT': 2,
    'SOLUSDT': 3,
    '1000PEPEUSDT': 7,
    'ARBUSDT': 4,
    'SUIUSDT': 5,
    'DOGEUSDT': 5,
    'XRPUSDT': 4,
    'OPUSDT': 4,
}

# Risk Yönetimi
RISK_PER_TRADE_USDT = 40.0  # Per 20 USDT risk
LEVERAGE = 25  # (max 25x)
DEFAULT_LEVERAGE = 25

SYMBOL_SETTINGS = {
    'BTCUSDT': {'risk': 20.0, 'leverage': 25},
    'ETHUSDT': {'risk': 20.0, 'leverage': 25},
    'SOLUSDT': {'risk': 20.0, 'leverage': 25},
    'XRPUSDT': {'risk': 20.0, 'leverage': 25},
    'DOGEUSDT': {'risk': 20.0, 'leverage': 25}, # '1000PEPEUSDT': {'risk': 40.0, 'leverage': 20}
}

# Trading Mode
POSITION_MODE = "Hedge"  # default : OneWay (Hedge mode long/short)
