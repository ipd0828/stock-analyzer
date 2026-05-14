# src/data_collection/collect_vtb_news.py (улучшенная версия)

"""
Сбор официальных новостей ВТБ через API с возобновлением
"""

import requests
import pandas as pd
import time
import sys
import json
from pathlib import Path
from datetime import datetime
from tqdm import tqdm

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR


class VtbNewsCollector:
    """
    Сборщик новостей ВТБ через API с поддержкой возобновления
    """

    def __init__(self, start_year=2020):
        self.base_url = "https://www.vtb.ru/api/news/v2/newsArticles"
        self.start_year = start_year
        self.output_dir = RAW_DATA_DIR / "vtb_official_news"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.vtb.ru/about/press/'
        }
        self.per_page = 50

    def get_existing_ids(self):
        """Возвращает множество уже собранных ID новостей"""
        existing_ids = set()

        # Проверяем основной файл
        csv_file = self.output_dir / "vtb_official_news_all.csv"
        if csv_file.exists():
            try:
                df = pd.read_csv(csv_file)
                if 'id' in df.columns:
                    existing_ids.update(df['id'].dropna().astype(int).tolist())
                print(f"   📚 Найдено существующих новостей: {len(existing_ids)}")
            except Exception as e:
                print(f"   ⚠️ Ошибка чтения CSV: {e}")

        return existing_ids

    def fetch_page(self, skip=0):
        """Загружает одну страницу новостей через API"""
        params = {
            'Skip': skip,
            'Count': self.per_page,
            'projectSysName': 'vtb.ru',
            'Category': 'press-releases'
        }

        try:
            response = requests.get(self.base_url, headers=self.headers, params=params, timeout=15)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"   ❌ HTTP {response.status_code}")
                return None
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            return None

    def parse_news_item(self, item):
        """Парсит одну новость из JSON"""
        publish_date = item.get('publishDate', '')

        # Нормализуем дату
        if publish_date:
            try:
                day, month, year = publish_date.split('.')
                normalized_date = f"{year}-{month}-{day}"
            except:
                normalized_date = publish_date
        else:
            normalized_date = None

        return {
            'id': item.get('id'),
            'ticker': 'VTBR',
            'company': 'ВТБ',
            'date_raw': publish_date,
            'date_normalized': normalized_date,
            'create_date': item.get('createDate', ''),
            'title': item.get('title', ''),
            'text': item.get('text', '').strip(),
            'category': item.get('category', ''),
            'url': f"https://www.vtb.ru/about/press/news{item.get('url', '')}",
            'source': 'vtb_official',
            'collected_at': datetime.now().isoformat()
        }

    def save_batch(self, news_list, filename_suffix=""):
        """Сохраняет батч новостей"""
        if not news_list:
            return

        df = pd.DataFrame(news_list)

        # Основной файл (все новости)
        csv_file = self.output_dir / f"vtb_official_news_all{filename_suffix}.csv"

        # Если файл существует, добавляем новости
        if csv_file.exists():
            try:
                existing = pd.read_csv(csv_file)
                df = pd.concat([existing, df], ignore_index=True)
                # Убираем дубликаты по id
                if 'id' in df.columns:
                    df = df.drop_duplicates(subset=['id'], keep='last')
            except:
                pass

        df.to_csv(csv_file, index=False, encoding='utf-8')
        return df

    def collect_all(self, max_items=None):
        """Собирает все новости с возобновлением"""
        print("\n" + "=" * 70)
        print("🚀 СБОР ОФИЦИАЛЬНЫХ НОВОСТЕЙ ВТБ")
        print("=" * 70)

        # Загружаем уже собранные ID
        existing_ids = self.get_existing_ids()

        all_news = []
        skip = 0
        total = None
        new_count = 0

        # Создаём временный файл для промежуточного сохранения
        temp_file = self.output_dir / "vtb_news_temp.json"

        # Если есть временный файл, загружаем его
        if temp_file.exists():
            try:
                with open(temp_file, 'r', encoding='utf-8') as f:
                    temp_news = json.load(f)
                    all_news = temp_news
                    print(f"   🔄 Загружен временный файл: {len(all_news)} новостей")
            except:
                pass

        # Определяем, с какого skip начинать
        if all_news:
            skip = len(all_news)
            print(f"   🔄 Продолжаем со skip={skip}")

        # Создаём прогресс-бар
        pbar = None

        while True:
            print(f"\n📄 Загрузка страницы (skip={skip})...")
            data = self.fetch_page(skip)

            if not data:
                print("   ❌ Не удалось загрузить данные")
                break

            # Получаем общее количество
            if total is None:
                total = data.get('total', 0)
                print(f"   📊 Всего новостей: {total}")
                pbar = tqdm(total=total, desc="Прогресс", unit="нов.")

            # Извлекаем новости
            news_list = data.get('news', [])
            if not news_list:
                print("   ⏹️ Новости закончились")
                break

            # Парсим и фильтруем
            new_items = []
            for item in news_list:
                item_id = item.get('id')

                # Пропускаем уже собранные
                if item_id in existing_ids:
                    continue

                news = self.parse_news_item(item)

                # Проверяем год
                if news['date_normalized']:
                    try:
                        year = int(news['date_normalized'][:4])
                        if year < self.start_year:
                            print(f"\n   ⏹️ Достигнут {year} год (< {self.start_year})")
                            # Сохраняем прогресс перед выходом
                            if new_items:
                                all_news.extend(new_items)
                                self.save_batch(all_news)
                            return all_news
                    except:
                        pass

                new_items.append(news)
                existing_ids.add(item_id)

            if new_items:
                all_news.extend(new_items)
                new_count += len(new_items)

                # Обновляем прогресс-бар
                if pbar:
                    pbar.update(len(new_items))

                print(f"   ✅ Новых: {len(new_items)} (всего: {new_count})")

                # Сохраняем промежуточный результат каждые 500 новостей
                if len(all_news) % 500 == 0:
                    self.save_batch(all_news)
                    print(f"   💾 Промежуточное сохранение: {len(all_news)} новостей")

                    # Сохраняем временный файл для возобновления
                    with open(temp_file, 'w', encoding='utf-8') as f:
                        json.dump(all_news, f, ensure_ascii=False, indent=2)
            else:
                print(f"   ⏭️ Нет новых новостей на этой странице")

            skip += self.per_page

            # Останавливаемся если достигли лимита
            if max_items and len(all_news) >= max_items:
                print(f"\n   ⏹️ Достигнут лимит: {max_items}")
                break

            # Если загрузили все
            if skip >= total:
                break

            time.sleep(0.3)

        if pbar:
            pbar.close()

        # Финальное сохранение
        if all_news:
            self.save_batch(all_news)
            print(f"\n✅ Сохранено {len(all_news)} новостей")

            # Удаляем временный файл
            if temp_file.exists():
                temp_file.unlink()

        # Выводим статистику
        self.print_stats()

        return all_news

    def print_stats(self):
        """Выводит статистику"""
        csv_file = self.output_dir / "vtb_official_news_all.csv"

        if not csv_file.exists():
            print("❌ Файл не найден")
            return

        df = pd.read_csv(csv_file)

        print("\n" + "=" * 70)
        print("📊 СТАТИСТИКА СОБРАННЫХ НОВОСТЕЙ")
        print("=" * 70)
        print(f"   Всего новостей: {len(df):,}")

        # По годам
        if 'date_normalized' in df.columns:
            df['year'] = pd.to_datetime(df['date_normalized'], errors='coerce').dt.year
            print(f"\n   ПО ГОДАМ:")
            for year in sorted(df['year'].dropna().unique()):
                count = (df['year'] == year).sum()
                print(f"      {int(year)}: {count}")

        # С текстом
        if 'text' in df.columns:
            with_text = df[df['text'].notna() & (df['text'].str.len() > 100)]
            print(f"\n   С полным текстом: {len(with_text):,} ({len(with_text) / len(df) * 100:.1f}%)")

        print(f"\n📁 Файл: {csv_file}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--max', type=int, help='Максимум новостей для теста')
    parser.add_argument('--start-year', type=int, default=2020, help='Год начала сбора')

    args = parser.parse_args()

    collector = VtbNewsCollector(start_year=args.start_year)

    if args.max:
        print(f"\n🧪 ТЕСТ: {args.max} новостей")
        collector.collect_all(max_items=args.max)
    else:
        print("\n🚀 ПОЛНЫЙ СБОР (с возобновлением)")
        collector.collect_all()


if __name__ == "__main__":
    main()