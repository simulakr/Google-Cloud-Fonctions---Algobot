import numpy as np
import pandas as pd
from config import atr_ranges,Z_INDICATOR_PARAMS, Z_RANGES
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)

# --- RSI ---
def calculate_rsi(price_data, window=14, price_col='close'):
    delta = price_data[price_col].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# --- ATR ---
def calculate_atr(price_data, window=14):
    high = price_data['high']
    low = price_data['low']
    close = price_data['close']
    previous_close = close.shift(1)
    tr1 = high - low
    tr2 = abs(high - previous_close)
    tr3 = abs(low - previous_close)
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1/window, adjust=False).mean()
    return atr

# --- Donchian Channel ---
def calculate_donchian_channel(price_data, window=20):
    upper_band = price_data['high'].rolling(window=window).max()
    lower_band = price_data['low'].rolling(window=window).min()
    middle_band = (upper_band + lower_band) / 2
    return pd.DataFrame({'dc_upper': upper_band, 'dc_lower': lower_band, 'dc_middle': middle_band})

# --- SMA ---
def calculate_sma(price_data, window=50, price_col='close'):    
    sma = price_data[price_col].rolling(window=window).mean()
    return sma

# --- SMA Trend ---
def determine_sma_trend(price_data, short_window=50, long_window=200, price_col='close'):
    short_sma = price_data[price_col].rolling(window=short_window).mean()
    long_sma = price_data[price_col].rolling(window=long_window).mean()
    trend = np.where(short_sma > long_sma, 'uptrend', 'downtrend')
    return pd.Series(trend, index=price_data.index)

# --- Nadaraya-Watson Envelope ---
def calculate_nadaraya_watson_envelope_optimized(df, bandwidth=8.0, multiplier=3.0, source_col='close', window_size=50):
    n_bars = len(df)
    source_data = df[source_col].values
    def gauss(x, h): return np.exp(-(x**2) / (h * h * 2))
    weights = np.array([gauss(i, bandwidth) for i in range(window_size)])
    weights_sum = np.sum(weights)
    nw_out_arr = np.full(n_bars, np.nan)
    nw_lower_arr = np.full(n_bars, np.nan)
    nw_upper_arr = np.full(n_bars, np.nan)

    for i in range(n_bars):
        if i < window_size - 1:
            continue
        weighted_sum = np.dot(source_data[i - window_size + 1 : i + 1], weights[::-1])
        current_nw_out = weighted_sum / weights_sum
        nw_out_arr[i] = current_nw_out
        abs_diffs = np.abs(source_data[i - window_size + 1 : i + 1] - nw_out_arr[i - window_size + 1 : i + 1])
        current_mae = np.mean(abs_diffs) * multiplier
        nw_lower_arr[i] = current_nw_out - current_mae
        nw_upper_arr[i] = current_nw_out + current_mae

    return pd.DataFrame({'nw': nw_out_arr, 'nw_upper': nw_upper_arr, 'nw_lower': nw_lower_arr}, index=df.index)

