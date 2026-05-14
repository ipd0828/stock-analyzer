# src/llm_labeling/classify_lenta_final.py

"""
РАБОЧАЯ КЛАССИФИКАЦИЯ
- Идёт с последней даты в прошлое
- По одному заголовку (стабильно)
- Сохраняет после каждого дня
"""

import json
import pandas as pd
from openai import OpenAI
from tqdm import tqdm
from pathlib import Path
import sys
from datetime import datetime, timedelta
import time
import argparse

sys.path.append(str(Path(__file__).parent.parent.parent))

LENTA_ARCHIVE_DIR = Path("/home/ipd0828-777/PycharmProjects/stockanalyser_2/data/lenta_archive")
OUTPUT_DIR = Path("/home/ipd0828-777/PycharmProjects/stockanalyser_2/data/features/lenta_classified")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = """Return JSON: {"category":"...", "sentiment":"..."}

Categories: WAR, SANCTIONS, OIL_GAS, MARKET, CATASTROPHE, POLITICAL, SOCIAL, INCIDENT, OTHER
Sentiments: POSITIVE, NEGATIVE, NEUTRAL"""


def classify_one(title):
    if not title or len(title) < 10:
        return {"category": "OTHER", "sentiment": "NEUTRAL"}

    client = OpenAI(base_url="http://127.0.0.1:8001/v1", api_key="sk-no-key-required")

    try:
        response = client.chat.completions.create(
            model="unsloth/Qwen3.5-9B-GGUF",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f'Headline: "{title[:200]}"'}
            ],
            temperature=0,
            max_tokens=80,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            timeout=30
        )

        text = response.choices[0].message.content.strip()
        if text.startswith('```json'):
            text = text[7:]
        if text.startswith('```'):
            text = text[3:]
        if text.endswith('```'):
            text = text[:-3]

        data = json.loads(text)
        return {"category": data.get("category", "OTHER"), "sentiment": data.get("sentiment", "NEUTRAL")}

    except:
        return {"category": "OTHER", "sentiment": "NEUTRAL"}


def get_all_dates():
    """Возвращает все даты из папки, отсортированные от последней к первой"""
    files = sorted(LENTA_ARCHIVE_DIR.glob("*.json"))
    dates = []
    for f in files:
        try:
            dates.append(datetime.strptime(f.stem, '%Y-%m-%d'))
        except:
            continue
    return sorted(dates, reverse=True)  # <- последняя дата первая


def classify_day(date, verbose=False):
    date_str = date.strftime("%Y-%m-%d")
    file_path = LENTA_ARCHIVE_DIR / f"{date_str}.json"

    if not file_path.exists():
        return 0

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    articles = data.get('articles', [])
    if not articles:
        return 0

    day_file = OUTPUT_DIR / f"lenta_{date_str}.csv"
    if day_file.exists():
        return 0

    if verbose:
        print(f"\n📅 {date_str} - {len(articles)} заголовков")

    results = []
    for article in tqdm(articles, desc=f"   {date_str}", leave=False):
        title = article.get('title', '')
        if not title:
            continue

        result = classify_one(title)

        results.append({
            'date': date_str,
            'title': title,
            'url': article.get('url', ''),
            'category': result['category'],
            'sentiment': result['sentiment']
        })

        time.sleep(0.02)

    if results:
        df = pd.DataFrame(results)
        df.to_csv(day_file, index=False, encoding='utf-8')
        if verbose:
            print(f"   💾 Сохранено: {day_file}")

    return len(results)


def classify_all(verbose=False):
    all_dates = get_all_dates()

    if not all_dates:
        print("❌ Нет файлов с заголовками")
        return

    print("\n" + "=" * 70)
    print("📝 КЛАССИФИКАЦИЯ ЗАГОЛОВКОВ (с последней даты)")
    print(f"   Всего дней: {len(all_dates)}")
    print(f"   Первый день: {all_dates[0].strftime('%Y-%m-%d')}")
    print(f"   Последний: {all_dates[-1].strftime('%Y-%m-%d')}")
    print("=" * 70)

    total = 0
    start_time = time.time()

    for date in all_dates:
        total += classify_day(date, verbose)

    elapsed = time.time() - start_time

    # Объединяем все дни
    merge_all()

    print(f"\n✅ ГОТОВО!")
    print(f"   Заголовков: {total}")
    print(f"   Время: {elapsed / 60:.1f} мин")


def merge_all():
    all_files = sorted(OUTPUT_DIR.glob("lenta_*.csv"))
    if not all_files:
        return

    dfs = []
    for f in all_files:
        dfs.append(pd.read_csv(f))

    df_all = pd.concat(dfs, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=['url'], keep='last')
    df_all = df_all.sort_values('date')

    output_file = OUTPUT_DIR / "lenta_headers_classified.csv"
    df_all.to_csv(output_file, index=False, encoding='utf-8')

    print(f"\n💾 ОБЪЕДИНЕНО: {len(df_all)} заголовков")
    print(f"   Файл: {output_file}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    classify_all(verbose=args.verbose)


if __name__ == "__main__":
    main()