# scripts/parse_lenta_articles.py

"""
Полноценный скрипт для парсинга статей Lenta.ru
- Читает ссылки из company_articles_to_fetch.csv
- Парсит текст каждой статьи
- Сохраняет результат в company_articles_with_text.csv
- Поддерживает возобновление (можно остановить и продолжить)
"""

import requests
import pandas as pd
import time
import random
import json
import re
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
from bs4 import BeautifulSoup

# ========== КОНФИГУРАЦИЯ ==========
INPUT_FILE = Path("data/raw/company_articles/company_articles_to_fetch.csv")
OUTPUT_FILE = Path("data/raw/company_articles/company_articles_with_text.csv")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}


# ========== ПАРСЕР СТАТЬИ ==========
def parse_article(url: str) -> dict:
    """
    Парсит одну статью с Lenta.ru
    Возвращает словарь с полями: title, text, date, author, rubric, tags
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.encoding = 'utf-8'

        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, 'html.parser')

        result = {
            'title': None,
            'text': None,
            'date': None,
            'author': None,
            'rubric': None,
            'tags': []
        }

        # ===== ЗАГОЛОВОК =====
        title_elem = soup.find('h1', class_='topic-body__title')
        if title_elem:
            result['title'] = title_elem.get_text(strip=True)

        if not result['title']:
            og_title = soup.find('meta', property='og:title')
            if og_title:
                result['title'] = og_title.get('content', '')

        # ===== ДАТА =====
        date_elem = soup.find('a', class_='topic-header__time')
        if date_elem:
            result['date'] = date_elem.get_text(strip=True)

        if not result['date']:
            time_meta = soup.find('meta', property='article:published_time')
            if time_meta:
                result['date'] = time_meta.get('content', '')

        # ===== АВТОР =====
        author_elem = soup.find('span', class_='topic-authors__name')
        if author_elem:
            result['author'] = author_elem.get_text(strip=True)

        # ===== РУБРИКА =====
        rubric_elem = soup.find('div', class_='rubric-header__title')
        if rubric_elem:
            result['rubric'] = rubric_elem.get_text(strip=True)

        # ===== ТЕКСТ СТАТЬИ (самое важное) =====
        text_parts = []

        # Ищем контейнер с текстом
        content_div = soup.find('div', class_='topic-body__content')
        if not content_div:
            content_div = soup.find('div', itemprop='articleBody')
        if not content_div:
            content_div = soup.find('div', class_='news-detail__content')

        if content_div:
            # Убираем мусор
            for tag in content_div.find_all(['script', 'style', 'ins', 'iframe', 'div.banner']):
                tag.decompose()

            # Собираем параграфы
            paragraphs = content_div.find_all('p')
            for p in paragraphs:
                p_text = p.get_text(strip=True)
                if p_text and len(p_text) > 30:
                    text_parts.append(p_text)

            # Если нет параграфов — берём весь текст
            if not text_parts:
                full_text = content_div.get_text(' ', strip=True)
                if full_text:
                    text_parts.append(full_text)

        result['text'] = '\n\n'.join(text_parts) if text_parts else None

        # ===== ТЕГИ =====
        if content_div:
            tags = set()
            for link in content_div.find_all('a', href=True):
                if '/tags/' in link.get('href', ''):
                    tag_text = link.get_text(strip=True)
                    if tag_text and len(tag_text) < 50:
                        tags.add(tag_text)
            result['tags'] = list(tags)

        # ===== JSON-LD (запасной вариант) =====
        if not result['text']:
            json_ld = soup.find('script', type='application/ld+json')
            if json_ld and json_ld.string:
                try:
                    ld_data = json.loads(json_ld.string)
                    if isinstance(ld_data, list):
                        ld_data = ld_data[0]
                    if 'articleBody' in ld_data:
                        result['text'] = ld_data['articleBody']
                except:
                    pass

        return result

    except Exception as e:
        return None


# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    print("=" * 70)
    print("📥 ПАРСИНГ СТАТЕЙ LENTA.RU")
    print("=" * 70)

    # Проверяем входной файл
    if not INPUT_FILE.exists():
        print(f"❌ Файл не найден: {INPUT_FILE}")
        print("   Сначала запусти: python scripts/extract_company_links.py")
        return

    # Загружаем ссылки
    df = pd.read_csv(INPUT_FILE)
    print(f"📚 Всего ссылок: {len(df)}")

    # Загружаем уже обработанные
    processed_urls = set()
    all_results = []

    if OUTPUT_FILE.exists():
        existing = pd.read_csv(OUTPUT_FILE)
        processed_urls = set(existing['url'].tolist())
        all_results = existing.to_dict('records')
        print(f"✅ Уже обработано: {len(processed_urls)}")

    # Фильтруем
    df_to_fetch = df[~df['url'].isin(processed_urls)]
    print(f"📥 Осталось: {len(df_to_fetch)}")

    if len(df_to_fetch) == 0:
        print("✅ Все статьи уже обработаны!")
        return

    # Парсим
    success = 0

    for idx, row in tqdm(df_to_fetch.iterrows(), total=len(df_to_fetch), desc="Парсинг"):
        url = row['url']
        company = row['company']
        date = row['date']

        article = parse_article(url)

        if article and article.get('text'):
            success += 1
            result = {
                'date': date,
                'title': article.get('title', row['title']),
                'url': url,
                'company': company,
                'text': article['text'],
                'text_length': len(article['text']),
                'author': article.get('author'),
                'rubric': article.get('rubric'),
                'tags': '|'.join(article.get('tags', [])),
                'fetched_at': datetime.now().isoformat()
            }
        else:
            result = {
                'date': date,
                'title': row['title'],
                'url': url,
                'company': company,
                'text': None,
                'text_length': 0,
                'author': None,
                'rubric': None,
                'tags': None,
                'fetched_at': datetime.now().isoformat()
            }

        all_results.append(result)

        # Сохраняем после каждой статьи
        df_temp = pd.DataFrame(all_results)
        df_temp.to_csv(OUTPUT_FILE, index=False, encoding='utf-8')

        # Задержка
        time.sleep(random.uniform(0.5, 1.0))

        # Прогресс
        if success % 10 == 0 and success > 0:
            print(f"   ✅ Успешно: {success}/{len(df_to_fetch)}")

    # Финальная статистика
    print(f"\n✅ ГОТОВО!")
    print(f"   Успешно: {success}/{len(df_to_fetch)}")
    print(f"   Файл: {OUTPUT_FILE}")

    # Статистика по компаниям
    df_result = pd.read_csv(OUTPUT_FILE)
    print("\n📊 ПО КОМПАНИЯМ:")
    for company in df_result['company'].unique():
        comp_df = df_result[df_result['company'] == company]
        with_text = comp_df['text'].notna().sum()
        print(f"   {company}: {len(comp_df)} статей, с текстом: {with_text}")


if __name__ == "__main__":
    main()