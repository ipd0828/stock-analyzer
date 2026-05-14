#!/usr/bin/env python3
# scripts/daily_update.py
"""
Ежедневное обновление всех данных.
Запускается по cron каждый день в 23:00.
"""

import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

sys.path.append(str(Path(__file__).parent.parent))


def update_lenta_headers():
    """Дособрать заголовки Lenta за вчера и сегодня"""
    print("\n📰 ОБНОВЛЕНИЕ ЗАГОЛОВКОВ LENTA...")
    from src.data_collection.collect_lenta_headers import HeaderCollector
    collector = HeaderCollector()

    yesterday = datetime.now() - timedelta(days=1)
    today = datetime.now()

    # Собираем за 2 дня (на случай если вчера пропустили)
    collector.collect_period(yesterday, today)
    print("✅ Заголовки обновлены")


def classify_new_headers():
    """Классифицировать новые заголовки"""
    print("\n🧠 КЛАССИФИКАЦИЯ НОВЫХ ЗАГОЛОВКОВ...")
    from src.llm_labeling.classify_lenta_final import classify_day, merge_all
    from src.data_collection.collect_lenta_headers import HeaderCollector

    yesterday = datetime.now() - timedelta(days=1)
    today = datetime.now()

    # Классифицируем последние 2 дня
    for date in [yesterday, today]:
        classify_day(date, verbose=False)

    # Объединяем все дни
    merge_all()
    print("✅ Классификация завершена")


def update_embeddings():
    """Добавить векторы только для новых дней"""
    print("\n🔧 ОБНОВЛЕНИЕ ВЕКТОРОВ ДНЕЙ...")
    import json
    import numpy as np
    import pandas as pd
    from pathlib import Path
    from sentence_transformers import SentenceTransformer

    MODEL_NAME = 'intfloat/multilingual-e5-large'
    LENTA_CLASSIFIED = Path("data/features/lenta_classified/lenta_headers_classified.csv")
    DAY_VECTORS_FILE = Path("data/features/day_embeddings/day_vectors.json")

    CATEGORIES = ['WAR', 'SANCTIONS', 'OIL_GAS', 'MARKET', 'POLITICAL', 'CATASTROPHE', 'INCIDENT', 'OTHER']
    SENTIMENTS = ['POSITIVE', 'NEGATIVE', 'NEUTRAL']

    # Загружаем существующие векторы
    if DAY_VECTORS_FILE.exists():
        with open(DAY_VECTORS_FILE) as f:
            day_vectors = json.load(f)
    else:
        day_vectors = {}

    # Загружаем классифицированные заголовки
    df = pd.read_csv(LENTA_CLASSIFIED)
    df['date'] = pd.to_datetime(df['date'])

    # Находим дни которых ещё нет в векторах
    existing_dates = set(day_vectors.keys())
    new_dates = df[~df['date'].dt.strftime('%Y-%m-%d').isin(existing_dates)]

    if len(new_dates) == 0:
        print("   Все дни уже векторизованы")
        return

    print(f"   Новых дней: {new_dates['date'].nunique()}")

    # Модель
    model = SentenceTransformer(MODEL_NAME, device='cpu')

    # Добавляем только новые дни
    for date, group in new_dates.groupby('date'):
        total = len(group)
        date_str = date.strftime('%Y-%m-%d')

        cat_features = [(group['category'] == c).sum() / total for c in CATEGORIES]
        sent_features = [(group['sentiment'] == s).sum() / total for s in SENTIMENTS]

        day_text = " | ".join(group['title'].tolist())
        emb = model.encode(day_text, normalize_embeddings=True)

        full = np.concatenate([cat_features, sent_features, emb]).tolist()

        day_vectors[date_str] = {
            'date': date_str,
            'total': total,
            'categories': {c: int((group['category'] == c).sum()) for c in CATEGORIES},
            'sentiments': {s: int((group['sentiment'] == s).sum()) for s in SENTIMENTS},
            'vector': full
        }

    # Сохраняем
    with open(DAY_VECTORS_FILE, 'w', encoding='utf-8') as f:
        json.dump(day_vectors, f, ensure_ascii=False)

    print(f"   ✅ Добавлено {len(new_dates['date'].unique())} дней, всего {len(day_vectors)}")


def update_datasets():
    """Пересобрать датасеты для 5 компаний"""
    print("\n📊 ПЕРЕСБОРКА ДАТАСЕТОВ...")
    from scripts.build_company_datasets import build_dataset, COMPANIES

    for ticker in COMPANIES:
        try:
            build_dataset(ticker)
            print(f"  ✅ {ticker}")
        except Exception as e:
            print(f"  ❌ {ticker}: {e}")

    print("✅ Датасеты обновлены")


def main():
    print("=" * 70)
    print(f"🚀 ЕЖЕДНЕВНОЕ ОБНОВЛЕНИЕ — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    start = time.time()

    try:
        update_lenta_headers()
        classify_new_headers()
        update_embeddings()
        update_datasets()
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")

    elapsed = time.time() - start
    print(f"\n✅ ГОТОВО за {elapsed / 60:.1f} мин")


if __name__ == "__main__":
    main()