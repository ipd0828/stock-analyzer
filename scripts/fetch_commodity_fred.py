# scripts/fetch_commodity_fred.py

import pandas as pd
from pathlib import Path

OUTPUT_DIR = Path("data/raw/commodities")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# FRED серии (бесплатно)
SERIES = {
    'brent': 'DCOILBRENTEU',  # Brent - Europe
    'wti': 'DCOILWTICO',  # WTI - Cushing
    'natural_gas': 'DHHNGSP',  # Henry Hub Natural Gas
}


def fetch():
    df = None
    for name, series_id in SERIES.items():
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        try:
            data = pd.read_csv(url)
            data.columns = ['date', name]
            data['date'] = pd.to_datetime(data['date'])

            if df is None:
                df = data
            else:
                df = df.merge(data, on='date', how='outer')
            print(f"✅ {name}: {len(data)} записей")
        except Exception as e:
            print(f"❌ {name}: {e}")

    if df is not None:
        df = df.sort_values('date').reset_index(drop=True)
        output_file = OUTPUT_DIR / "commodity_prices_fred.csv"
        df.to_csv(output_file, index=False)
        print(f"\n✅ Сохранено: {output_file}")


if __name__ == "__main__":
    fetch()