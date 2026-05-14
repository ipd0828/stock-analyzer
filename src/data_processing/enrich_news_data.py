# src/data_processing/enrich_news_data.py

import pandas as pd
import json
from pathlib import Path
import sys
from datetime import datetime
from tqdm import tqdm
import argparse
import requests
from bs4 import BeautifulSoup
import re

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR, PROCESSED_DATA_DIR
from config.settings import REQUEST_DELAY


# Функция парсинга страницы статьи
def parse_article_page(url: str):
    """Парсит страницу со статьёй"""

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'

        if response.status_code != 200:
            print(f"   ❌ Статус {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')

        result = {
            'author': None,
            'date_published': None,
            'text': None,
            'views': None,
            'favorites': None,
            'tags': [],
            'comments': []
        }

        # 1. Дата и автор
        action_list = soup.find('ul', class_='action')
        if action_list:
            date_li = action_list.find('li', class_='date')
            if date_li:
                result['date_published'] = date_li.get_text(strip=True)
                print(f"      📅 Дата: {result['date_published']}")

            author_li = action_list.find('li', class_='author')
            if author_li:
                author_link = author_li.find('a')
                if author_link:
                    result['author'] = author_link.get_text(strip=True)
                    print(f"      ✍️ Автор: {result['author']}")

        # 2. Текст статьи - ищем ВСЕ div.content и берём нужный
        content_divs = soup.find_all('div', class_='content')
        print(f"      🔍 Найдено div.content: {len(content_divs)}")

        for i, div in enumerate(content_divs):
            text = div.get_text('\n', strip=True)
            print(f"         div {i + 1}: {len(text)} символов")

            # Если в тексте есть слова, которые указывают на реальную статью
            if text and 'Авторизация' not in text and len(text) > 200:
                result['text'] = text[:10000]
                print(f"      ✅ Текст найден в div {i + 1} ({len(result['text'])} символов)")
                print(f"      Первые 200 символов: {result['text'][:200]}...")
                break

        if not result['text']:
            print(f"      ⚠️ Текст не найден ни в одном div.content")

        # 3. Просмотры и избранное
        views_div = soup.find('div', class_='views-total-topic')
        if views_div:
            views_span = views_div.find('span', class_='views-span') or views_div.find('span',
                                                                                       class_='watchlater-views-indicator')
            if views_span:
                views_text = views_span.get_text(strip=True)
                if views_text.isdigit():
                    result['views'] = int(views_text)
                    print(f"      👁️ Просмотры: {result['views']}")

            fav_span = views_div.find('span', class_='favourited_menu')
            if fav_span:
                fav_text = fav_span.get_text(strip=True).replace('★', '').strip()
                if fav_text and fav_text.isdigit():
                    result['favorites'] = int(fav_text)
                    print(f"      ⭐ В избранном: {result['favorites']}")

        # 4. Теги
        tags_ul = soup.find('ul', class_='tags')
        if tags_ul:
            for tag_li in tags_ul.find_all('li'):
                tag_link = tag_li.find('a')
                if tag_link:
                    tag = tag_link.get_text(strip=True)
                    if tag and tag != 'Ключевые слова:':
                        result['tags'].append(tag)
            if result['tags']:
                print(f"      🏷️ Теги: {', '.join(result['tags'][:3])}...")

        # 5. Комментарии
        comments_div = soup.find('div', class_='comments')
        if comments_div:
            comments = comments_div.find_all('div', class_='comment')
            for comment in comments:
                try:
                    text_div = comment.find('div', class_='text')
                    if not text_div:
                        continue

                    author_elem = comment.find('div', class_='author')
                    author = author_elem.get_text(strip=True) if author_elem else None

                    date_elem = comment.find('li', class_='date')
                    comment_date = date_elem.get_text(strip=True) if date_elem else None

                    result['comments'].append({
                        'author': author,
                        'date': comment_date,
                        'text': text_div.get_text(strip=True)[:500]
                    })
                except:
                    continue

            if result['comments']:
                print(f"      💬 Комментариев: {len(result['comments'])}")

        return result

    except Exception as e:
        print(f"❌ Ошибка парсинга {url}: {e}")
        return None

    except Exception as e:
        print(f"❌ Ошибка парсинга {url}: {e}")
        return None


class NewsDataEnricher:
    """Обогащает данные новостей: добавляет текст, даты, комментарии"""

    def __init__(self):
        self.input_file = RAW_DATA_DIR / "news_links" / "company_news_processed.csv"
        self.output_dir = PROCESSED_DATA_DIR / "enriched_news"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.results = []
        print(f"📁 Входной файл: {self.input_file}")
        print(f"📁 Выходная папка: {self.output_dir}")

    def normalize_date(self, date_str: str) -> str:
        """Преобразует дату из формата 'ДД/ММ' в 'YYYY-MM-DD'"""
        if not date_str or pd.isna(date_str):
            return None

        try:
            parts = date_str.strip().split('/')
            if len(parts) == 2:
                day, month = int(parts[0]), int(parts[1])
                year = datetime.now().year
                if month > datetime.now().month:
                    year -= 1
                return f"{year}-{month:02d}-{day:02d}"
            elif len(parts) == 3:
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                if year < 100:
                    year += 2000
                return f"{year}-{month:02d}-{day:02d}"
        except:
            pass
        return None

    def process_article(self, row):
        """Обрабатывает одну статью"""
        try:
            article_data = parse_article_page(row['url'])
            if not article_data:
                return None

            normalized_date = self.normalize_date(row['date'])

            result = {
                'url': row['url'],
                'article_id': row['article_id'],
                'title': row['title'],
                'date_raw': row['date'],
                'date_normalized': normalized_date,
                'tickers': row['tickers'],  # все тикеры через |
                'mentions': row['mentions'],  # количество компаний
                'comments_count_raw': row['comments'] if pd.notna(row['comments']) else 0,

                # Данные со страницы статьи
                'article_author': article_data.get('author'),
                'article_date': article_data.get('date_published'),
                'article_text': article_data.get('text'),
                'views': article_data.get('views'),
                'rating': article_data.get('rating'),
                'tags': '|'.join(article_data.get('tags', [])),
                'comments_data': json.dumps(article_data.get('comments', []), ensure_ascii=False),
                'comments_count_actual': len(article_data.get('comments', [])),

                'processed_at': datetime.now().isoformat()
            }

            return result

        except Exception as e:
            print(f"❌ Ошибка обработки {row['url']}: {e}")
            return None

    def save_progress(self, processed_count):
        """Промежуточное сохранение"""
        temp_df = pd.DataFrame(self.results)
        temp_file = self.output_dir / "enriched_news_temp.csv"
        temp_df.to_csv(temp_file, index=False, encoding='utf-8')
        print(f"\n💾 Промежуточно сохранено {processed_count} записей")

    def save_final(self):
        """Финальное сохранение"""
        if not self.results:
            print("❌ Нет данных для сохранения")
            return

        df = pd.DataFrame(self.results)

        # Основной файл
        output_file = self.output_dir / "enriched_news.csv"
        df.to_csv(output_file, index=False, encoding='utf-8')

        # JSON для сложных структур
        json_file = self.output_dir / "enriched_news.json"
        df.to_json(json_file, orient='records', force_ascii=False, indent=2)

        print(f"\n✅ Данные сохранены:")
        print(f"   CSV: {output_file}")
        print(f"   JSON: {json_file}")
        print(f"   Всего записей: {len(df)}")

        # Статистика
        print(f"\n📊 СТАТИСТИКА:")
        print(f"   С компаниями:")

        # Анализируем тикеры
        all_tickers = []
        for tickers in df['tickers']:
            all_tickers.extend(tickers.split('|'))

        from collections import Counter
        ticker_counts = Counter(all_tickers)
        for ticker in sorted(ticker_counts.keys()):
            print(f"   {ticker}: {ticker_counts[ticker]} статей")

        # Статьи с текстом
        with_text = df[df['article_text'].notna()]
        print(f"\n   Статей с текстом: {len(with_text)} ({len(with_text) / len(df) * 100:.1f}%)")

        # Статьи с комментариями
        with_comments = df[df['comments_count_actual'] > 0]
        print(f"   Статей с комментариями: {len(with_comments)} ({len(with_comments) / len(df) * 100:.1f}%)")

        # Диапазон дат
        valid_dates = df[df['date_normalized'].notna()]
        if len(valid_dates) > 0:
            min_date = valid_dates['date_normalized'].min()
            max_date = valid_dates['date_normalized'].max()
            print(f"   Период: {min_date} - {max_date}")

    def process_all(self, limit=None):
        """Обрабатывает все новости"""

        print("📚 Загрузка данных новостей...")
        df = pd.read_csv(self.input_file)
        print(f"   Всего записей: {len(df)}")

        if limit:
            df = df.head(limit)
            print(f"   Тестовый режим: {limit} записей")

        print("\n🚀 Начало обработки статей...")

        for idx, row in tqdm(df.iterrows(), total=len(df), desc="Прогресс"):
            result = self.process_article(row)
            if result:
                self.results.append(result)

            # Промежуточное сохранение каждые 100 записей
            if (idx + 1) % 100 == 0:
                self.save_progress(idx + 1)

            # Небольшая задержка между запросами
            if (idx + 1) % 10 == 0:
                import time
                time.sleep(REQUEST_DELAY)

        # Финальное сохранение
        self.save_final()


def main():
    """Основная функция"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, help='Количество статей для теста')
    args = parser.parse_args()

    enricher = NewsDataEnricher()

    if args.limit:
        print(f"\n🧪 ТЕСТОВЫЙ РЕЖИМ: обрабатываем {args.limit} статей")
        enricher.process_all(limit=args.limit)
    else:
        enricher.process_all()


if __name__ == "__main__":
    main()