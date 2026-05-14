# scripts/fetch_commodity_global.py

import yfinance as yf
import pandas as pd
from pathlib import Path

OUTPUT_DIR = Path("data/raw/commodities")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Тикеры на yfinance
COMMODITIES = {
    'brent': 'BZ=F',  # Brent crude oil
    'wti': 'CL=F',  # WTI crude oil
    'natural_gas': 'NG=F',  # Natural gas Henry Hub
    'russian_urals': 'URALS',  # Urals (если есть)
}


def fetch():
    df = None
    for name, ticker in COMMODITIES.items():
        try:
            data = yf.download(ticker, start='2020-01-01', progress=False)
            data = data[['Close']].reset_index()
            data.columns = ['date', name]

            if df is None:
                df = data
            else:
                df = df.merge(data, on='date', how='outer')
            print(f"✅ {name}: {len(data)} записей")
        except Exception as e:
            print(f"❌ {name}: {e}")

    if df is not None:
        df = df.sort_values('date').reset_index(drop=True)
        output_file = OUTPUT_DIR / "commodity_prices_global.csv"
        df.to_csv(output_file, index=False)
        print(f"\n✅ Сохранено: {output_file}")
        print(f"   Период: {df['date'].min()} - {df['date'].max()}")


if __name__ == "__main__":
    fetch()