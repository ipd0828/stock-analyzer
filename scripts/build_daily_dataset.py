# scripts/build_daily_dataset_v2.py

"""
Построение дневного датасета
- Нормализация дат
- Агрегация комментариев по дням и тикерам
- Агрегация новостей Lenta по дням
- Объединение с ценами акций
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))
from config.paths import RAW_DATA_DIR, FEATURES_DIR

OUTPUT_DIR = Path("data/daily_dataset")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def normalize_date_series(series):
    """
    Приводит серию с датами к единому формату YYYY-MM-DD
    """
    series_str = series.astype(str)
    series_date = series_str.str[:10]
    return pd.to_datetime(series_date, format='%Y-%m-%d', errors='coerce')


def load_and_prepare_prices():
    """Загружает цены акций (OHLCV)"""
    print("\n📈 1. Загрузка цен MOEX...")

    prices_file = RAW_DATA_DIR / "moex/stocks.csv"
    if not prices_file.exists():
        print(f"   ❌ Файл не найден: {prices_file}")
        return None

    prices = pd.read_csv(prices_file)
    prices['date'] = normalize_date_series(prices['date'])
    prices = prices.dropna(subset=['date'])

    # Берём нужные колонки
    prices = prices[['date', 'ticker', 'open', 'high', 'low', 'close', 'volume']]
    prices = prices.rename(columns={'close': 'price'})

    print(f"   Загружено: {len(prices)} записей")
    print(f"   Период: {prices['date'].min()} - {prices['date'].max()}")
    print(f"   Тикеры: {prices['ticker'].unique().tolist()}")

    return prices


def load_and_prepare_comments():
    """Загружает и агрегирует комментарии по дням и тикерам"""
    print("\n💬 2. Загрузка и агрегация комментариев...")

    comments_file = FEATURES_DIR / "qwen35_classified/qwen35_classified_all.csv"
    if not comments_file.exists():
        print(f"   ❌ Файл не найден: {comments_file}")
        return None

    comments = pd.read_csv(comments_file)
    print(f"   Загружено комментариев: {len(comments)}")

    # Нормализуем дату
    comments['date'] = normalize_date_series(comments['date'])
    comments = comments.dropna(subset=['date'])
    print(f"   После нормализации дат: {len(comments)}")

    # Агрегация по дате и тикеру
    daily_comments = comments.groupby(['date', 'ticker']).agg(
        comments_positive=('sentiment', lambda x: (x == 'POSITIVE').sum()),
        comments_negative=('sentiment', lambda x: (x == 'NEGATIVE').sum()),
        comments_neutral=('sentiment', lambda x: (x == 'NEUTRAL').sum()),
        comments_total=('sentiment', 'count'),
        comments_price=('category', lambda x: (x == 'PRICE').sum()),
        comments_dividends=('category', lambda x: (x == 'DIVIDENDS').sum()),
        comments_reports=('category', lambda x: (x == 'REPORTS').sum()),
        comments_macro=('category', lambda x: (x == 'MACRO').sum()),
        comments_news=('category', lambda x: (x == 'NEWS').sum()),
    ).reset_index()

    print(f"   Агрегировано: {len(daily_comments)} записей (день-тикер)")

    # Покажем пример
    if len(daily_comments) > 0:
        print(f"   Пример: {daily_comments.head(1).to_string()}")

    return daily_comments


def load_and_prepare_lenta():
    """Загружает и агрегирует новости Lenta по дням"""
    print("\n📰 3. Загрузка и агрегация новостей Lenta...")

    lenta_file = FEATURES_DIR / "lenta_classified/lenta_headers_classified.csv"
    if not lenta_file.exists():
        print(f"   ⚠️ Файл не найден: {lenta_file}")
        return None

    lenta = pd.read_csv(lenta_file)
    print(f"   Загружено заголовков: {len(lenta)}")

    lenta['date'] = normalize_date_series(lenta['date'])
    lenta = lenta.dropna(subset=['date'])
    print(f"   После нормализации дат: {len(lenta)}")

    # Агрегация по дате
    daily_lenta = lenta.groupby('date').agg(
        lenta_positive=('sentiment', lambda x: (x == 'POSITIVE').sum()),
        lenta_negative=('sentiment', lambda x: (x == 'NEGATIVE').sum()),
        lenta_neutral=('sentiment', lambda x: (x == 'NEUTRAL').sum()),
        lenta_total=('sentiment', 'count'),
        lenta_war=('category', lambda x: (x == 'WAR').sum()),
        lenta_sanctions=('category', lambda x: (x == 'SANCTIONS').sum()),
        lenta_oil_gas=('category', lambda x: (x == 'OIL_GAS').sum()),
        lenta_market=('category', lambda x: (x == 'MARKET').sum()),
        lenta_political=('category', lambda x: (x == 'POLITICAL').sum()),
    ).reset_index()

    print(f"   Агрегировано: {len(daily_lenta)} дней")

    return daily_lenta


def build_dataset(start_date='2020-01-01', end_date='2026-03-31'):
    """Строит итоговый датасет"""

    print("=" * 80)
    print("📊 ПОСТРОЕНИЕ ДНЕВНОГО ДАТАСЕТА")
    print(f"   Период: {start_date} - {end_date}")
    print("=" * 80)

    # Загружаем данные
    prices = load_and_prepare_prices()
    comments = load_and_prepare_comments()
    lenta = load_and_prepare_lenta()

    if prices is None:
        print("❌ Нет данных по ценам")
        return None

    # Фильтруем по дате
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    prices = prices[(prices['date'] >= start) & (prices['date'] <= end)]

    if prices.empty:
        print("❌ Нет данных по ценам за указанный период")
        return None

    companies = prices['ticker'].unique()
    all_data = []

    for ticker in companies:
        print(f"\n📊 {ticker}")

        # Биржевые данные
        ticker_prices = prices[prices['ticker'] == ticker].copy()

        # Комментарии по компании
        ticker_comments = None
        if comments is not None:
            ticker_comments = comments[comments['ticker'] == ticker].copy()
            if 'ticker' in ticker_comments.columns:
                ticker_comments = ticker_comments.drop(columns=['ticker'])

        # Объединяем
        df = ticker_prices.copy()
        if ticker_comments is not None and len(ticker_comments) > 0:
            df = df.merge(ticker_comments, on='date', how='left')

        # Добавляем новости Lenta
        if lenta is not None:
            df = df.merge(lenta, on='date', how='left')

        # Заполняем NaN
        comment_cols = ['comments_positive', 'comments_negative', 'comments_neutral',
                        'comments_total', 'comments_price', 'comments_dividends',
                        'comments_reports', 'comments_macro', 'comments_news']
        for col in comment_cols:
            if col in df.columns:
                df[col] = df[col].fillna(0)

        lenta_cols = ['lenta_positive', 'lenta_negative', 'lenta_neutral', 'lenta_total',
                      'lenta_war', 'lenta_sanctions', 'lenta_oil_gas', 'lenta_market', 'lenta_political']
        for col in lenta_cols:
            if col in df.columns:
                df[col] = df[col].fillna(0)

        # Заполняем пропуски в ценах (выходные)
        df['price'] = df['price'].replace(0, np.nan).ffill().fillna(0)
        df['volume'] = df['volume'].replace(0, np.nan).ffill().fillna(0)

        all_data.append(df)

        print(f"   Дней: {len(df)}")
        if comments is not None:
            print(f"   Комментариев: {df['comments_total'].sum():,.0f}")
        if lenta is not None:
            print(f"   Новостей Lenta: {df['lenta_total'].sum():,.0f}")

    # Объединяем все компании
    final_df = pd.concat(all_data, ignore_index=True)
    final_df = final_df.sort_values(['ticker', 'date'])

    # Сохраняем
    output_file = OUTPUT_DIR / f"daily_dataset_{start_date}_to_{end_date}.csv"
    final_df.to_csv(output_file, index=False, encoding='utf-8')

    print("\n" + "=" * 80)
    print("✅ ДНЕВНОЙ ДАТАСЕТ СОЗДАН")
    print("=" * 80)
    print(f"   Файл: {output_file}")
    print(f"   Записей: {len(final_df)}")
    print(f"   Колонок: {len(final_df.columns)}")

    # Статистика по компаниям
    print("\n📊 СТАТИСТИКА ПО КОМПАНИЯМ:")
    for ticker in companies:
        ticker_df = final_df[final_df['ticker'] == ticker]
        comments_sum = ticker_df['comments_total'].sum() if 'comments_total' in ticker_df.columns else 0
        lenta_sum = ticker_df['lenta_total'].sum() if 'lenta_total' in ticker_df.columns else 0
        print(f"   {ticker}: {len(ticker_df)} дней, комм: {comments_sum:,.0f}, lenta: {lenta_sum:,.0f}")

    return final_df


if __name__ == "__main__":
    df = build_dataset(start_date='2020-01-01', end_date='2026-03-31')

    # Покажем примеры строк с комментариями
    if df is not None and 'comments_total' in df.columns:
        print("\n📋 ПРИМЕРЫ СТРОК С КОММЕНТАРИЯМИ:")
        with_comments = df[df['comments_total'] > 0]
        if len(with_comments) > 0:
            print(with_comments.head(10).to_string())
        else:
            print("⚠️ Нет строк с комментариями за этот период")