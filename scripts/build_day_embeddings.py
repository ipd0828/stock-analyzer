#!/usr/bin/env python3
# scripts/build_day_embeddings.py
import os

os.environ['CUDA_VISIBLE_DEVICES'] = ''  # CPU only

import pandas as pd
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
import json

MODEL_NAME = 'intfloat/multilingual-e5-large'  # 1024 размерности
LENTA_CLASSIFIED = Path("data/features/lenta_classified/lenta_headers_classified.csv")
OUTPUT_DIR = Path("data/features/day_embeddings")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CATEGORIES = ['WAR', 'SANCTIONS', 'OIL_GAS', 'MARKET', 'POLITICAL', 'CATASTROPHE', 'INCIDENT', 'OTHER']
SENTIMENTS = ['POSITIVE', 'NEGATIVE', 'NEUTRAL']


def main():
    print(f"📥 Загрузка модели {MODEL_NAME} (CPU)...")
    model = SentenceTransformer(MODEL_NAME, device='cpu')
    dim = model.get_sentence_embedding_dimension()
    print(f"   Размерность: {dim}")

    print(f"\n📚 Загрузка заголовков...")
    df = pd.read_csv(LENTA_CLASSIFIED)
    df['date'] = pd.to_datetime(df['date'])
    print(f"   {len(df)} заголовков, {df['date'].nunique()} дней")

    print(f"\n🔧 Векторизация...")
    day_vectors = {}

    for i, (date, group) in enumerate(df.groupby('date')):
        total = len(group)
        date_str = date.strftime('%Y-%m-%d')

        # Категории и сентименты
        cat_features = [(group['category'] == c).sum() / total for c in CATEGORIES]
        sent_features = [(group['sentiment'] == s).sum() / total for s in SENTIMENTS]

        # Эмбеддинг
        titles = group['title'].tolist()
        day_text = " | ".join(titles)
        emb = model.encode(day_text, normalize_embeddings=True)

        # Полный вектор
        full = np.concatenate([cat_features, sent_features, emb])

        day_vectors[date_str] = {
            'date': date_str,
            'total': total,
            'categories': {c: int((group['category'] == c).sum()) for c in CATEGORIES},
            'sentiments': {s: int((group['sentiment'] == s).sum()) for s in SENTIMENTS},
            'vector': full.tolist()
        }

        if (i + 1) % 100 == 0:
            print(f"   {i + 1} дней...")

    # Сохраняем
    output_file = OUTPUT_DIR / "day_vectors.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(day_vectors, f, ensure_ascii=False)

    print(f"\n✅ {output_file} ({len(day_vectors)} дней)")
    print(f"   Размер вектора: {len(list(day_vectors.values())[0]['vector'])}")


if __name__ == "__main__":
    main()