def atr_zigzag_two_columns(df, atr_col="atr", close_col="close", atr_mult=1, suffix=""): 
    closes = df[close_col].values
    atrs = df[atr_col].values

    high_pivot = [None] * len(df)
    low_pivot = [None] * len(df)
    high_pivot_atr = [None] * len(df)
    low_pivot_atr = [None] * len(df)
    high_pivot_confirmed = [0] * len(df)
    low_pivot_confirmed = [0] * len(df)
    pivot_bars_ago = [None] * len(df)

    last_pivot = closes[0]
    last_atr = atrs[0]
    last_pivot_idx = 0
    direction = None

    for i in range(1, len(df)):
        price = closes[i]
        atr = atrs[i] * atr_mult

        if direction is None:
            if price >= last_pivot + atr:
                direction = "up"
                last_pivot = closes[last_pivot_idx]
                high_pivot[last_pivot_idx] = last_pivot
                high_pivot_atr[last_pivot_idx] = atrs[last_pivot_idx]
            elif price <= last_pivot - atr:
                direction = "down"
                last_pivot = closes[last_pivot_idx]
                low_pivot[last_pivot_idx] = last_pivot
                low_pivot_atr[last_pivot_idx] = atrs[last_pivot_idx]

        elif direction == "up":
            if price <= (last_pivot - atr):
                high_pivot[last_pivot_idx] = last_pivot
                high_pivot_atr[last_pivot_idx] = atrs[last_pivot_idx]
                high_pivot_confirmed[i] = 1
                pivot_bars_ago[i] = i - last_pivot_idx

                direction = "down"
                last_pivot = price
                last_pivot_idx = i
            elif price > last_pivot:
                last_pivot = price
                last_pivot_idx = i

        elif direction == "down":
            if price >= (last_pivot + atr):
                low_pivot[last_pivot_idx] = last_pivot
                low_pivot_atr[last_pivot_idx] = atrs[last_pivot_idx]
                low_pivot_confirmed[i] = 1
                pivot_bars_ago[i] = i - last_pivot_idx

                direction = "up"
                last_pivot = price
                last_pivot_idx = i
            elif price < last_pivot:
                last_pivot = price
                last_pivot_idx = i

    # Sütun isimlerine suffix ekle
    df[f"high_pivot{suffix}"] = high_pivot
    df[f"low_pivot{suffix}"] = low_pivot
    df[f"high_pivot_atr{suffix}"] = high_pivot_atr
    df[f"low_pivot_atr{suffix}"] = low_pivot_atr
    df[f"high_pivot_confirmed{suffix}"] = high_pivot_confirmed
    df[f"low_pivot_confirmed{suffix}"] = low_pivot_confirmed
    df[f"pivot_bars_ago{suffix}"] = pivot_bars_ago

    # Forward fill işlemleri - suffix eklenmiş isimlerle
    df[f"high_pivot_filled{suffix}"] = df[f"high_pivot{suffix}"].ffill()
    df[f"low_pivot_filled{suffix}"] = df[f"low_pivot{suffix}"].ffill()
    df[f"high_pivot_atr_filled{suffix}"] = df[f"high_pivot_atr{suffix}"].ffill()
    df[f"low_pivot_atr_filled{suffix}"] = df[f"low_pivot_atr{suffix}"].ffill()

    # High pivot confirmed - suffix ile
    high_temp = df[f"high_pivot_confirmed{suffix}"].replace(0, np.nan)
    high_temp = high_temp.ffill()
    df[f"high_pivot_confirmed_filled{suffix}"] = high_temp.fillna(0).astype(int)
    
    # Low pivot confirmed - suffix ile
    low_temp = df[f"low_pivot_confirmed{suffix}"].replace(0, np.nan)
    low_temp = low_temp.ffill()
    df[f"low_pivot_confirmed_filled{suffix}"] = low_temp.fillna(0).astype(int)

    # Pivot bars ago filled
    pivot_bars_filled = []
    last_valid_value = None
    last_valid_index = None

    for i, value in enumerate(pivot_bars_ago):
        if value is not None:
            last_valid_value = value
            last_valid_index = i
            pivot_bars_filled.append(value)
        elif last_valid_value is not None:
            new_value = last_valid_value + (i - last_valid_index)
            pivot_bars_filled.append(new_value)
        else:
            pivot_bars_filled.append(None)

    df[f"pivot_bars_ago_filled{suffix}"] = pivot_bars_filled

    return df

def calculate_z(df, symbol):
    
    if symbol not in Z_RANGES:
        raise ValueError(f"Z_RANGES'de {symbol} için değer tanımlanmamış!")
  
    pct_min, pct_max = Z_RANGES[symbol]  
    atr_mult = Z_INDICATOR_PARAMS['atr_multiplier']

    z = np.minimum(
        np.maximum(
            df['close'] * pct_min / 100,
            atr_mult * df['atr']
        ),
        df['close'] * pct_max / 100
    )
    
    return z

