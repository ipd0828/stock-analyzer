# scripts/extract_company_links.py

"""
Из исходных JSON-файлов Lenta.ru находит статьи с упоминаниями компаний,
сохраняет ссылки для последующего скачивания.
Работает напрямую с JSON, не дожидаясь классификации.
"""

import json
import pandas as pd
from pathlib import Path
import sys
from datetime import datetime
import re

sys.path.append(str(Path(__file__).parent.parent))

LENTA_ARCHIVE_DIR = Path("data/lenta_archive")
OUTPUT_FILE = Path("data/raw/company_articles/company_articles_to_fetch.csv")
OUTPUT_DIR = Path("data/raw/company_articles")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# РАСШИРЕННЫЕ КЛЮЧЕВЫЕ СЛОВА
COMPANY_KEYWORDS = {
    'SBER': [
        'сбер', 'сбербанк', 'sber', 'сбера', 'сбербанка',
        'sberbank', 'сбер онлайн', 'сбербанк россии'
    ],
    'GAZP': [
        'газпром', 'gazprom', 'газпрома', 'gazprom',
        'газпромбанк', 'gazprombank'
    ],
    'LKOH': [
        'лукойл', 'lukoil', 'лукойла', 'lukoil',
        'лукойл нефть', 'лукойл компания'
    ],
    'NVTK': [
        'новатэк', 'novatek', 'новатэка', 'novatek',
        'ямал спг', 'ямал lng', 'арктик спг', 'арктик lng'
    ],
    'VTBR': [
        'втб', 'vtb', 'втб банк', 'vtb bank',
        'втб 24', 'vtb 24', 'банк втб'
    ]
}

TICKERS = ['SBER', 'GAZP', 'LKOH', 'NVTK', 'VTBR']


def find_company_in_title(title):
    """Возвращает тикер компании, если найдено упоминание"""
    if not title:
        return None

    title_lower = title.lower()

    # Поиск по ключевым словам
    for ticker, keywords in COMPANY_KEYWORDS.items():
        for kw in keywords:
            if kw in title_lower:
                return ticker

    # Поиск по тикерам как отдельным словам
    for ticker in TICKERS:
        if f' {ticker.lower()} ' in title_lower or title_lower.startswith(f'{ticker.lower()} '):
            return ticker

    return None


def extract_links():
    """Проходит по всем JSON файлам и собирает ссылки"""
    json_files = sorted(LENTA_ARCHIVE_DIR.glob("*.json"))
    print(f"📁 Найдено JSON файлов: {len(json_files)}")

    results = []
    found_count = 0
    processed_days = 0

    for file_path in json_files:
        date_str = file_path.stem

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        articles = data.get('articles', [])

        for article in articles:
            title = article.get('title', '')
            url = article.get('url', '')

            if not url or not title:
                continue

            company = find_company_in_title(title)

            if company:
                results.append({
                    'date': date_str,
                    'title': title,
                    'url': url,
                    'company': company,
                    'found_at': datetime.now().isoformat()
                })
                found_count += 1

        processed_days += 1
        if processed_days % 100 == 0:
            print(f"   Обработано {processed_days} дней, найдено {found_count}")

    # Сохраняем
    df_results = pd.DataFrame(results)
    df_results.to_csv(OUTPUT_FILE, index=False, encoding='utf-8')

    print(f"\n✅ Найдено статей с упоминаниями: {len(df_results)}")
    print(f"   Сохранено: {OUTPUT_FILE}")

    # Статистика по компаниям
    print("\n📊 ПО КОМПАНИЯМ:")
    for company in COMPANY_KEYWORDS.keys():
        count = (df_results['company'] == company).sum()
        print(f"   {company}: {count}")

    # Примеры
    print("\n📰 ПРИМЕРЫ НАЙДЕННЫХ СТАТЕЙ:")
    for _, row in df_results.head(10).iterrows():
        print(f"   {row['date']} | {row['company']} | {row['title'][:70]}...")

    return df_results


if __name__ == "__main__":
    extract_links()