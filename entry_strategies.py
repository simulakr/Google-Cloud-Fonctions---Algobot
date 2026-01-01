from typing import Dict, Any, Tuple

LONG_PAIRS_2X = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT','XRPUSDT','DOGEUSDT']
SHORT_PAIRS_2X = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT','XRPUSDT','DOGEUSDT']

def check_long_entry(row: Dict[str, Any], symbol: str) -> bool:
    if symbol in LONG_PAIRS_2X:
        return row['pivot_go_breakout_2x'] == True
    return False

def check_short_entry(row: Dict[str, Any], symbol: str) -> bool:
    atr_steps_col = 'pivot_go_breakdown_2x' if symbol in SHORT_PAIRS_2X else 'pivot_go_down_3x'
    return row[atr_steps_col] == True