# --- Calculations ---
def calculate_indicators(df, symbol):
    df['rsi'] = calculate_rsi(df)
    df['atr'] = calculate_atr(df)
    df['pct_atr'] = (df['atr'] / df['close']) * 100
    
    df['z'] = calculate_z(df, symbol=symbol)
    df['pct_z'] = (df['z'] / df['close']) * 100
    
    for w in [20, 50]:
        dc = calculate_donchian_channel(df, window=w)
        df[f'dc_upper_{w}'] = dc['dc_upper']
        df[f'dc_lower_{w}'] = dc['dc_lower']
        df[f'dc_middle_{w}'] = dc['dc_middle']
        df[f'dc_position_ratio_{w}'] = (df['close'] - df[f'dc_lower_{w}']) / (df[f'dc_upper_{w}'] - df[f'dc_lower_{w}']) * 100
        df[f'dc_breakout_{w}'] = df['high'] > df[f'dc_upper_{w}']
        df[f'dc_breakdown_{w}'] = df['low'] < df[f'dc_lower_{w}']
    
    df['sma_50'] = calculate_sma(df,window=50)
    df['sma_200'] = calculate_sma(df,window=200)
    
    df['trend_50_200'] = determine_sma_trend(df, short_window=50, long_window=200)

    nw = calculate_nadaraya_watson_envelope_optimized(df)
    df[['nw', 'nw_upper', 'nw_lower']] = nw
    
    df = atr_zigzag_two_columns(df, atr_col="z", close_col="close", atr_mult=2, suffix='_2x')
    df = atr_zigzag_two_columns(df, atr_col="z", close_col="close", atr_mult=3, suffix='_3x')

    df.loc[df['high_pivot_filled_2x'] < df['high_pivot_filled_2x'].shift(1), 'high_structure_2x'] = 'LH'
    df.loc[df['high_pivot_filled_2x'] > df['high_pivot_filled_2x'].shift(1), 'high_structure_2x'] = 'HH'
    df.loc[df['low_pivot_filled_2x'] < df['low_pivot_filled_2x'].shift(1), 'low_structure_2x'] = 'LL'
    df.loc[df['low_pivot_filled_2x'] > df['low_pivot_filled_2x'].shift(1), 'low_structure_2x'] = 'HL'
    
    df['high_structure_2x'] = df['high_structure_2x'].ffill().fillna('HH')
    df['low_structure_2x'] = df['low_structure_2x'].ffill().fillna('LL')
    
    df.loc[df['high_pivot_filled_3x'] < df['high_pivot_filled_3x'].shift(1), 'high_structure_3x'] = 'LH'
    df.loc[df['high_pivot_filled_3x'] > df['high_pivot_filled_3x'].shift(1), 'high_structure_3x'] = 'HH'
    df.loc[df['low_pivot_filled_3x'] < df['low_pivot_filled_3x'].shift(1), 'low_structure_3x'] = 'LL'
    df.loc[df['low_pivot_filled_3x'] > df['low_pivot_filled_3x'].shift(1), 'low_structure_3x'] = 'HL'
    
    df['high_structure_3x'] = df['high_structure_3x'].ffill().fillna('HH')
    df['low_structure_3x'] = df['low_structure_3x'].ffill().fillna('LL')
    
    df['pivot_go_up_2x'] = False
    df['pivot_go_down_2x'] = False
    df.loc[(df['low_pivot_confirmed_2x']) & (df['low_structure_2x']=='HL') & (df['high_structure_2x']=='HH') & (df['trend_50_200']== 'uptrend') & (df['close'] < df['nw_upper']) & (atr_ranges[symbol][0] < df['pct_atr']) & (df['pct_atr'] < atr_ranges[symbol][1]), 'pivot_go_up_2x'] = True
    df.loc[(df['high_pivot_confirmed_2x']) & (df['high_structure_2x']=='LH') & (df['low_structure_2x']=='LL') & (df['trend_50_200']== 'downtrend') & (df['close'] > df['nw_lower']) & (atr_ranges[symbol][0] < df['pct_atr']) & (df['pct_atr'] < atr_ranges[symbol][1]), 'pivot_go_down_2x'] = True
    
    df['pivot_go_up_3x'] = False
    df['pivot_go_down_3x'] = False
    df.loc[(df['low_pivot_confirmed_3x']) & (df['low_structure_3x']=='HL') & (df['high_structure_3x']=='HH') &  (df['close'] < df['nw_upper']) & (atr_ranges[symbol][0] < df['pct_atr']) & (df['pct_atr'] < atr_ranges[symbol][1]), 'pivot_go_up_3x'] = True
    df.loc[(df['high_pivot_confirmed_3x']) & (df['high_structure_3x']=='LH') & (df['low_structure_3x']=='LL') & (df['close'] > df['nw_lower']) & (atr_ranges[symbol][0] < df['pct_atr']) & (df['pct_atr'] < atr_ranges[symbol][1]), 'pivot_go_down_3x'] = True

    df['pivot_go_breakout_2x'] = False
    df['pivot_go_breakdown_2x'] = False
    df['pivot_go_breakout_3x'] = False
    df['pivot_go_breakdown_3x'] = False
    df.loc[(df['low_pivot_confirmed_2x']) & (df['low_structure_2x']=='HL') & (df['high_structure_2x']!='HH') & (df['close'] > df['high_pivot_filled_2x'] ), 'pivot_go_breakout_2x'] = True
    df.loc[(df['high_pivot_confirmed_2x']) & (df['high_structure_2x']=='LH') & (df['low_structure_2x']!='LL') & (df['close'] < df['low_pivot_filled_2x']), 'pivot_go_breakdown_2x'] = True
    df.loc[(df['low_pivot_confirmed_3x']) & (df['low_structure_3x']=='HL') & (df['high_structure_3x']!='HH') & (df['close'] > df['high_pivot_filled_3x'] ), 'pivot_go_breakout_3x'] = True
    df.loc[(df['high_pivot_confirmed_3x']) & (df['high_structure_3x']=='LH') & (df['low_structure_3x']!='LL') & (df['close'] < df['low_pivot_filled_3x']), 'pivot_go_breakdown_3x'] = True

    low_atr = atr_ranges[symbol][0]
    high_atr = atr_ranges[symbol][1]
    
    long_conditions = [
        (df['close'].shift(i) < df['high_pivot_filled_2x']).fillna(False) 
        for i in range(1, 11)
    ]
    long_shift_condition = pd.concat(long_conditions, axis=1).all(axis=1)
    
    second_long_condition = (
        (df['low_structure_2x'] == 'HL') & 
        long_shift_condition & 
        (df['high_structure_2x'] != 'HH') & 
        (df['close'] > df['high_pivot_filled_2x']) & 
        (df['pct_atr'].between(low_atr, high_atr)) & 
        (df['pivot_go_breakout_2x'] == False)
    )
    
    short_conditions = [
        (df['close'].shift(i) > df['low_pivot_filled_2x']).fillna(False) 
        for i in range(1, 11)
    ]
    short_shift_condition = pd.concat(short_conditions, axis=1).all(axis=1)
    
    second_short_condition = (
        (df['low_structure_2x'] != 'LL') & 
        short_shift_condition & 
        (df['high_structure_2x'] == 'LH') & 
        (df['close'] < df['low_pivot_filled_2x']) & 
        (df['pct_atr'].between(low_atr, high_atr)) & 
        (df['pivot_go_breakdown_2x'] == False)
    )


    df.loc[second_long_condition,'pivot_go_breakout_2x'] = True
    df.loc[second_short_condition,'pivot_go_breakdown_2x'] = True
    
    return df
