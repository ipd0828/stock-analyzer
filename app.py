#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# app.py
"""
Streamlit-приложение для анализа акций.
"""

import os

os.environ['PYTHONUTF8'] = '1'
os.environ['LANG'] = 'ru_RU.UTF-8'
os.environ['LC_ALL'] = 'ru_RU.UTF-8'
os.environ['CUDA_VISIBLE_DEVICES'] = ''

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import sys
from datetime import datetime, timedelta
import time
import warnings
import json
import re
import requests
import feedparser

# ML
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.metrics.pairwise import cosine_similarity

# API MOEX
import apimoex

# PostgreSQL
import psycopg2
from psycopg2.extras import RealDictCursor

# Embeddings
from sentence_transformers import SentenceTransformer

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Анализатор акций", page_icon="📊", layout="wide")

# ========== КОНФИГУРАЦИЯ ==========

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "database": os.environ.get("DB_NAME", "investment_db"),
    "user": os.environ.get("DB_USER", "investor_nick"),
    "password": os.environ.get("DB_PASSWORD", "")
}

COMPANIES = {
    'GAZP': 'Газпром', 'SBER': 'Сбер', 'LKOH': 'Лукойл',
    'NVTK': 'Новатэк', 'VTBR': 'ВТБ'
}

SHARES = {
    'GAZP': 23645, 'SBER': 21587, 'LKOH': 851,
    'NVTK': 4500, 'VTBR': 790000
}

CATEGORIES = ['WAR', 'SANCTIONS', 'OIL_GAS', 'MARKET', 'POLITICAL', 'CATASTROPHE', 'INCIDENT', 'OTHER']
SENTIMENTS = ['POSITIVE', 'NEGATIVE', 'NEUTRAL']
MODEL_NAME = 'intfloat/multilingual-e5-large'
DAY_VECTORS_FILE = Path("data/features/day_embeddings/day_vectors.json")
LENTA_RSS = "https://lenta.ru/rss/news"

plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False


# ========== ФУНКЦИИ ЗАГРУЗКИ ==========

