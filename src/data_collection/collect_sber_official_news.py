# src/data_collection/collect_sber_official_news.py

"""
Сбор официальных новостей с сайта Сбербанка (IR раздел)
Источник: https://www.sberbank.com/ru/investor-relations/ir/news
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import sys
from pathlib import Path
from datetime import datetime
import json
import re

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR
from config.settings import REQUEST_DELAY


class SberOfficialNewsCollector:
    """
    Сборщик официальных новостей с сайта Сбербанка
    """

    def __init__(self):
        self.base_url = "https://www.sberbank.com/ru/investor-relations/ir/news"
        self.output_dir = RAW_DATA_DIR / "sber_official_news"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        self.news_data = []

    def get_page(self, page=1):
        """Загружает страницу с новостями"""
        if page == 1:
            url = self.base_url
        else:
            url = f"{self.base_url}?page={page}"

        print(f"   Загрузка страницы {page}: {url}")

        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.encoding = 'utf-8'

            if response.status_code == 200:
                return response.text
            else:
                print(f"      ❌ HTTP {response.status_code}")
                return None
        except Exception as e:
            print(f"      ❌ Ошибка: {e}")
            return None

    def get_total_pages(self, html):
        """Определяет общее количество страниц"""
        soup = BeautifulSoup(html, 'html.parser')

        # Ищем пагинацию
        pagination = soup.find('nav', class_='list-paginator')
        if not pagination:
            return 1

        # Ищем последнюю страницу
        pages = pagination.find_all('li', role='button')
        max_page = 0
        for page in pages:
            text = page.text.strip()
            if text.isdigit():
                max_page = max(max_page, int(text))

        return max_page if max_page > 0 else 1

    def parse_page(self, html, page_num):
        """Парсит страницу и извлекает новости"""
        soup = BeautifulSoup(html, 'html.parser')
        news_items = []

        # Находим все статьи
        articles = soup.find_all('div', class_='news-archive-list__article')

        for article in articles:
            try:
                # Дата
                date_elem = article.find('div', class_='sta-date__date-text')
                date_raw = date_elem.text.strip() if date_elem else None

                # Заголовок и ссылка
                link_elem = article.find('a', class_='news-archive-list__title')
                if not link_elem:
                    continue

                title = link_elem.text.strip()
                href = link_elem.get('href')

                # Полный URL
                if href.startswith('/'):
                    full_url = f"https://www.sberbank.com{href}"
                else:
                    full_url = href

                # UUID из ссылки (если есть)
                uuid_match = re.search(r'newsID=([a-f0-9-]+)', full_url)
                uuid = uuid_match.group(1) if uuid_match else None

                # Парсим дату
                news_date = None
                if date_raw:
                    try:
                        # Формат: "11 марта 2026"
                        months = {
                            'января': '01', 'февраля': '02', 'марта': '03',
                            'апреля': '04', 'мая': '05', 'июня': '06',
                            'июля': '07', 'августа': '08', 'сентября': '09',
                            'октября': '10', 'ноября': '11', 'декабря': '12'
                        }
                        parts = date_raw.split()
                        if len(parts) == 3:
                            day, month_str, year = parts
                            month = months.get(month_str.lower())
                            if month:
                                news_date = f"{year}-{month}-{day.zfill(2)}"
                    except:
                        pass

                news_items.append({
                    'uuid': uuid,
                    'date_raw': date_raw,
                    'date_normalized': news_date,
                    'title': title,
                    'url': full_url,
                    'page': page_num,
                    'source': 'sberbank_official',
                    'collected_at': datetime.now().isoformat()
                })

            except Exception as e:
                print(f"      ⚠️ Ошибка парсинга статьи: {e}")
                continue

        return news_items

    def get_article_content(self, url):
        """Получает полный текст статьи"""
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.encoding = 'utf-8'

            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, 'html.parser')

            # Ищем контейнер с текстом
            content = soup.find('div', class_='article-content')
            if not content:
                content = soup.find('div', class_='news-detail__content')
            if not content:
                content = soup.find('article')

            if content:
                # Убираем лишние элементы
                for tag in content.find_all(['script', 'style', 'iframe', 'nav']):
                    tag.decompose()

                text = content.get_text('\n', strip=True)
                return text[:5000]  # Ограничиваем длину

            return None

        except Exception as e:
            print(f"      ⚠️ Ошибка загрузки статьи: {e}")
            return None

    def collect_all(self, max_pages=None, get_full_text=False):
        """Собирает все новости"""

        print("\n" + "=" * 70)
        print("🚀 СБОР ОФИЦИАЛЬНЫХ НОВОСТЕЙ СБЕРБАНКА")
        print("=" * 70)

        # Загружаем первую страницу
        first_page = self.get_page(1)
        if not first_page:
            print("❌ Не удалось загрузить первую страницу")
            return []

        total_pages = self.get_total_pages(first_page)
        print(f"\n📄 Всего страниц: {total_pages}")

        if max_pages:
            total_pages = min(total_pages, max_pages)
            print(f"   Тестовый режим: {max_pages} страниц")

        all_news = []

        for page in range(1, total_pages + 1):
            print(f"\n📄 Страница {page}/{total_pages}")

            if page == 1:
                html = first_page
            else:
                html = self.get_page(page)

            if not html:
                print(f"   ⚠️ Не удалось загрузить страницу {page}")
                continue

            news = self.parse_page(html, page)
            print(f"   Найдено новостей: {len(news)}")

            # Загружаем полные тексты (опционально)
            if get_full_text:
                for i, item in enumerate(news):
                    print(f"      Загрузка текста {i + 1}/{len(news)}...")
                    content = self.get_article_content(item['url'])
                    if content:
                        item['content'] = content
                    time.sleep(REQUEST_DELAY / 2)

            all_news.extend(news)
            time.sleep(REQUEST_DELAY)

        # Сохраняем результаты
        self._save_results(all_news, get_full_text)

        return all_news

    def _save_results(self, news, with_content=False):
        """Сохраняет результаты"""
        if not news:
            print("❌ Нет данных для сохранения")
            return

        df = pd.DataFrame(news)

        # Сохраняем CSV
        csv_file = self.output_dir / "sber_official_news_all.csv"
        df.to_csv(csv_file, index=False, encoding='utf-8')

        # Сохраняем JSON
        json_file = self.output_dir / "sber_official_news_all.json"
        df.to_json(json_file, orient='records', force_ascii=False, indent=2)

        print("\n" + "=" * 70)
        print("✅ СБОР ЗАВЕРШЁН")
        print("=" * 70)
        print(f"\n📁 Файлы сохранены:")
        print(f"   CSV: {csv_file}")
        print(f"   JSON: {json_file}")
        print(f"   Всего новостей: {len(df)}")

        # Статистика по годам
        df['year'] = pd.to_datetime(df['date_normalized'], errors='coerce').dt.year
        print(f"\n📊 СТАТИСТИКА ПО ГОДАМ:")
        for year in sorted(df['year'].dropna().unique()):
            count = (df['year'] == year).sum()
            print(f"   {int(year)}: {count} новостей")

        return df


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-pages', type=int, help='Максимум страниц для теста')
    parser.add_argument('--full-text', action='store_true', help='Собирать полные тексты')

    args = parser.parse_args()

    collector = SberOfficialNewsCollector()

    if args.max_pages:
        print(f"\n🧪 ТЕСТ: {args.max_pages} страниц")
        collector.collect_all(max_pages=args.max_pages, get_full_text=args.full_text)
    else:
        print("\n🚀 ПОЛНЫЙ СБОР")
        collector.collect_all(get_full_text=args.full_text)


if __name__ == "__main__":
    main()
