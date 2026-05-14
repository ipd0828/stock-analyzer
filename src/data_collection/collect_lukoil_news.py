# src/data_collection/collect_lukoil_news.py

"""
Сбор всех официальных новостей Лукойла через пагинацию URL
"""

import requests
import pandas as pd
import sys
import re
import time
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
from tqdm import tqdm

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR


class LukoilNewsCollector:
    """
    Сборщик новостей Лукойла через URL пагинацию
    """

    def __init__(self):
        self.base_url = "https://lukoil.ru/ru/PressCenter/Pressreleases"
        self.output_dir = RAW_DATA_DIR / "lukoil_official_news"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    def fetch_page(self, skip=0, take=20):
        """Загружает страницу с параметрами take и skip"""
        url = f"{self.base_url}?take={take}&skip={skip}"

        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.encoding = 'utf-8'

            if response.status_code == 200:
                return response.text
            else:
                print(f"   ❌ HTTP {response.status_code}")
                return None
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            return None

    def extract_json_from_html(self, html):
        """Извлекает JSON с новостями из HTML"""
        match = re.search(r'<script[^>]*class="pressreleases-data"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not match:
            return None

        try:
            import json
            return json.loads(match.group(1))
        except:
            return None

    def parse_news_item(self, item):
        """Парсит одну новость"""

        # Очищаем HTML
        announcement = item.get('Announcement', '')
        if announcement:
            announcement = re.sub(r'<[^>]+>', '', announcement)
            announcement = announcement.replace('&nbsp;', ' ').strip()

        description = item.get('Description', '')
        if description:
            description = re.sub(r'<[^>]+>', '', description)
            description = description.replace('&nbsp;', ' ').strip()

        # Нормализуем URL
        url = item.get('Url', '')
        if url and not url.startswith('http'):
            url = 'https://lukoil.ru' + url

        # Нормализуем дату
        date_str = item.get('PublicationDate', '')
        if date_str:
            date_str = date_str.split('T')[0]

        return {
            'ticker': 'LKOH',
            'company': 'Лукойл',
            'date': date_str,
            'title': item.get('Name', ''),
            'announcement': announcement[:1000],
            'description': description[:3000],
            'url': url,
            'source': 'lukoil_official',
            'collected_at': datetime.now().isoformat()
        }

    def get_total_count(self):
        """Получает общее количество новостей из первой страницы"""
        html = self.fetch_page(skip=0, take=1)
        if not html:
            return 0

        data = self.extract_json_from_html(html)
        if data:
            return data.get('Count', 0)
        return 0

    def collect_all(self, max_items=None):
        """Собирает все новости"""

        print("\n" + "=" * 70)
        print("🚀 СБОР ОФИЦИАЛЬНЫХ НОВОСТЕЙ ЛУКОЙЛА")
        print("=" * 70)

        # Получаем общее количество
        total = self.get_total_count()
        if total == 0:
            print("❌ Не удалось получить количество новостей")
            return []

        print(f"\n📊 Всего новостей: {total}")

        if max_items:
            total = min(total, max_items)
            print(f"   Тестовый режим: {max_items}")

        all_news = []
        batch_size = 20  # Загружаем по 20 новостей за раз

        with tqdm(total=total, desc="Загрузка") as pbar:
            for skip in range(0, total, batch_size):
                html = self.fetch_page(skip=skip, take=batch_size)

                if not html:
                    continue

                data = self.extract_json_from_html(html)
                if not data or 'Items' not in data:
                    continue

                for item in data['Items']:
                    news = self.parse_news_item(item)
                    all_news.append(news)
                    pbar.update(1)

                time.sleep(0.5)  # Небольшая задержка

        # Сохраняем
        self._save_results(all_news)

        return all_news

    def _save_results(self, news):
        """Сохраняет результаты"""
        if not news:
            print("❌ Нет данных для сохранения")
            return

        df = pd.DataFrame(news)

        csv_file = self.output_dir / "lukoil_official_news_all.csv"
        df.to_csv(csv_file, index=False, encoding='utf-8')

        json_file = self.output_dir / "lukoil_official_news_all.json"
        df.to_json(json_file, orient='records', force_ascii=False, indent=2)

        print("\n" + "=" * 70)
        print("✅ СБОР НОВОСТЕЙ ЛУКОЙЛА ЗАВЕРШЁН")
        print("=" * 70)
        print(f"\n📁 Файлы сохранены:")
        print(f"   CSV: {csv_file}")
        print(f"   JSON: {json_file}")
        print(f"   Всего новостей: {len(df)}")

        # Статистика по годам
        df['year'] = pd.to_datetime(df['date'], errors='coerce').dt.year
        print(f"\n📊 СТАТИСТИКА ПО ГОДАМ:")
        for year in sorted(df['year'].dropna().unique()):
            count = (df['year'] == year).sum()
            print(f"   {int(year)}: {count} новостей")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--max', type=int, help='Максимум новостей для теста')

    args = parser.parse_args()

    collector = LukoilNewsCollector()

    if args.max:
        print(f"\n🧪 ТЕСТ: {args.max} новостей")
        collector.collect_all(max_items=args.max)
    else:
        print("\n🚀 ПОЛНЫЙ СБОР")
        collector.collect_all()


if __name__ == "__main__":
    main()