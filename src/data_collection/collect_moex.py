# src/data_collection/collect_moex.py

"""
Сбор данных MOEX
Акции: OHLCV (open, high, low, close, volume)
Индексы: только close (как в оригинале)
"""

import apimoex
import requests
import pandas as pd
import time
from pathlib import Path
from datetime import datetime, timedelta
import sys

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR
from config.companies import TICKERS

# ========== КОНФИГ ==========
START_DATE = "2020-01-01"
END_DATE = "2026-03-31"
STOCKS = TICKERS
INDICES = ['IMOEX', 'RTSI', 'MOEXOG', 'MOEXFN', 'MOEXMM', 'MOEXCN']
OUTPUT_DIR = RAW_DATA_DIR / "moex"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
session = requests.Session()


def fetch_stock(ticker):
    """Акции: OHLCV"""
    print(f"📊 {ticker}...")
    all_data = []
    start = datetime.strptime(START_DATE, '%Y-%m-%d')
    end = datetime.strptime(END_DATE, '%Y-%m-%d')

    while start < end:
        chunk_end = min(start + timedelta(days=365), end)
        data = apimoex.get_board_candles(
            session, security=ticker, interval=24,
            start=start.strftime('%Y-%m-%d'),
            end=chunk_end.strftime('%Y-%m-%d')
        )
        if data:
            all_data.extend(data)
        start = chunk_end + timedelta(days=1)
        time.sleep(0.3)

    if not all_data:
        return None

    df = pd.DataFrame(all_data)
    result = pd.DataFrame({
        'date': pd.to_datetime(df['begin']),
        'ticker': ticker,
        'open': pd.to_numeric(df['open'], errors='coerce'),
        'high': pd.to_numeric(df['high'], errors='coerce'),
        'low': pd.to_numeric(df['low'], errors='coerce'),
        'close': pd.to_numeric(df['close'], errors='coerce'),
        'volume': pd.to_numeric(df['volume'], errors='coerce'),
        'value': pd.to_numeric(df['value'], errors='coerce'),
    })
    print(f"   ✅ {len(result)} записей")
    return result.sort_values('date')


def fetch_index(ticker):
    """Индексы: только close (оригинальный формат)"""
    print(f"📈 {ticker}...")
    data = apimoex.get_market_history(
        session,
        security=ticker,
        start=START_DATE,
        end=END_DATE,
        market='index'
    )
    if not data:
        return None

    df = pd.DataFrame(data)
    result = pd.DataFrame({
        'date': pd.to_datetime(df['TRADEDATE']),
        'ticker': ticker,
        'source': 'MOEX',
        'tradedate': df['TRADEDATE'],
        'close': pd.to_numeric(df['CLOSE'], errors='coerce'),
    })
    print(f"   ✅ {len(result)} записей")
    return result.sort_values('date')


# ========== ЗАПУСК ==========
if __name__ == "__main__":
    # Акции
    print("\n" + "=" * 60)
    print("СБОР АКЦИЙ (OHLCV)")
    print("=" * 60)
    stocks_list = []
    for ticker in STOCKS:
        df = fetch_stock(ticker)
        if df is not None:
            stocks_list.append(df)
            df.to_csv(OUTPUT_DIR / f"{ticker}.csv", index=False)
        time.sleep(0.5)

    if stocks_list:
        pd.concat(stocks_list, ignore_index=True).to_csv(OUTPUT_DIR / "stocks.csv", index=False)
        print(f"\n✅ stocks.csv")

    # Индексы
    print("\n" + "=" * 60)
    print("СБОР ИНДЕКСОВ (close)")
    print("=" * 60)
    indices_list = []
    for ticker in INDICES:
        df = fetch_index(ticker)
        if df is not None:
            indices_list.append(df)
            df.to_csv(OUTPUT_DIR / f"{ticker}.csv", index=False)
        time.sleep(0.5)

    if indices_list:
        pd.concat(indices_list, ignore_index=True).to_csv(OUTPUT_DIR / "indices.csv", index=False)
        print(f"\n✅ indices.csv")

    print("\n🎉 ГОТОВО!")