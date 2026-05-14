# scripts/build_gazp_complete_dataset.py
"""
Формирование полного датасета для ПАО «Газпром» (2020-2026)
Включает: цены, индексы, нефть Brent, газ, ставку ЦБ (через cbrapi),
курс USD (через XML API ЦБ), комментарии, Lenta, фундаментальные показатели
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys
from datetime import datetime
import requests
import xml.etree.ElementTree as ET

sys.path.append(str(Path(__file__).parent.parent))
from config.paths import RAW_DATA_DIR, FEATURES_DIR, PROCESSED_DATA_DIR


def safe_ffill(df, columns):
    """Безопасный forward fill"""
    for col in columns:
        if col in df.columns:
            df[col] = df[col].ffill()
    return df


def safe_fillna(df, columns, value=0):
    """Безопасное заполнение пропусков"""
    for col in columns:
        if col in df.columns:
            df[col] = df[col].fillna(value)
    return df


def load_cbr_key_rate():
    """Загружает ключевую ставку ЦБ через cbrapi"""

    start_date = '2020-01-01'
    end_date = '2026-03-15'

    try:
        import cbrapi as cbr

        all_data_list = []

        for year in range(2020, 2027):
            year_start = f"{year}-01-01"
            year_end = f"{year}-12-31" if year < 2026 else "2026-03-31"

            try:
                year_data = cbr.get_key_rate(year_start, year_end)
                if len(year_data) > 0:
                    if hasattr(year_data.index, 'to_timestamp'):
                        year_data.index = year_data.index.to_timestamp()
                    all_data_list.append(year_data)
            except:
                pass

        if not all_data_list:
            raise Exception("Не удалось загрузить данные через cbrapi")

        all_data = pd.concat(all_data_list)
        all_data = all_data[~all_data.index.duplicated(keep='first')]
        all_data = all_data.sort_index()

        date_range = pd.date_range(start=start_date, end=end_date, freq='D')

        df = pd.DataFrame({'date': date_range})
        df = df.set_index('date')
        df['cbr_key_rate'] = all_data.reindex(date_range, method='ffill')
        df['cbr_key_rate'] = df['cbr_key_rate'].fillna(all_data.iloc[0])
        df = df.reset_index()

        print(f"   ✅ Загружена ставка ЦБ через cbrapi")
        print(f"   Найдено изменений: {len(all_data[all_data.diff() != 0])}")
        print(f"   Диапазон: {df['cbr_key_rate'].min():.2f}% - {df['cbr_key_rate'].max():.2f}%")

        return df[['date', 'cbr_key_rate']]

    except ImportError:
        print(f"   ❌ Библиотека cbrapi не установлена")
        raise
    except Exception as e:
        print(f"   ❌ Ошибка загрузки ставки ЦБ: {e}")
        raise


def load_usd_rate():
    """Загружает курс доллара США через XML API ЦБ РФ (разбивка по годам)"""

    start_date = '2020-01-01'
    end_date = '2026-03-15'

    try:
        all_records = []

        # Разбиваем запрос по годам
        years = range(2020, 2027)

        for year in years:
            year_start = f"{year}-01-01"
            year_end = f"{year}-12-31" if year < 2026 else "2026-03-15"

            start_formatted = datetime.strptime(year_start, '%Y-%m-%d').strftime('%d/%m/%Y')
            end_formatted = datetime.strptime(year_end, '%Y-%m-%d').strftime('%d/%m/%Y')

            url = "https://www.cbr.ru/scripts/XML_dynamic.asp"
            params = {
                'date_req1': start_formatted,
                'date_req2': end_formatted,
                'VAL_NM_RQ': 'R01235'
            }

            response = requests.get(url, params=params, timeout=30)

            if response.status_code != 200:
                print(f"   ⚠️ {year}: HTTP error {response.status_code}")
                continue

            root = ET.fromstring(response.content)

            year_records = 0
            for record in root.findall('Record'):
                date_str = record.get('Date')
                value_elem = record.find('Value')

                if date_str and value_elem is not None and value_elem.text:
                    try:
                        date = datetime.strptime(date_str, '%d.%m.%Y')
                        value = float(value_elem.text.replace(',', '.'))
                        all_records.append({'date': date, 'usd_rate': value})
                        year_records += 1
                    except:
                        pass

            print(f"   {year}: загружено {year_records} записей")

        if not all_records:
            raise Exception("Не удалось получить данные ни за один год")

        usd_df = pd.DataFrame(all_records)
        usd_df = usd_df.sort_values('date')
        usd_df = usd_df.drop_duplicates(subset=['date'])

        # Создаём непрерывный ряд
        date_range = pd.date_range(start=start_date, end=end_date, freq='D')

        df = pd.DataFrame({'date': date_range})
        df = df.merge(usd_df, on='date', how='left')
        df['usd_rate'] = df['usd_rate'].ffill()

        # Заполняем начало периода
        first_valid = usd_df['usd_rate'].iloc[0]
        df['usd_rate'] = df['usd_rate'].fillna(first_valid)

        print(f"   ✅ Загружен курс USD через XML API ЦБ РФ")
        print(f"   Всего записей: {len(usd_df)}")
        print(f"   Диапазон: {df['usd_rate'].min():.4f} - {df['usd_rate'].max():.4f} руб")

        return df[['date', 'usd_rate']]

    except Exception as e:
        print(f"   ❌ Ошибка загрузки курса USD: {e}")
        raise


def load_manual_financial_data():
    """Загружает фундаментальные показатели Газпрома из подготовленного файла"""

    manual_file = PROCESSED_DATA_DIR / "gazp_financial_data/gazp_manual_data.csv"

    if manual_file.exists():
        df = pd.read_csv(manual_file)
        print(f"   ✅ Загружены фундаментальные показатели: {len(df)} записей")
        return df
    else:
        print(f"   ⚠️ Файл с фундаментальными показателями не найден: {manual_file}")
        print(f"   Создайте файл с колонками: year, bvps_rub, eps_rub, pb_ratio, pe_ratio, graham_number_rub")
        return None


def aggregate_comments(comments_df):
    """Агрегация комментариев по датам"""

    comments_df['date'] = pd.to_datetime(comments_df['date']).dt.date
    comments_df['date'] = pd.to_datetime(comments_df['date'])

    daily = comments_df.groupby('date').agg(
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

    return daily


def build_gazp_dataset():
    """Формирует полный датасет для Газпрома"""

    print("=" * 80)
    print("ФОРМИРОВАНИЕ ДАТАСЕТА ДЛЯ GAZP")
    print("=" * 80)

    # ========== 1. ЦЕНЫ ==========
    print("\n1. Загрузка цен MOEX...")

    prices_file = RAW_DATA_DIR / "moex/stocks.csv"
    if not prices_file.exists():
        print(f"   ❌ Файл не найден: {prices_file}")
        return None

    prices = pd.read_csv(prices_file)
    prices['date'] = pd.to_datetime(prices['date'])
    prices = prices[prices['ticker'] == 'GAZP'].copy()
    prices = prices[['date', 'open', 'high', 'low', 'close', 'volume']]
    prices = prices.rename(columns={'close': 'price'})
    prices = prices.sort_values('date')

    print(f"   Загружено: {len(prices)} записей")
    print(f"   Период: {prices['date'].min().date()} - {prices['date'].max().date()}")

    # ========== 2. ИНДЕКСЫ ==========
    print("\n2. Загрузка индексов MOEX...")

    indices_file = RAW_DATA_DIR / "moex/indices.csv"
    indices_pivot = pd.DataFrame()

    if indices_file.exists():
        indices = pd.read_csv(indices_file)
        indices['date'] = pd.to_datetime(indices['date'])
        indices_pivot = indices.pivot(index='date', columns='ticker', values='close').reset_index()
        print(f"   Загружены индексы: {indices_pivot.shape}")
    else:
        print(f"   ⚠️ Файл не найден: {indices_file}")

    # ========== 3. НЕФТЬ И ГАЗ ==========
    print("\n3. Загрузка нефти и газа...")

    commodity_file = RAW_DATA_DIR / "commodities/commodity_prices_global.csv"
    commodities = pd.DataFrame()

    if commodity_file.exists():
        commodities = pd.read_csv(commodity_file)
        commodities['date'] = pd.to_datetime(commodities['date'])
        commodities = commodities[['date', 'brent', 'natural_gas']].copy()
        commodities = commodities.rename(columns={
            'brent': 'oil_brent',
            'natural_gas': 'gas_henry_hub'
        })
        print(f"   Загружены: нефть Brent, газ Henry Hub")
    else:
        print(f"   ⚠️ Файл не найден: {commodity_file}")

    # ========== 4. СТАВКА ЦБ ==========
    print("\n4. Загрузка ключевой ставки ЦБ...")
    cbr = load_cbr_key_rate()

    # ========== 5. КУРС USD ==========
    print("\n5. Загрузка курса доллара США...")
    usd = load_usd_rate()

    # ========== 6. КОММЕНТАРИИ ==========
    print("\n6. Загрузка и агрегация комментариев...")

    comments_file = FEATURES_DIR / "qwen35_classified/qwen35_classified_all.csv"
    daily_comments = pd.DataFrame()

    if comments_file.exists():
        comments = pd.read_csv(comments_file)
        print(f"   Загружено комментариев: {len(comments)}")

        if 'ticker' in comments.columns:
            comments = comments[comments['ticker'] == 'GAZP']
            print(f"   Записей для GAZP: {len(comments)}")

        if len(comments) > 0:
            daily_comments = aggregate_comments(comments)
            print(f"   Агрегировано: {len(daily_comments)} дней")
            print(f"   Всего комментариев: {daily_comments['comments_total'].sum():.0f}")
        else:
            print("   ⚠️ Нет комментариев для GAZP")
    else:
        print(f"   ⚠️ Файл не найден: {comments_file}")

    # ========== 7. ЗАГОЛОВКИ LENTA ==========
    print("\n7. Загрузка заголовков Lenta...")

    lenta_file = FEATURES_DIR / "lenta_classified/lenta_headers_classified.csv"
    daily_lenta = pd.DataFrame()

    if lenta_file.exists():
        lenta = pd.read_csv(lenta_file)
        lenta['date'] = pd.to_datetime(lenta['date'])

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
    else:
        print(f"   ⚠️ Файл не найден: {lenta_file}")

    # ========== 8. ФУНДАМЕНТАЛЬНЫЕ ПОКАЗАТЕЛИ ==========
    print("\n8. Загрузка фундаментальных показателей...")
    manual_data = load_manual_financial_data()
    if manual_data is not None:
        manual_data['year'] = manual_data['year'].astype(int)

    # ========== 9. ОБЪЕДИНЕНИЕ ==========
    print("\n9. Объединение данных...")

    start_date = '2020-01-01'
    end_date = '2026-03-15'
    dates = pd.DataFrame({'date': pd.date_range(start_date, end_date, freq='D')})
    df = dates.copy()

    # Цены
    df = df.merge(prices, on='date', how='left')

    # Индексы
    if not indices_pivot.empty:
        df = df.merge(indices_pivot, on='date', how='left')

    # Нефть и газ
    if not commodities.empty:
        df = df.merge(commodities, on='date', how='left')

    # Ставка ЦБ
    if not cbr.empty:
        df = df.merge(cbr, on='date', how='left')

    # Курс USD
    if not usd.empty:
        df = df.merge(usd, on='date', how='left')

    # Комментарии
    if not daily_comments.empty:
        df = df.merge(daily_comments, on='date', how='left')

    # Lenta
    if not daily_lenta.empty:
        df = df.merge(daily_lenta, on='date', how='left')

    # Фундаментальные показатели
    if manual_data is not None:
        df['year'] = df['date'].dt.year
        df = df.merge(manual_data, on='year', how='left')
        df = df.drop(columns=['year'])

    print(f"   После объединения: {df.shape}")

    # ========== 10. ЗАПОЛНЕНИЕ ПРОПУСКОВ ==========
    print("\n10. Заполнение пропусков...")

    # Ценовые данные
    price_cols = ['price', 'volume', 'open', 'high', 'low']
    df = safe_ffill(df, price_cols)
    df['volume'] = df['volume'].fillna(0)

    # Индексы
    index_cols = ['IMOEX', 'RTSI', 'MOEXOG', 'MOEXFN', 'MOEXMM', 'MOEXCN']
    existing_indices = [c for c in index_cols if c in df.columns]
    df = safe_ffill(df, existing_indices)

    # Сырьевые товары
    if 'oil_brent' in df.columns:
        df['oil_brent'] = df['oil_brent'].ffill()
    if 'gas_henry_hub' in df.columns:
        df['gas_henry_hub'] = df['gas_henry_hub'].ffill()

    # Ставка ЦБ и курс USD уже заполнены
    if 'cbr_key_rate' in df.columns:
        df['cbr_key_rate'] = df['cbr_key_rate'].ffill()
    if 'usd_rate' in df.columns:
        df['usd_rate'] = df['usd_rate'].ffill()

    # Новостные данные
    news_cols = [c for c in df.columns if c.startswith('comments_') or c.startswith('lenta_')]
    df = safe_fillna(df, news_cols, 0)

    # Фундаментальные показатели
    fund_cols = ['bvps_rub', 'eps_rub', 'graham_number_rub', 'pb_ratio', 'pe_ratio']
    df = safe_ffill(df, fund_cols)
    df = safe_fillna(df, fund_cols, 0)

    # ========== 11. ФИНАЛЬНАЯ ОЧИСТКА ==========
    print("\n11. Финальная очистка...")

    df = df.dropna(subset=['price'])
    df = df.sort_values('date')
    df = df.drop_duplicates(subset=['date'])
    df = df.reset_index(drop=True)

    df['return_today'] = df['price'].pct_change()
    df['return_next_day'] = df['price'].shift(-1) / df['price'] - 1
    df['direction_next_day'] = (df['return_next_day'] > 0).astype(int)
    df['ticker'] = 'GAZP'

    # ========== 12. СОХРАНЕНИЕ ==========
    print("\n12. Сохранение датасета...")

    output_dir = PROCESSED_DATA_DIR / "gazp_financial_data"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "GAZP_complete_dataset.csv"
    df.to_csv(output_file, index=False, encoding='utf-8')
    print(f"   ✅ Сохранён: {output_file}")

    # ========== 13. ИТОГИ ==========
    print("\n" + "=" * 80)
    print("ИТОГИ СБОРКИ")
    print("=" * 80)
    print(f"   Форма датасета: {df.shape}")
    print(f"   Период: {df['date'].min().date()} - {df['date'].max().date()}")
    print(f"   Торговых дней: {len(df)}")

    print(f"\n   КЛЮЧЕВЫЕ КОЛОНКИ:")
    key_cols = ['price', 'volume', 'oil_brent', 'gas_henry_hub', 'cbr_key_rate', 'usd_rate',
                'comments_total', 'lenta_total', 'bvps_rub', 'pe_ratio']
    for col in key_cols:
        if col in df.columns:
            if col == 'cbr_key_rate':
                print(f"      ✅ {col}: {df[col].min():.2f}% - {df[col].max():.2f}%")
            elif col == 'usd_rate':
                print(f"      ✅ {col}: {df[col].min():.4f} - {df[col].max():.4f} руб")
            elif col in ['price', 'volume', 'bvps_rub']:
                print(f"      ✅ {col}: {df[col].mean():.2f}")
            else:
                print(f"      ✅ {col}")
        else:
            print(f"      ❌ {col}: отсутствует")

    return df


if __name__ == "__main__":
    df = build_gazp_dataset()

    if df is not None:
        print("\n" + "=" * 80)
        print("ПОСЛЕДНИЕ 10 ДНЕЙ:")
        print("=" * 80)
        cols = ['date', 'price', 'oil_brent', 'gas_henry_hub', 'cbr_key_rate', 'usd_rate', 'comments_total']
        existing_cols = [c for c in cols if c in df.columns]
        print(df.tail(10)[existing_cols].to_string())