@st.cache_data(ttl=300)
def fetch_moex_data(ticker: str, days: int = 365):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    try:
        with requests.Session() as session:
            data = apimoex.get_board_candles(session, security=ticker, interval=24,
                                             start=start_date.strftime('%Y-%m-%d'),
                                             end=end_date.strftime('%Y-%m-%d'))
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['begin'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df[['date', 'open', 'high', 'low', 'close', 'volume']].dropna()
        return df.sort_values('date').reset_index(drop=True)
    except Exception as e:
        st.error(f"Ошибка MOEX: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=600)
def load_fundamental_from_db(ticker: str) -> pd.DataFrame:
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        current_year = datetime.now().year
        query = """
        SELECT fr.year, fr.month, fr.period, fr.report_type,
               fr.revenue, fr.earnings, fr.ebitda,
               fr.total_assets, fr.equity_stock_holders,
               fr.total_debt, fr.current_assets, fr.current_liabilities,
               fr.eps, fr.cfo, fr.fcf, fr.capex
        FROM financial_reports fr
        JOIN companies c ON c.id = fr.company_id
        WHERE c.code = %s AND c.exchange = 'MOEX' AND fr.year >= %s
        ORDER BY fr.year, fr.month
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (ticker, current_year - 5))
            rows = cur.fetchall()
        conn.close()
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df = df[df['report_type'].str.contains('МСФО', na=False)].copy()
        if len(df) == 0:
            return pd.DataFrame()

        df['period_clean'] = df['period'].str.strip().str.upper()
        yearly_periods = ['Y', 'FY', '12M', 'ANNUAL']
        df['is_yearly'] = df['period_clean'].isin(yearly_periods)

        df_yearly = df[df['is_yearly']].copy()
        has_current_year = (df_yearly['year'] == current_year).any()
        if not has_current_year:
            df_quarterly = df[~df['is_yearly']].copy()
            latest_q = df_quarterly[df_quarterly['year'] == current_year]
            if len(latest_q) > 0:
                latest_q = latest_q.sort_values('month', ascending=False).iloc[:1]
                df_yearly = pd.concat([df_yearly, latest_q], ignore_index=True)

        df = df_yearly.sort_values('year').drop_duplicates(subset=['year'], keep='last')

        num_cols = ['revenue', 'earnings', 'ebitda', 'total_assets', 'equity_stock_holders',
                    'total_debt', 'current_assets', 'current_liabilities', 'eps', 'cfo', 'fcf', 'capex']
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        for col in ['revenue', 'earnings', 'ebitda', 'total_assets', 'equity_stock_holders',
                    'total_debt', 'current_assets', 'current_liabilities', 'cfo', 'fcf', 'capex']:
            if col in df.columns:
                df[col] = df[col] / 1000

        shares = SHARES.get(ticker, 1000)
        df['bvps_rub'] = df['equity_stock_holders'] * 1000 / shares
        df['ncav_rub'] = (df['current_assets'] - df['total_debt']) * 1000 / shares
        df['roe'] = np.where(df['equity_stock_holders'].fillna(0) != 0,
                             df['earnings'] / df['equity_stock_holders'] * 100, np.nan)
        df['roa'] = np.where(df['total_assets'].fillna(0) != 0,
                             df['earnings'] / df['total_assets'] * 100, np.nan)
        df['net_margin'] = np.where(df['revenue'].fillna(0) != 0,
                                    df['earnings'] / df['revenue'] * 100, np.nan)
        df['debt_to_equity'] = np.where(df['equity_stock_holders'].fillna(0) != 0,
                                        df['total_debt'] / df['equity_stock_holders'], np.nan)

        mask = (df['eps'].fillna(0) > 0) & (df['bvps_rub'].fillna(0) > 0)
        df['graham_number_rub'] = np.nan
        if mask.any():
            df.loc[mask, 'graham_number_rub'] = np.sqrt(22.5 * df.loc[mask, 'eps'] * df.loc[mask, 'bvps_rub'])

        for col in ['revenue', 'earnings', 'ebitda', 'total_assets', 'total_debt']:
            if col in df.columns:
                df[f'{col}_bln'] = df[col]

        return df
    except Exception as e:
        st.error(f"Ошибка БД: {e}")
        return pd.DataFrame()


@st.cache_resource
def load_embedding_model():
    return SentenceTransformer(MODEL_NAME, device='cpu')


def classify_headline(title: str) -> dict:
    resp = requests.post(
        "http://127.0.0.1:8001/v1/chat/completions",
        json={
            "model": "local-model",
            "messages": [
                {"role": "system",
                 "content": "Return JSON: {\"sentiment\":\"POSITIVE|NEGATIVE|NEUTRAL\", \"category\":\"WAR|SANCTIONS|OIL_GAS|MARKET|POLITICAL|CATASTROPHE|INCIDENT|OTHER\"}"},
                {"role": "user", "content": f'Headline: "{title[:200]}"'}
            ],
            "temperature": 0, "max_tokens": 80
        },
        timeout=30
    )
    if resp.status_code == 200:
        answer = resp.json()['choices'][0]['message']['content'].strip()
        if answer.startswith('```'):
            answer = answer.replace('```json', '').replace('```', '')
        try:
            return json.loads(answer)
        except:
            pass
    return {"sentiment": "NEUTRAL", "category": "OTHER"}


def load_historical_prices(ticker: str) -> pd.DataFrame:
    prices_file = Path("data/raw/moex/stocks.csv")
    if not prices_file.exists():
        return pd.DataFrame()
    df = pd.read_csv(prices_file)
    df['date'] = pd.to_datetime(df['date'])
    df = df[df['ticker'] == ticker].copy()
    if 'close' in df.columns:
        df = df.rename(columns={'close': 'price'})
    df['year'] = df['date'].dt.year
    yearly = df.groupby('year')['price'].mean().reset_index()
    yearly.columns = ['year', 'avg_price']
    return yearly


# ========== ML ==========

def train_price_model(df: pd.DataFrame):
    if len(df) < 30:
        return None, None, None, None, None, None, None
    df = df.copy()
    for lag in [1, 2, 3, 5, 10]:
        df[f'close_lag_{lag}'] = df['close'].shift(lag)
        df[f'open_lag_{lag}'] = df['open'].shift(lag)
    df['returns'] = df['close'].pct_change().abs()
    for lag in [1, 2, 3, 5]:
        df[f'vol_lag_{lag}'] = df['returns'].shift(lag)
    df['vol_5d'] = df['returns'].rolling(5).std()
    df['vol_10d'] = df['returns'].rolling(10).std()
    df['hl_ratio'] = (df['high'] - df['low']) / df['close']
    df['volume_ma_5'] = df['volume'].rolling(5).mean()
    df['volume_change'] = df['volume'].pct_change()
    model_df = df.dropna()
    if len(model_df) < 20:
        return None, None, None, None, None, None, None

    close_features = [c for c in model_df.columns if c.startswith('close_lag')] + ['hl_ratio', 'volume_ma_5']
    open_features = [c for c in model_df.columns if c.startswith('open_lag')] + ['hl_ratio', 'volume_ma_5']
    vol_features = [c for c in model_df.columns if c.startswith('vol_lag') or c.startswith('vol_')] + ['hl_ratio',
                                                                                                       'volume_change']

    split = int(len(model_df) * 0.85)

    Xc_train, Xc_test = model_df[close_features].values[:split], model_df[close_features].values[split:]
    yc_train, yc_test = model_df['close'].values[:split], model_df['close'].values[split:]
    sc = StandardScaler()
    model_close = Ridge(alpha=1.0).fit(sc.fit_transform(Xc_train), yc_train)
    mae_c, r2_c = mean_absolute_error(yc_test, model_close.predict(sc.transform(Xc_test))), r2_score(yc_test,
                                                                                                     model_close.predict(
                                                                                                         sc.transform(
                                                                                                             Xc_test)))

    Xo_train, Xo_test = model_df[open_features].values[:split], model_df[open_features].values[split:]
    yo_train, yo_test = model_df['open'].values[:split], model_df['open'].values[split:]
    so = StandardScaler()
    model_open = Ridge(alpha=1.0).fit(so.fit_transform(Xo_train), yo_train)
    mae_o, r2_o = mean_absolute_error(yo_test, model_open.predict(so.transform(Xo_test))), r2_score(yo_test,
                                                                                                    model_open.predict(
                                                                                                        so.transform(
                                                                                                            Xo_test)))

    Xv_train, Xv_test = model_df[vol_features].values[:split], model_df[vol_features].values[split:]
    yv_train, yv_test = model_df['returns'].values[:split], model_df['returns'].values[split:]
    sv = StandardScaler()
    vol_model = Ridge(alpha=0.5).fit(sv.fit_transform(Xv_train), yv_train)
    mae_v = mean_absolute_error(yv_test, np.abs(vol_model.predict(sv.transform(Xv_test))))

    metrics = {'mae_close': mae_c, 'r2_close': r2_c, 'mae_open': mae_o, 'r2_open': r2_o,
               'mae_vol': mae_v, 'train_size': split, 'test_size': len(model_df) - split}
    return model_close, model_open, vol_model, sc, so, sv, metrics


def predict_next_day(df, mc, mo, vm, sc, so, sv):
    if mc is None:
        return None
    last = df.dropna().iloc[-1:]
    close_f = [c for c in df.columns if c.startswith('close_lag')] + ['hl_ratio', 'volume_ma_5']
    open_f = [c for c in df.columns if c.startswith('open_lag')] + ['hl_ratio', 'volume_ma_5']
    vol_f = [c for c in df.columns if c.startswith('vol_lag') or c.startswith('vol_')] + ['hl_ratio', 'volume_change']

    pc = mc.predict(sc.transform(last[[c for c in close_f if c in last.columns]].values))[0]
    po = mo.predict(so.transform(last[[c for c in open_f if c in last.columns]].values))[0]
    pv = abs(vm.predict(sv.transform(last[[c for c in vol_f if c in last.columns]].values))[0]) * 100

    lc, lo = last['close'].values[0], last['open'].values[0]
    return {
        'last_close': lc, 'last_open': lo,
        'predicted_close': pc, 'predicted_open': po,
        'change_close_pct': (pc - lc) / lc * 100,
        'change_open_pct': (po - lo) / lo * 100,
        'direction_close': '📈 РОСТ' if pc > lc else '📉 ПАДЕНИЕ',
        'direction_open': '📈 РОСТ' if po > lo else '📉 ПАДЕНИЕ',
        'volatility': pv
    }


# ========== ГРАФИК ==========

def plot_fundamental_chart(fund_df, ticker, current_price, hist_prices=None):
    if len(fund_df) == 0:
        return None
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    years = fund_df['year'].values.astype(int)
    bvps = fund_df['bvps_rub'].values
    width = 0.35
    x = np.arange(len(years))

    yearly_prices = []
    for year in years:
        if hist_prices is not None and len(hist_prices) > 0:
            year_row = hist_prices[hist_prices['year'] == year]
            if len(year_row) > 0:
                yearly_prices.append(year_row['avg_price'].values[0])
            else:
                yearly_prices.append(current_price)
        else:
            yearly_prices.append(current_price)
    yearly_prices = np.array(yearly_prices)

    axes[0, 0].bar(x - width / 2, yearly_prices, width, label='Средняя цена за год', color='steelblue', alpha=0.8)
    axes[0, 0].bar(x + width / 2, bvps, width, label='BVPS', color='coral', alpha=0.8)
    axes[0, 0].set_xticks(x)
    axes[0, 0].set_xticklabels(years)
    axes[0, 0].set_title('Цена vs Балансовая стоимость')
    axes[0, 0].legend()
    axes[0, 0].grid(True, alpha=0.3, axis='y')
    for i, (price, bv) in enumerate(zip(yearly_prices, bvps)):
        if not np.isnan(bv):
            axes[0, 0].text(i, bv + 15, f'{bv:.0f}', ha='center', fontsize=7, color='coral')
            axes[0, 0].text(i, price + 15, f'{price:.0f}', ha='center', fontsize=7, color='steelblue')

    valid = bvps > 0
    discount = np.where(valid, (1 - yearly_prices / bvps) * 100, np.nan)
    colors = ['red' if not np.isnan(d) and d > 0 else 'green' if not np.isnan(d) else 'gray' for d in discount]
    axes[0, 1].bar(x, discount, color=colors, alpha=0.7)
    axes[0, 1].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    axes[0, 1].set_xticks(x)
    axes[0, 1].set_xticklabels(years)
    axes[0, 1].set_title('Дисконт к балансовой стоимости')
    axes[0, 1].grid(True, alpha=0.3, axis='y')
    for i, d in enumerate(discount):
        if not np.isnan(d):
            offset = 1.5 if d > 0 else -3
            axes[0, 1].text(i, d + offset, f'{d:.1f}%', ha='center', fontsize=8, fontweight='bold')

    graham_mask = fund_df['graham_number_rub'].notna()
    if graham_mask.any():
        g_years = years[graham_mask]
        g_prices = yearly_prices[graham_mask]
        g_values = fund_df['graham_number_rub'].values[graham_mask]
        xg = np.arange(len(g_years))
        axes[1, 0].bar(xg - width / 2, g_prices, width, label='Средняя цена', color='steelblue', alpha=0.8)
        axes[1, 0].bar(xg + width / 2, g_values, width, label='Graham Number', color='green', alpha=0.8)
        axes[1, 0].set_xticks(xg)
        axes[1, 0].set_xticklabels(g_years)
        axes[1, 0].set_title('Цена vs Graham Number')
        axes[1, 0].legend()
        axes[1, 0].grid(True, alpha=0.3, axis='y')
    else:
        axes[1, 0].text(0.5, 0.5, 'Нет данных\n(EPS ≤ 0 или BVPS ≤ 0)', transform=axes[1, 0].transAxes, ha='center',
                        fontsize=12)
        axes[1, 0].set_title('Graham Number = √(22.5 × EPS × BVPS)')

    if 'roe' in fund_df.columns and 'net_margin' in fund_df.columns:
        axes[1, 1].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        axes[1, 1].plot(years, fund_df['roe'].values, 'o-', label='ROE, %', color='blue', linewidth=2, markersize=6)
        axes[1, 1].plot(years, fund_df['net_margin'].values, 's-', label='Маржа, %', color='orange', linewidth=2,
                        markersize=6)
        for i, (y, roe, margin) in enumerate(zip(years, fund_df['roe'].values, fund_df['net_margin'].values)):
            if not np.isnan(roe):
                axes[1, 1].annotate(f'{roe:.1f}', (y, roe), textcoords="offset points", xytext=(0, 10), ha='center',
                                    fontsize=7, color='blue')
            if not np.isnan(margin):
                axes[1, 1].annotate(f'{margin:.1f}', (y, margin), textcoords="offset points", xytext=(0, -12),
                                    ha='center', fontsize=7, color='orange')
        axes[1, 1].set_xlabel('Год')
        axes[1, 1].set_ylabel('Проценты')
        axes[1, 1].set_title('Рентабельность')
        axes[1, 1].legend()
        axes[1, 1].grid(True, alpha=0.3)

    plt.suptitle(f'{COMPANIES.get(ticker, ticker)}: Фундаментальный анализ', fontsize=14, fontweight='bold')
    plt.tight_layout()
    return fig


# ========== ИНТЕРФЕЙС ==========

def main():
    st.title("📊 Анализатор акций — Фундаментальный анализ и ML-прогноз")
    st.markdown("---")

    with st.sidebar:
        st.header("⚙️ Настройки")
        ticker = st.selectbox("Тикер", list(COMPANIES.keys()), format_func=lambda x: f"{x} — {COMPANIES[x]}")
        st.markdown("---")

        load_btn = st.button("🔄 Загрузить данные MOEX и БД", type="primary", use_container_width=True)
        st.markdown("---")

        st.markdown("### 📰 Новости SmartLab")
        if st.button("📥 Собрать новости за 7 дней", use_container_width=True):
            with st.spinner(f"Сбор новостей {ticker}..."):
                from scripts.collect_recent_news import collect_recent_news
                news_list = collect_recent_news(ticker, days=7)
                st.session_state['news_list'] = news_list
                st.session_state['news_ticker'] = ticker
                st.success(f"✅ Собрано {len(news_list)} новостей")
                st.rerun()

        if st.button("🧠 LLM-анализ новостей", use_container_width=True, disabled='news_list' not in st.session_state):
            with st.spinner("Qwen анализирует..."):
                news_list = st.session_state['news_list']
                company_name = COMPANIES.get(ticker, ticker)
                results = []
                progress_bar = st.progress(0)

                for i, news in enumerate(news_list):
                    if not news.get('content') or len(news['content']) < 50:
                        continue

                    prompt = f"""Ты — финансовый аналитик. Оцени влияние новости на цену акций {company_name} ({ticker}).

НОВОСТЬ:
Заголовок: {news['title']}
Текст: {news['content'][:4000]}

Верни ТОЛЬКО JSON:
{{"sentiment":"POSITIVE","price_impact_percent":1.5,"confidence":0.8,"reasoning":"Рост прибыли на 16% позитивен для акций"}}"""

                    try:
                        resp = requests.post(
                            "http://127.0.0.1:8001/v1/chat/completions",
                            json={
                                "model": "local-model",
                                "messages": [
                                    {"role": "system", "content": "Ты — финансовый аналитик. Отвечай только JSON."},
                                    {"role": "user", "content": prompt}
                                ],
                                "temperature": 0, "max_tokens": 300
                            }, timeout=120
                        )
                        if resp.status_code == 200:
                            answer = resp.json()['choices'][0]['message']['content'].strip()
                            brace_idx = answer.find('{')
                            if brace_idx > 0:
                                answer = answer[brace_idx:]
                            last_brace = answer.rfind('}')
                            if last_brace > 0:
                                answer = answer[:last_brace + 1]
                            answer = answer.replace('```json', '').replace('```', '').strip()
                            try:
                                analysis = json.loads(answer)
                            except:
                                analysis = {"sentiment": "NEUTRAL", "price_impact_percent": 0, "confidence": 0.5,
                                            "reasoning": answer[:100]}
                            analysis['title'] = news['title']
                            analysis['date'] = news['date']
                            results.append(analysis)
                    except:
                        pass
                    progress_bar.progress((i + 1) / len(news_list))
                    time.sleep(0.3)

                st.session_state['llm_results'] = results
                st.success(f"✅ Проанализировано {len(results)} новостей")
                st.rerun()

        st.markdown("---")
        st.markdown("### 🔍 Похожие дни")
        if st.button("🔍 Найти похожие дни", use_container_width=True):
            with st.spinner("Анализ информационного фона..."):
                model = load_embedding_model()
                feed = feedparser.parse(LENTA_RSS)
                headlines = []
                for entry in feed.entries[:50]:
                    result = classify_headline(entry.title)
                    headlines.append({
                        'title': entry.title,
                        'sentiment': result.get('sentiment', 'NEUTRAL'),
                        'category': result.get('category', 'OTHER')
                    })

                total = len(headlines)
                cat_f = [(sum(1 for h in headlines if h['category'] == c)) / total for c in CATEGORIES]
                sent_f = [(sum(1 for h in headlines if h['sentiment'] == s)) / total for s in SENTIMENTS]
                day_text = " | ".join([h['title'] for h in headlines])
                emb = model.encode(day_text, normalize_embeddings=True)
                today_vec = np.concatenate([cat_f, sent_f, emb])

                if not DAY_VECTORS_FILE.exists():
                    st.warning("Сначала запустите scripts/build_day_embeddings.py")
                else:
                    with open(DAY_VECTORS_FILE) as f:
                        history = json.load(f)
                    dates = list(history.keys())
                    matrix = np.array([history[d]['vector'] for d in dates])
                    sims = cosine_similarity(today_vec.reshape(1, -1), matrix)[0]
                    top = np.argsort(sims)[-10:][::-1]

                    # Загружаем полную историю цен ОДИН раз
                    prices_full = pd.DataFrame()
                    prices_file = Path("data/raw/moex/stocks.csv")
                    if prices_file.exists():
                        prices_full = pd.read_csv(prices_file)
                        prices_full['date'] = pd.to_datetime(prices_full['date'])

                    if 'prices' in st.session_state and len(st.session_state['prices']) > 0:
                        fresh = st.session_state['prices'].copy()
                        if 'close' not in fresh.columns and 'price' in fresh.columns:
                            fresh = fresh.rename(columns={'price': 'close'})
                        if 'ticker' not in fresh.columns:
                            fresh['ticker'] = ticker
                        prices_full = pd.concat([prices_full, fresh], ignore_index=True)
                        prices_full = prices_full.drop_duplicates(subset=['date', 'ticker'], keep='last')

                    ticker_prices = prices_full[prices_full['ticker'] == ticker].copy()
                    ticker_prices['close'] = pd.to_numeric(ticker_prices['close'], errors='coerce')
                    ticker_prices = ticker_prices.sort_values('date').reset_index(drop=True)

                    similar = []
                    for idx in top:
                        d = dates[idx]
                        info = history[d]
                        price_info = ""

                        if len(ticker_prices) > 0:
                            day_data = ticker_prices[ticker_prices['date'].dt.date == pd.to_datetime(d).date()]
                            if len(day_data) > 0:
                                close_price = day_data['close'].values[0]
                                day_idx = day_data.index[0]
                                if day_idx + 1 < len(ticker_prices):
                                    next_close = ticker_prices.iloc[day_idx + 1]['close']
                                    change = (next_close - close_price) / close_price * 100
                                    price_info = f"{close_price:.1f} ₽ → {change:+.1f}%"
                                else:
                                    price_info = f"{close_price:.1f} ₽"

                        similar.append({
                            'date': d,
                            'similarity': float(sims[idx]),
                            'war': info['categories'].get('WAR', 0),
                            'neg': info['sentiments'].get('NEGATIVE', 0),
                            'total': info.get('total', 0),
                            'price_info': price_info
                        })

                    st.session_state['similar_days'] = similar
                    st.success(f"✅ Найдено {len(similar)} похожих дней")
                    st.rerun()

        st.markdown("---")
        st.info("**Источники:** MOEX API, PostgreSQL, SmartLab, Lenta.ru")

    # ========== ОСНОВНАЯ ОБЛАСТЬ ==========

    if load_btn:
        with st.spinner(f"Загрузка данных для {ticker}..."):
            prices = fetch_moex_data(ticker, days=365)
            fundamental = load_fundamental_from_db(ticker)
            st.session_state['prices'] = prices
            st.session_state['fundamental'] = fundamental
            st.session_state['data_loaded'] = True
            st.session_state['data_ticker'] = ticker
            st.rerun()

    if st.session_state.get('data_loaded') and st.session_state.get('data_ticker') == ticker:
        prices = st.session_state['prices']
        fundamental = st.session_state['fundamental']

        if len(prices) == 0:
            st.error("❌ Не удалось загрузить данные MOEX")
            return

        last = prices.iloc[-1]
        prev = prices.iloc[-2] if len(prices) > 1 else last

        st.markdown("### 📈 Текущие показатели")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Закрытие", f"{last['close']:.2f} ₽", f"{(last['close'] - prev['close']):+.2f} ₽")
        col2.metric("Объём", f"{last['volume']:,.0f}", f"{(last['volume'] - prev['volume']):+,.0f}")
        col3.metric("Макс.", f"{last['high']:.2f} ₽")
        col4.metric("Мин.", f"{last['low']:.2f} ₽")
        ch20 = (last['close'] - prices.iloc[-21]['close']) / prices.iloc[-21]['close'] * 100 if len(prices) > 20 else 0
        col5.metric("20 дней", f"{ch20:+.2f}%")
        st.markdown("---")

        st.markdown("### 🤖 ML-прогноз на следующий день (Ridge)")
        mc, mo, vm, sc, so, sv, metrics = train_price_model(prices.copy())

        if mc is not None:
            pc = prices.copy()
            for lag in [1, 2, 3, 5, 10]:
                pc[f'close_lag_{lag}'] = pc['close'].shift(lag)
                pc[f'open_lag_{lag}'] = pc['open'].shift(lag)
            pc['returns'] = pc['close'].pct_change().abs()
            for lag in [1, 2, 3, 5]:
                pc[f'vol_lag_{lag}'] = pc['returns'].shift(lag)
            pc['vol_5d'] = pc['returns'].rolling(5).std()
            pc['vol_10d'] = pc['returns'].rolling(10).std()
            pc['hl_ratio'] = (pc['high'] - pc['low']) / pc['close']
            pc['volume_ma_5'] = pc['volume'].rolling(5).mean()
            pc['volume_change'] = pc['volume'].pct_change()

            pred = predict_next_day(pc, mc, mo, vm, sc, so, sv)

            if pred:
                c1, c2 = st.columns(2)
                c1.metric("Цена открытия", f"{pred['predicted_open']:.2f} ₽", f"{pred['change_open_pct']:+.2f}%")
                c1.caption(f"Вчера: {pred['last_open']:.2f} ₽ | {pred['direction_open']}")
                c2.metric("Цена закрытия", f"{pred['predicted_close']:.2f} ₽", f"{pred['change_close_pct']:+.2f}%")
                c2.caption(f"Вчера: {pred['last_close']:.2f} ₽ | {pred['direction_close']}")
                st.markdown("#### Волатильность")
                st.metric("Дневная", f"±{pred['volatility']:.2f}%")
                st.caption(
                    f"MAE Open: {metrics['mae_open']:.4f} | MAE Close: {metrics['mae_close']:.4f} | Обучение: {metrics['train_size']} дн.")

        st.markdown("---")

        st.markdown("### 💎 Фундаментальные показатели (МСФО)")
        if len(fundamental) > 0:
            display = {
                'year': 'Год', 'revenue_bln': 'Выручка (млрд ₽)', 'earnings_bln': 'Прибыль (млрд ₽)',
                'ebitda_bln': 'EBITDA (млрд ₽)', 'eps': 'EPS (₽)', 'bvps_rub': 'BVPS (₽)',
                'roe': 'ROE (%)', 'roa': 'ROA (%)', 'net_margin': 'Маржа (%)',
                'debt_to_equity': 'Долг/Капитал', 'graham_number_rub': 'Graham Number (₽)'
            }
            ex = {k: v for k, v in display.items() if k in fundamental.columns}
            td = fundamental[list(ex.keys())].rename(columns=ex).set_index('Год')
            st.dataframe(td.style.format({
                'Выручка (млрд ₽)': '{:,.0f}', 'Прибыль (млрд ₽)': '{:+,.0f}',
                'EBITDA (млрд ₽)': '{:,.0f}', 'EPS (₽)': '{:+.2f}', 'BVPS (₽)': '{:,.2f}',
                'ROE (%)': '{:+.1f}', 'ROA (%)': '{:+.1f}', 'Маржа (%)': '{:+.1f}',
                'Долг/Капитал': '{:.2f}', 'Graham Number (₽)': '{:,.2f}'
            }).background_gradient(cmap='RdYlGn', subset=['ROE (%)', 'Маржа (%)']), use_container_width=True)

            st.markdown("#### 📊 График")
            hist_prices = load_historical_prices(ticker)
            fig = plot_fundamental_chart(fundamental, ticker, float(last['close']), hist_prices)
            if fig:
                st.pyplot(fig)
        else:
            st.warning("⚠️ Нет фундаментальных данных")

        st.markdown("---")
        st.markdown("### 📈 Динамика цены")
        fig, ax = plt.subplots(figsize=(14, 5))
        ax.plot(prices['date'], prices['close'], 'b-', linewidth=1.5, alpha=0.8, label='Закрытие')
        ax.fill_between(prices['date'], prices['low'], prices['high'], alpha=0.3, color='blue')
        if len(prices) >= 20:
            ax.plot(prices['date'], prices['close'].rolling(20).mean(), 'orange', linewidth=1.5, label='MA 20')
        ax.set_xlabel('Дата')
        ax.set_ylabel('Цена, ₽')
        ax.set_title(f'{COMPANIES.get(ticker, ticker)} ({ticker})')
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        st.pyplot(fig)

    # ========== НОВОСТИ ==========
    if 'news_list' in st.session_state and st.session_state.get('news_ticker') == ticker:
        st.markdown("---")
        st.markdown(f"### 📰 Новости SmartLab ({len(st.session_state['news_list'])} шт.)")
        for news in st.session_state['news_list']:
            with st.expander(f"{news['date']} — {news['title'][:80]}", expanded=False):
                st.text(news.get('content', '')[:2000])

        if 'llm_results' in st.session_state:
            st.markdown("### 🧠 LLM-анализ влияния на цену")
            total = 0
            for r in st.session_state['llm_results']:
                total += r.get('price_impact_percent', 0)
                emoji = {'STRONG_POSITIVE': '🟢🟢', 'POSITIVE': '🟢', 'NEUTRAL': '⚪',
                         'NEGATIVE': '🔴', 'STRONG_NEGATIVE': '🔴🔴'}.get(r.get('sentiment'), '⚪')
                impact = r.get('price_impact_percent', 0)
                color = 'green' if impact > 0 else 'red' if impact < 0 else 'gray'
                st.markdown(f"**{emoji} {r.get('title', '')[:100]}**  \n"
                            f"Влияние: :{color}[{impact:+.1f}%] | Уверенность: {r.get('confidence', 0):.0%}  \n"
                            f"{r.get('reasoning', '')}")
                st.markdown("---")
            st.metric("Суммарное влияние", f"{total:+.1f}%")

    # ========== ПОХОЖИЕ ДНИ ==========
    if 'similar_days' in st.session_state:
        st.markdown("---")
        st.markdown("### 🔍 Похожие дни по информационному фону")
        st.caption("На основе cosine similarity векторов заголовков Lenta.ru")

        for i, day in enumerate(st.session_state['similar_days']):
            col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
            with col1:
                st.markdown(f"**{i + 1}. {day['date']}**")
            with col2:
                sim_color = 'green' if day['similarity'] > 0.92 else 'orange' if day['similarity'] > 0.88 else 'gray'
                st.markdown(f":{sim_color}[{day['similarity']:.3f}]")
            with col3:
                st.markdown(f"⚔️ {day['war']} | 😡 {day['neg']} | 📰 {day['total']}")
            with col4:
                if day['price_info']:
                    st.markdown(f"💰 {day['price_info']}")
                else:
                    st.markdown("—")
            st.progress(min(day['similarity'], 1.0))

    # Приветственный экран
    if not st.session_state.get(
            'data_loaded') and 'news_list' not in st.session_state and 'similar_days' not in st.session_state:
        st.info("👈 Нажмите **«Загрузить данные»** или **«Собрать новости»** в боковой панели")
        c1, c2 = st.columns(2)
        c1.markdown(
            "### 📋 Возможности:\n\n1. 📈 Котировки MOEX\n2. 🤖 ML-прогноз (Ridge)\n3. 💎 Фундаментальный анализ\n4. 📰 Новости SmartLab\n5. 🧠 LLM-анализ\n6. 🔍 Поиск похожих дней")
        c2.success(
            "### 🛠️ Технологии:\n\n- Ridge-регрессия\n- MOEX ISS API\n- PostgreSQL\n- Qwen 35B\n- multilingual-e5-large\n- Streamlit\n\n### Тикеры:\nGAZP, SBER, LKOH, NVTK, VTBR")


if __name__ == "__main__":
    main()