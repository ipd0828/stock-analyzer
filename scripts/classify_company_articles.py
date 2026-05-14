# scripts/classify_company_articles.py

"""
Оценка статей о компаниях через LLM
- Читает company_articles_with_text.csv
- Оценивает каждую статью по 5 параметрам
- Сохраняет результат
"""

import json
import pandas as pd
from openai import OpenAI
from tqdm import tqdm
from pathlib import Path
import sys
import time
import random
from datetime import datetime

sys.path.append(str(Path(__file__).parent.parent))

INPUT_FILE = Path("data/raw/company_articles/company_articles_with_text.csv")
OUTPUT_FILE = Path("data/features/company_articles_classified.csv")

# Промпт для классификации
SYSTEM_PROMPT = """Ты финансовый аналитик. Оцени влияние новости на компанию.

Верни ТОЛЬКО JSON в формате:
{"sentiment": "POSITIVE|NEGATIVE|NEUTRAL", "impact": -10-10, "relevance": "HIGH|MEDIUM|LOW", "category": "EARNINGS|DIVIDENDS|STRATEGY|REGULATORY|MACRO|OTHER", "time_horizon": "SHORT|MEDIUM|LONG"}"""


def classify_article(title, text):
    """Классифицирует одну статью"""
    content = f"Заголовок: {title}\n\nТекст: {text[:2000]}"

    client = OpenAI(base_url="http://127.0.0.1:8001/v1", api_key="sk-no-key-required")

    try:
        response = client.chat.completions.create(
            model="unsloth/Qwen3.5-9B-GGUF",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content}
            ],
            temperature=0,
            max_tokens=150,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            timeout=30
        )

        text_resp = response.choices[0].message.content.strip()

        # Очистка
        if text_resp.startswith('```json'):
            text_resp = text_resp[7:]
        if text_resp.startswith('```'):
            text_resp = text_resp[3:]
        if text_resp.endswith('```'):
            text_resp = text_resp[:-3]

        return json.loads(text_resp)

    except Exception as e:
        print(f"   Ошибка: {e}")
        return {"sentiment": "NEUTRAL", "impact": 0, "relevance": "LOW", "category": "OTHER", "time_horizon": "MEDIUM"}


def main():
    print("=" * 70)
    print("📊 КЛАССИФИКАЦИЯ СТАТЕЙ О КОМПАНИЯХ")
    print("=" * 70)

    # Загружаем статьи
    df = pd.read_csv(INPUT_FILE)
    df = df[df['text'].notna()]
    print(f"📚 Статей с текстом: {len(df)}")

    # Проверяем прогресс
    if OUTPUT_FILE.exists():
        existing = pd.read_csv(OUTPUT_FILE)
        processed_urls = set(existing['url'].tolist())
        print(f"✅ Уже обработано: {len(processed_urls)}")
        df = df[~df['url'].isin(processed_urls)]
        all_results = existing.to_dict('records')
    else:
        processed_urls = set()
        all_results = []

    print(f"📥 Осталось: {len(df)}")

    if len(df) == 0:
        print("✅ Все статьи уже обработаны!")
        return

    # Классифицируем
    success = 0

    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Классификация"):
        title = row['title']
        text = row['text']
        company = row['company']
        date = row['date']

        result = classify_article(title, text)

        all_results.append({
            'date': date,
            'title': title,
            'url': row['url'],
            'company': company,
            'sentiment': result.get('sentiment', 'NEUTRAL'),
            'impact': result.get('impact', 0),
            'relevance': result.get('relevance', 'MEDIUM'),
            'category': result.get('category', 'OTHER'),
            'time_horizon': result.get('time_horizon', 'MEDIUM'),
            'text_length': row['text_length'],
            'classified_at': datetime.now().isoformat()
        })

        success += 1

        # Сохраняем каждые 100
        if success % 100 == 0:
            df_temp = pd.DataFrame(all_results)
            df_temp.to_csv(OUTPUT_FILE, index=False, encoding='utf-8')
            print(f"   💾 Сохранено: {success}")

        # Задержка
        time.sleep(random.uniform(0.3, 0.7))

    # Финальное сохранение
    df_results = pd.DataFrame(all_results)
    df_results.to_csv(OUTPUT_FILE, index=False, encoding='utf-8')

    print(f"\n✅ ГОТОВО!")
    print(f"   Файл: {OUTPUT_FILE}")
    print(f"   Всего: {len(df_results)} статей")

    # Статистика
    print("\n📊 ПО КОМПАНИЯМ:")
    for company in df_results['company'].unique():
        comp_df = df_results[df_results['company'] == company]
        pos = (comp_df['sentiment'] == 'POSITIVE').sum()
        neg = (comp_df['sentiment'] == 'NEGATIVE').sum()
        high_impact = (comp_df['impact'].abs() >= 5).sum()
        print(f"   {company}: {len(comp_df)} статей | POS: {pos} | NEG: {neg} | HIGH_IMPACT: {high_impact}")

    print("\n📊 ПО КАТЕГОРИЯМ:")
    for cat in ['EARNINGS', 'DIVIDENDS', 'STRATEGY', 'REGULATORY', 'MACRO', 'OTHER']:
        count = (df_results['category'] == cat).sum()
        if count > 0:
            print(f"   {cat}: {count}")


if __name__ == "__main__":
    main()