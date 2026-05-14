#!/usr/bin/env python3
# scripts/find_similar_days.py
"""Поиск похожих дней через cosine similarity (CPU)"""

import os
os.environ['CUDA_VISIBLE_DEVICES'] = ''

import json
import numpy as np
import requests
from pathlib import Path
from datetime import datetime
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
import feedparser

DAY_VECTORS_FILE = Path("data/features/day_embeddings/day_vectors.json")
LENTA_RSS = "https://lenta.ru/rss/news"
MODEL_NAME = 'intfloat/multilingual-e5-large'

CATEGORIES = ['WAR', 'SANCTIONS', 'OIL_GAS', 'MARKET', 'POLITICAL', 'CATASTROPHE', 'INCIDENT', 'OTHER']
SENTIMENTS = ['POSITIVE', 'NEGATIVE', 'NEUTRAL']


def classify_headline(title: str) -> dict:
    """Классифицирует один заголовок через llama-server"""
    resp = requests.post(
        "http://127.0.0.1:8001/v1/chat/completions",
        json={
            "model": "local-model",
            "messages": [
                {"role": "system", "content": "Return JSON: {\"sentiment\":\"POSITIVE|NEGATIVE|NEUTRAL\", \"category\":\"WAR|SANCTIONS|OIL_GAS|MARKET|POLITICAL|CATASTROPHE|INCIDENT|OTHER\"}"},
                {"role": "user", "content": f'Headline: "{title[:200]}"'}
            ],
            "temperature": 0, "max_tokens": 80
        },
        timeout=30
    )
    if resp.status_code == 200:
        answer = resp.json()['choices'][0]['message']['content'].strip()
        if answer.startswith('```'): answer = answer.replace('```json', '').replace('```', '')
        try:
            return json.loads(answer)
        except:
            pass
    return {"sentiment": "NEUTRAL", "category": "OTHER"}


def main():
    print("=" * 70)
    print("🔍 ПОИСК ПОХОЖИХ ДНЕЙ")
    print("=" * 70)

    # Модель для эмбеддингов (CPU)
    print(f"\n📥 Загрузка модели {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME, device='cpu')

    # RSS сегодня
    print("📰 Загрузка RSS Lenta.ru...")
    feed = feedparser.parse(LENTA_RSS)
    headlines = []
    for entry in feed.entries[:1000]:
        result = classify_headline(entry.title)
        headlines.append({
            'title': entry.title,
            'sentiment': result.get('sentiment', 'NEUTRAL'),
            'category': result.get('category', 'OTHER')
        })
    print(f"   {len(headlines)} заголовков")

    # Вектор сегодня
    total = len(headlines)
    cat_features = [(sum(1 for h in headlines if h['category'] == c)) / total for c in CATEGORIES]
    sent_features = [(sum(1 for h in headlines if h['sentiment'] == s)) / total for s in SENTIMENTS]
    day_text = " | ".join([h['title'] for h in headlines])
    emb = model.encode(day_text, normalize_embeddings=True)
    today_vec = np.concatenate([cat_features, sent_features, emb])

    # Исторические векторы
    print("📚 Загрузка истории...")
    with open(DAY_VECTORS_FILE) as f:
        history = json.load(f)
    dates = list(history.keys())
    matrix = np.array([history[d]['vector'] for d in dates])

    # Cosine similarity
    today_2d = today_vec.reshape(1, -1)
    sims = cosine_similarity(today_2d, matrix)[0]
    top = np.argsort(sims)[-10:][::-1]

    # Вывод
    print("\nТОП-10 ПОХОЖИХ ДНЕЙ:")
    print("-" * 50)
    for i, idx in enumerate(top, 1):
        d = dates[idx]
        info = history[d]
        print(f"{i:2}. {d} (sim: {sims[idx]:.3f}) | WAR: {info['categories'].get('WAR',0):3} | NEG: {info['sentiments'].get('NEGATIVE',0):3}")

    # Сохраняем
    output = {
        'date': datetime.now().isoformat(),
        'today_categories': {c: sum(1 for h in headlines if h['category'] == c) for c in CATEGORIES},
        'similar': [{'date': dates[i], 'similarity': float(sims[i])} for i in top]
    }
    with open("data/features/similar_days.json", 'w') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ data/features/similar_days.json")


if __name__ == "__main__":
    main()