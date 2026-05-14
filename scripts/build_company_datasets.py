#!/usr/bin/env python3
# scripts/build_company_datasets.py
"""
Универсальный скрипт формирования полного датасета для 5 компаний.
Фундаментальные данные загружаются из PostgreSQL.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys
from datetime import datetime
import requests
import xml.etree.ElementTree as ET
import psycopg2
from psycopg2.extras import RealDictCursor
import argparse
import time

sys.path.append(str(Path(__file__).parent.parent))
from config.paths import RAW_DATA_DIR, FEATURES_DIR, PROCESSED_DATA_DIR

# ========== КОНФИГУРАЦИЯ ==========
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "investment_db",
    "user": "investor_nick",
    "password": "1q2A3z4X!@#"
}

START_DATE = "2020-01-01"
END_DATE = "2026-03-31"

COMPANIES = {
    'GAZP': 'Газпром',
    'SBER': 'Сбер',
    'LKOH': 'Лукойл',
    'NVTK': 'Новатэк',
    'VTBR': 'ВТБ'
}


def safe_convert_date(series):
    """Безопасно конвертирует дату в datetime64[ns] без часового пояса"""
    series = pd.to_datetime(series, errors='coerce')
    if hasattr(series.dtype, 'tz') and series.dtype.tz is not None:
        series = series.dt.tz_localize(None)
    return series


def load_cbr_key_rate():
    """Загружает ключевую ставку ЦБ"""
    print("   📊 Загрузка ключевой ставки ЦБ...")
    try:
        import cbrapi as cbr
        all_data = []
        for year in range(2020, 2027):
            y_start = f"{year}-01-01"
            y_end = f"{year}-12-31" if year < 2026 else "2026-03-31"
            try:
                data = cbr.get_key_rate(y_start, y_end)
                if len(data) > 0:
                    if hasattr(data.index, 'to_timestamp'):
                        data.index = data.index.to_timestamp()
                    all_data.append(data)
            except:
                pass
        if not all_data:
            raise Exception("Нет данных cbrapi")
        combined = pd.concat(all_data)
        combined = combined[~combined.index.duplicated(keep='first')].sort_index()
        date_range = pd.date_range(start=START_DATE, end=END_DATE, freq='D')
        df = pd.DataFrame({'date': date_range}).set_index('date')
        df['cbr_key_rate'] = combined.reindex(date_range, method='ffill')
        df['cbr_key_rate'] = df['cbr_key_rate'].fillna(combined.iloc[0])
        df = df.reset_index()
        print(f"      ✅ {df['cbr_key_rate'].min():.1f}% - {df['cbr_key_rate'].max():.1f}%")
        return df[['date', 'cbr_key_rate']]
    except Exception as e:
        print(f"      ❌ Ошибка: {e}")
        return pd.DataFrame(columns=['date', 'cbr_key_rate'])


def load_usd_rate():
    """Загружает курс USD через XML API ЦБ РФ"""
    print("   💵 Загрузка курса USD...")
    try:
        all_records = []
        for year in range(2020, 2027):
            y_start = f"{year}-01-01"
            y_end = f"{year}-12-31" if year < 2026 else "2026-03-15"
            start_fmt = datetime.strptime(y_start, '%Y-%m-%d').strftime('%d/%m/%Y')
            end_fmt = datetime.strptime(y_end, '%Y-%m-%d').strftime('%d/%m/%Y')
            url = "https://www.cbr.ru/scripts/XML_dynamic.asp"
            params = {'date_req1': start_fmt, 'date_req2': end_fmt, 'VAL_NM_RQ': 'R01235'}
            response = requests.get(url, params=params, timeout=30)
            if response.status_code != 200:
                continue
            root = ET.fromstring(response.content)
            for record in root.findall('Record'):
                date_str = record.get('Date')
                value_elem = record.find('Value')
                if date_str and value_elem is not None and value_elem.text:
                    try:
                        date = datetime.strptime(date_str, '%d.%m.%Y')
                        value = float(value_elem.text.replace(',', '.'))
                        all_records.append({'date': date, 'usd_rate': value})
                    except:
                        pass
            time.sleep(0.3)
        if not all_records:
            raise Exception("Нет данных USD")
        usd_df = pd.DataFrame(all_records).sort_values('date').drop_duplicates(subset=['date'])
        date_range = pd.date_range(start=START_DATE, end=END_DATE, freq='D')
        df = pd.DataFrame({'date': date_range})
        df = df.merge(usd_df, on='date', how='left')
        df['usd_rate'] = df['usd_rate'].ffill().fillna(usd_df['usd_rate'].iloc[0])
        print(f"      ✅ {df['usd_rate'].min():.2f} - {df['usd_rate'].max():.2f} руб")
        return df[['date', 'usd_rate']]
    except Exception as e:
        print(f"      ❌ Ошибка: {e}")
        return pd.DataFrame(columns=['date', 'usd_rate'])


def load_fundamental_from_db(ticker: str) -> pd.DataFrame:
    """Загружает фундаментальные показатели из PostgreSQL"""
    print(f"   📊 Загрузка фундаментальных данных {ticker} из БД...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)

        # Сначала проверим, какие периоды есть в БД
        check_query = """
        SELECT DISTINCT fr.period, fr.report_type, fr.year
        FROM financial_reports fr
        JOIN companies c ON c.id = fr.company_id
        WHERE c.code = %s AND c.exchange = 'MOEX'
        ORDER BY fr.year, fr.period
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(check_query, (ticker,))
            periods_info = cur.fetchall()

        print(f"      🔍 Доступные периоды в БД:")
        for p in periods_info:
            print(f"         year={p['year']}, period='{p['period']}', type='{p['report_type']}'")

        # Основной запрос — берём ВСЕ записи, потом отфильтруем
        query = """
        SELECT 
            c.code,
            fr.year,
            fr.month,
            fr.period,
            fr.report_type,
            fr.revenue,
            fr.earnings,
            fr.ebitda,
            fr.total_assets,
            fr.equity_stock_holders,
            fr.total_debt,
            fr.net_debt,
            fr.cash_and_equiv,
            fr.current_assets,
            fr.current_liabilities,
            fr.eps,
            fr.cfo,
            fr.fcf,
            fr.capex
        FROM financial_reports fr
        JOIN companies c ON c.id = fr.company_id
        WHERE c.code = %s AND c.exchange = 'MOEX'
          AND fr.year >= 2020
        ORDER BY fr.year, fr.month
        """

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (ticker,))
            rows = cur.fetchall()

        conn.close()

        if not rows:
            print(f"      ⚠️ Нет данных в БД для {ticker}")
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        print(f"      📥 Всего строк из БД: {len(df)}")

        # Определяем, какие периоды считать "годовыми"
        # Y = годовой, YTM = year-to-date, также может быть Q, 3m, 6m, 9m
        yearly_periods = ['Y', 'YTM', '12m', '12M', 'FY', 'Annual']
        df['is_yearly'] = df['period'].str.upper().isin([p.upper() for p in yearly_periods])

        # Если годовых нет, берём квартальные с month=12 (конец года)
        if df['is_yearly'].sum() == 0:
            print(f"      ⚠️ Нет годовых периодов, ищем записи за декабрь...")
            df['is_yearly'] = (df['month'] == 12) | (df['month'].isna())

        # Оставляем только годовые
        df = df[df['is_yearly']].copy()

        # Приоритет: МСФО > РСБУ
        df['priority'] = df['report_type'].apply(
            lambda x: 1 if x and 'МСФО' in str(x).upper() else
            (2 if x and 'РСБУ' in str(x).upper() else 3)
        )

        # Оставляем по одной записи на год (с наивысшим приоритетом)
        df = df.sort_values(['year', 'priority']).drop_duplicates(subset=['year'], keep='first')
        df = df.sort_values('year')

        print(f"      📋 После фильтрации: {len(df)} годовых записей, годы: {sorted(df['year'].tolist())}")

        # Количество акций (млн)
        shares_map = {
            'GAZP': 23645, 'SBER': 21587, 'LKOH': 851,
            'NVTK': 4500, 'VTBR': 790000
        }
        shares = shares_map.get(ticker, 1000)

        # Конвертируем в числа
        numeric_cols = ['revenue', 'earnings', 'ebitda', 'total_assets',
                        'equity_stock_holders', 'total_debt', 'net_debt',
                        'cash_and_equiv', 'current_assets', 'current_liabilities',
                        'eps', 'cfo', 'fcf', 'capex']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # BVPS (руб)
        df['bvps_rub'] = df['equity_stock_holders'] / shares

        # NCAV (руб)
        if 'current_assets' in df.columns and 'total_debt' in df.columns:
            df['ncav_rub'] = (df['current_assets'] - df['total_debt']) / shares

        # Graham Number (только при положительных EPS и BVPS)
        df['graham_number_rub'] = np.nan
        mask = (df['eps'].fillna(0) > 0) & (df['bvps_rub'].fillna(0) > 0)
        if mask.any():
            df.loc[mask, 'graham_number_rub'] = np.sqrt(
                22.5 * df.loc[mask, 'eps'] * df.loc[mask, 'bvps_rub']
            )

        # Мультипликаторы
        df['roe'] = np.where(
            df['equity_stock_holders'].fillna(0) != 0,
            df['earnings'] / df['equity_stock_holders'] * 100, np.nan
        )
        df['roa'] = np.where(
            df['total_assets'].fillna(0) != 0,
            df['earnings'] / df['total_assets'] * 100, np.nan
        )
        df['net_margin'] = np.where(
            df['revenue'].fillna(0) != 0,
            df['earnings'] / df['revenue'] * 100, np.nan
        )
        df['debt_to_equity'] = np.where(
            df['equity_stock_holders'].fillna(0) != 0,
            df['total_debt'] / df['equity_stock_holders'], np.nan
        )

        # Конвертируем в млрд
        for col in ['revenue', 'earnings', 'ebitda', 'total_assets', 'total_debt']:
            if col in df.columns:
                df[f'{col}_bln'] = df[col] / 1000

        # Только нужные колонки
        result_cols = [
            'year', 'period', 'report_type',
            'revenue_bln', 'earnings_bln', 'ebitda_bln',
            'eps', 'bvps_rub', 'ncav_rub', 'graham_number_rub',
            'roe', 'roa', 'net_margin', 'debt_to_equity'
        ]
        result_cols = [c for c in result_cols if c in df.columns]

        result = df[result_cols].copy()

        bvps_vals = result['bvps_rub'].dropna().round(0).tolist()
        print(f"      ✅ BVPS: {bvps_vals}")

        return result

    except Exception as e:
        print(f"      ❌ Ошибка БД: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def load_prices(ticker: str) -> pd.DataFrame:
    """Загружает цены акций с MOEX"""
    prices_file = RAW_DATA_DIR / "moex" / "stocks.csv"
    if not prices_file.exists():
        print(f"      ⚠️ Файл stocks.csv не найден")
        return pd.DataFrame()

    df = pd.read_csv(prices_file)
    df['date'] = safe_convert_date(df['date'])
    df = df[df['ticker'] == ticker].copy()
    if 'close' in df.columns:
        df = df.rename(columns={'close': 'price'})
    cols = ['date', 'open', 'high', 'low', 'price', 'volume']
    existing = [c for c in cols if c in df.columns]
    df = df[existing].sort_values('date')
    print(f"      ✅ {len(df)} записей ({df['date'].min().date()} - {df['date'].max().date()})")
    return df


def load_indices() -> pd.DataFrame:
    """Загружает индексы MOEX"""
    indices_file = RAW_DATA_DIR / "moex" / "indices.csv"
    if not indices_file.exists():
        return pd.DataFrame()
    df = pd.read_csv(indices_file)
    df['date'] = safe_convert_date(df['date'])
    pivot = df.pivot(index='date', columns='ticker', values='close').reset_index()
    return pivot


def load_commodities() -> pd.DataFrame:
    """Загружает цены на сырьё"""
    comm_file = RAW_DATA_DIR / "commodities" / "commodity_prices_global.csv"
    if not comm_file.exists():
        return pd.DataFrame()
    df = pd.read_csv(comm_file)
    df['date'] = safe_convert_date(df['date'])
    cols = {'brent': 'oil_brent', 'natural_gas': 'gas_henry_hub'}
    rename = {k: v for k, v in cols.items() if k in df.columns}
    df = df.rename(columns=rename)
    keep_cols = ['date'] + list(rename.values())
    return df[[c for c in keep_cols if c in df.columns]]


def load_comments(ticker: str) -> pd.DataFrame:
    """Загружает классифицированные комментарии SmartLab"""
    comments_file = FEATURES_DIR / "qwen35_classified" / "qwen35_classified_all.csv"
    if not comments_file.exists():
        print(f"      ⚠️ Файл не найден: {comments_file}")
        return pd.DataFrame()

    df = pd.read_csv(comments_file)

    # Ищем колонку с датой
    date_col = None
    for col in ['datetime', 'date', 'date_raw']:
        if col in df.columns:
            date_col = col
            break

    if date_col is None:
        print(f"      ❌ Нет колонки с датой! Колонки: {list(df.columns[:10])}")
        return pd.DataFrame()

    print(f"      📅 Используем колонку: {date_col}")

    # Конвертируем дату — берём ТОЛЬКО ДАТУ без времени
    df['date'] = safe_convert_date(df[date_col])
    df = df.dropna(subset=['date'])

    # Оставляем только дату (без времени)
    df['date'] = df['date'].dt.date
    df['date'] = pd.to_datetime(df['date'])

    # Очищаем строки
    if 'sentiment' in df.columns:
        df['sentiment'] = df['sentiment'].str.strip().str.upper()
    if 'category' in df.columns:
        df['category'] = df['category'].str.strip().str.upper()

    # Фильтруем по тикеру
    if 'ticker' in df.columns:
        df = df[df['ticker'] == ticker]

    if len(df) == 0:
        print(f"      ⚠️ Нет комментариев для {ticker}")
        return pd.DataFrame()

    print(f"      📥 Для {ticker}: {len(df)} комментариев, даты: {df['date'].min().date()} - {df['date'].max().date()}")

    # Агрегируем по дням
    daily = df.groupby('date').agg(
        comments_positive=('sentiment', lambda x: (x == 'POSITIVE').sum()),
        comments_negative=('sentiment', lambda x: (x == 'NEGATIVE').sum()),
        comments_neutral=('sentiment', lambda x: (x == 'NEUTRAL').sum()),
        comments_total=('sentiment', 'count'),
    ).reset_index()

    # Категории — отдельной агрегацией
    if 'category' in df.columns:
        cat_daily = df.groupby('date').agg(
            comments_price=('category', lambda x: (x == 'PRICE').sum()),
            comments_dividends=('category', lambda x: (x == 'DIVIDENDS').sum()),
            comments_reports=('category', lambda x: (x == 'REPORTS').sum()),
            comments_macro=('category', lambda x: (x == 'MACRO').sum()),
            comments_news=('category', lambda x: (x == 'NEWS').sum()),
        ).reset_index()
        daily = daily.merge(cat_daily, on='date', how='left')

    daily['comments_pos_ratio'] = daily['comments_positive'] / (daily['comments_total'] + 1)
    daily['comments_neg_ratio'] = daily['comments_negative'] / (daily['comments_total'] + 1)

    print(f"      ✅ Агрегировано: {len(daily)} дней, всего {daily['comments_total'].sum():.0f} комментариев")
    print(f"         POS: {daily['comments_positive'].sum():.0f}, NEG: {daily['comments_negative'].sum():.0f}")

    return daily


def load_lenta() -> pd.DataFrame:
    """Загружает классифицированные заголовки Lenta"""
    lenta_file = FEATURES_DIR / "lenta_classified" / "lenta_headers_classified.csv"
    if not lenta_file.exists():
        return pd.DataFrame()

    df = pd.read_csv(lenta_file)
    df['date'] = safe_convert_date(df['date'])
    df = df.dropna(subset=['date'])
    df['date'] = df['date'].dt.date
    df['date'] = pd.to_datetime(df['date'])

    df['sentiment'] = df['sentiment'].str.strip().str.upper()
    df['category'] = df['category'].str.strip().str.upper()

    daily = df.groupby('date').agg(
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

    daily['lenta_pos_ratio'] = daily['lenta_positive'] / (daily['lenta_total'] + 1)
    daily['lenta_neg_ratio'] = daily['lenta_negative'] / (daily['lenta_total'] + 1)

    return daily


def build_dataset(ticker: str, output_dir: Path = None) -> pd.DataFrame:
    """Формирует полный датасет для одной компании"""
    company_name = COMPANIES.get(ticker, ticker)

    print(f"\n{'=' * 70}")
    print(f"📊 ФОРМИРОВАНИЕ ДАТАСЕТА: {ticker} ({company_name})")
    print(f"{'=' * 70}")

    # 1. Цены
    prices = load_prices(ticker)
    if len(prices) == 0:
        print(f"❌ Нет цен для {ticker}")
        return pd.DataFrame()

    # 2. Индексы
    print("   📈 Загрузка индексов MOEX...")
    indices = load_indices()
    if len(indices) > 0:
        print(f"      ✅ {len(indices)} записей")

    # 3. Сырьё
    print("   🛢️ Загрузка нефти и газа...")
    commodities = load_commodities()
    if len(commodities) > 0:
        print(f"      ✅ {len(commodities)} записей")

    # 4. Ставка ЦБ
    cbr = load_cbr_key_rate()

    # 5. Курс USD
    usd = load_usd_rate()

    # 6. Фундаментальные из БД
    fundamental = load_fundamental_from_db(ticker)

    # 7. Комментарии
    print("   💬 Загрузка комментариев SmartLab...")
    comments = load_comments(ticker)

    # 8. Заголовки Lenta
    print("   📰 Загрузка заголовков Lenta...")
    lenta = load_lenta()
    if len(lenta) > 0:
        print(f"      ✅ {len(lenta)} дней")

    # ========== ОБЪЕДИНЕНИЕ ==========
    print("\n   🔗 Объединение всех данных...")

    df = prices.copy()

    if len(indices) > 0:
        df = df.merge(indices, on='date', how='left')
    if len(commodities) > 0:
        df = df.merge(commodities, on='date', how='left')
    if len(cbr) > 0:
        df = df.merge(cbr, on='date', how='left')
    if len(usd) > 0:
        df = df.merge(usd, on='date', how='left')
    if len(comments) > 0:
        df = df.merge(comments, on='date', how='left')
    if len(lenta) > 0:
        df = df.merge(lenta, on='date', how='left')
    if len(fundamental) > 0:
        df['year'] = df['date'].dt.year
        df = df.merge(fundamental, on='year', how='left')
        df = df.drop(columns=['year'])

    # ========== ЗАПОЛНЕНИЕ ПРОПУСКОВ ==========
    print("   🔧 Заполнение пропусков...")

    for col in ['price', 'volume', 'open', 'high', 'low']:
        if col in df.columns:
            df[col] = df[col].ffill()
    if 'volume' in df.columns:
        df['volume'] = df['volume'].fillna(0)

    for col in list(indices.columns) + ['oil_brent', 'gas_henry_hub', 'cbr_key_rate', 'usd_rate']:
        if col != 'date' and col in df.columns:
            df[col] = df[col].ffill()

    for col in df.columns:
        if col.startswith('comments_') or col.startswith('lenta_'):
            df[col] = df[col].fillna(0)

    for col in ['bvps_rub', 'ncav_rub', 'graham_number_rub', 'eps',
                'roe', 'roa', 'net_margin', 'debt_to_equity',
                'revenue_bln', 'earnings_bln', 'ebitda_bln']:
        if col in df.columns:
            df[col] = df[col].ffill().fillna(0)

    # ========== ПРОИЗВОДНЫЕ ПРИЗНАКИ ==========
    print("   🔧 Добавление производных признаков...")

    df = df.dropna(subset=['price'])
    df = df[df['price'] > 0]
    df = df.sort_values('date').reset_index(drop=True)

    for lag in [1, 2, 3, 5, 10, 20, 30]:
        df[f'price_lag_{lag}'] = df['price'].shift(lag)

    for window in [5, 10, 20, 50]:
        if len(df) >= window:
            df[f'price_ma_{window}'] = df['price'].rolling(window, min_periods=1).mean()

    df['return_today'] = df['price'].pct_change()
    df['volatility_5d'] = df['return_today'].rolling(5, min_periods=1).std()
    df['volatility_20d'] = df['return_today'].rolling(20, min_periods=1).std()

    df['return_next_day'] = df['price'].shift(-1) / df['price'] - 1
    df['direction_next_day'] = (df['return_next_day'] > 0).astype(int)

    if all(c in df.columns for c in ['high', 'low']):
        df['price_range'] = df['high'] - df['low']
        df['price_range_pct'] = df['price_range'] / df['low'].replace(0, np.nan) * 100

    if 'volume' in df.columns:
        df['volume_ma5'] = df['volume'].rolling(5, min_periods=1).mean()
        df['volume_change'] = df['volume'].pct_change()

    if 'comments_positive' in df.columns and 'comments_negative' in df.columns:
        df['sentiment_ratio'] = (df['comments_positive'] + 1) / (df['comments_negative'] + 1)

    df['ticker'] = ticker
    df['company'] = company_name

    df = df.dropna(subset=['return_next_day'])

    fill_zero = ['return_today', 'volatility_5d', 'volatility_20d',
                 'volume_change', 'price_range', 'price_range_pct', 'sentiment_ratio']
    for col in fill_zero:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    for col in df.columns:
        if col.startswith('price_lag_') or col.startswith('price_ma_'):
            df[col] = df[col].fillna(df['price'])

    df = df.reset_index(drop=True)

    # ========== СОХРАНЕНИЕ ==========
    if output_dir is None:
        output_dir = PROCESSED_DATA_DIR / f"{ticker}_dataset"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{ticker}_complete_dataset.csv"
    df.to_csv(output_file, index=False, encoding='utf-8')

    # ========== ИТОГИ ==========
    print(f"\n{'=' * 70}")
    print(f"✅ ДАТАСЕТ ДЛЯ {ticker} СОЗДАН")
    print(f"{'=' * 70}")
    print(f"   📁 Файл: {output_file}")
    print(f"   📊 Записей: {len(df)}")
    print(f"   📋 Признаков: {len(df.columns)}")
    print(f"   📅 Период: {df['date'].min().date()} - {df['date'].max().date()}")
    print(f"   💰 Цена: {df['price'].min():.2f} - {df['price'].max():.2f} руб")

    # Статистика
    print(f"\n   📊 СТАТИСТИКА:")
    checks = {
        'price': ('mean', 'средняя'),
        'comments_total': ('sum', 'всего'),
        'comments_positive': ('sum', 'позитив'),
        'comments_negative': ('sum', 'негатив'),
        'lenta_total': ('sum', 'Lenta всего'),
        'lenta_war': ('sum', 'Lenta война'),
        'bvps_rub': ('mean', 'BVPS средний'),
    }
    for col, (method, label) in checks.items():
        if col in df.columns and df[col].notna().any():
            val = getattr(df[col], method)()
            print(f"      {label}: {val:,.1f}")

    return df


def main():
    parser = argparse.ArgumentParser(description='Сборка датасета для компании')
    parser.add_argument('--ticker', type=str, default='GAZP',
                        choices=['GAZP', 'SBER', 'LKOH', 'NVTK', 'VTBR'],
                        help='Тикер компании')
    parser.add_argument('--all', action='store_true',
                        help='Собрать датасеты для всех 5 компаний')

    args = parser.parse_args()

    if args.all:
        print("\n" + "=" * 70)
        print("🚀 СБОРКА ДАТАСЕТОВ ДЛЯ ВСЕХ 5 КОМПАНИЙ")
        print("=" * 70)
        for ticker in COMPANIES:
            try:
                build_dataset(ticker)
            except Exception as e:
                print(f"\n❌ Ошибка при сборке {ticker}: {e}")
                import traceback
                traceback.print_exc()
    else:
        build_dataset(args.ticker)

    print("\n" + "=" * 70)
    print("✅ ГОТОВО!")
    print("=" * 70)


if __name__ == "__main__":
    main()