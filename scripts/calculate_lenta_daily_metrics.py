# scripts/calculate_lenta_daily_metrics.py

"""
Рассчитывает дневные метрики информационного фона из классифицированных заголовков
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys
from datetime import datetime

sys.path.append(str(Path(__file__).parent.parent))

INPUT_FILE = Path("data/features/lenta_classified/lenta_headers_classified.csv")
OUTPUT_FILE = Path("data/features/information_background/daily_metrics.csv")
OUTPUT_DIR = OUTPUT_FILE.parent
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Веса шоков
SHOCK_WEIGHTS = {
    'WAR': 1.0,
    'SANCTIONS': 0.9,
    'ECONOMIC_CRISIS': 0.8,
    'CATASTROPHE': 0.7,
    'POLITICAL': 0.6,
    'MARKET': 0.85,
    'INCIDENT': 0.2,
    'OTHER': 0.0
}


def calculate_daily_metrics():
    print("=" * 70)
    print("📊 РАСЧЁТ ДНЕВНЫХ МЕТРИК ИНФОРМАЦИОННОГО ФОНА")
    print("=" * 70)

    # Загружаем классифицированные заголовки
    df = pd.read_csv(INPUT_FILE)
    df['date'] = pd.to_datetime(df['date'])
    print(f"📚 Всего заголовков: {len(df)}")
    print(f"   Период: {df['date'].min().date()} - {df['date'].max().date()}")

    # Группируем по дням
    daily_metrics = []

    for date, group in df.groupby(df['date'].dt.date):
        total = len(group)

        # Тональность
        pos_count = (group['sentiment'] == 'POSITIVE').sum()
        neg_count = (group['sentiment'] == 'NEGATIVE').sum()
        pos_weighted = group[group['sentiment'] == 'POSITIVE']['intensity'].sum()
        neg_weighted = group[group['sentiment'] == 'NEGATIVE']['intensity'].sum()

        # Индекс тональности
        sentiment_index = (pos_weighted - neg_weighted) / max(total, 1)

        # N/P Ratio
        np_ratio = neg_count / max(pos_count, 1)

        # Экономическая релевантность
        economic = group[group['economic_relevance'] >= 5]
        economic_share = len(economic) / max(total, 1)
        economic_neg = (economic['sentiment'] == 'NEGATIVE').sum()
        economic_neg_share = economic_neg / max(len(economic), 1)

        # Информационный шум
        info_noise = 1 - economic_share

        # Шоки
        shocks = group[group['shock_type'] != 'OTHER']
        shock_count = len(shocks)
        shock_intensity = shocks['shock_intensity'].sum()

        # Детализация по типам шоков
        war_count = (group['shock_type'] == 'WAR').sum()
        sanctions_count = (group['shock_type'] == 'SANCTIONS').sum()
        crisis_count = (group['shock_type'] == 'ECONOMIC_CRISIS').sum()
        catastrophe_count = (group['shock_type'] == 'CATASTROPHE').sum()

        # Взвешенный индекс шока
        weighted_shock = 0
        for shock_type, weight in SHOCK_WEIGHTS.items():
            shock_group = group[group['shock_type'] == shock_type]
            weighted_shock += shock_group['shock_intensity'].sum() * weight
        weighted_shock_index = weighted_shock / max(total, 1)

        daily_metrics.append({
            'date': date,
            'total_headers': total,
            'economic_share': economic_share,
            'info_noise': info_noise,
            'sentiment_index': sentiment_index,
            'np_ratio': np_ratio,
            'positive_share': pos_count / max(total, 1),
            'negative_share': neg_count / max(total, 1),
            'avg_intensity': group['intensity'].mean(),
            'economic_neg_share': economic_neg_share,
            'shock_count': shock_count,
            'shock_share': shock_count / max(total, 1),
            'shock_intensity': shock_intensity / max(total, 1),
            'weighted_shock_index': weighted_shock_index,
            'war_count': war_count,
            'sanctions_count': sanctions_count,
            'crisis_count': crisis_count,
            'catastrophe_count': catastrophe_count
        })

    df_metrics = pd.DataFrame(daily_metrics)
    df_metrics = df_metrics.sort_values('date')

    # Сохраняем
    df_metrics.to_csv(OUTPUT_FILE, index=False, encoding='utf-8')

    print(f"\n✅ Сохранено: {OUTPUT_FILE}")
    print(f"   Всего дней: {len(df_metrics)}")
    print(f"   Период: {df_metrics['date'].min()} - {df_metrics['date'].max()}")

    # Статистика
    print(f"\n📊 СТАТИСТИКА:")
    print(f"   Средний индекс тональности: {df_metrics['sentiment_index'].mean():.3f}")
    print(f"   Средний N/P Ratio: {df_metrics['np_ratio'].mean():.2f}")
    print(f"   Средний индекс шока: {df_metrics['weighted_shock_index'].mean():.2f}")

    return df_metrics


if __name__ == "__main__":
    calculate_daily_metrics()