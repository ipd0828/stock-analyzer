# src/data_collection/collect_novatek_news.py

"""
Сбор официальных новостей Новатэка
Просто нажимаем кнопку "Загрузить ещё" N раз и собираем всё
"""

import time
import pandas as pd
import sys
import re
from pathlib import Path
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR


class NovatekNewsCollector:
    """
    Сборщик новостей Новатэка — просто нажимаем кнопку
    """

    def __init__(self):
        self.base_url = "https://www.novatek.ru/ru/press/releases/"
        self.output_dir = RAW_DATA_DIR / "novatek_official_news"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.driver = None

        # Настройки Chrome
        self.options = Options()
        self.options.add_argument("--headless")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--window-size=1920,1080")
        self.options.add_argument("--disable-gpu")
        self.options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

    def start_driver(self):
        """Запускает браузер"""
        print("   🚀 Запуск браузера...")
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=self.options
        )

    def stop_driver(self):
        """Закрывает браузер"""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def click_load_more(self):
        """Нажимает кнопку 'Загрузить ещё'"""
        try:
            load_button = self.driver.find_element(By.CSS_SELECTOR, "div[data-load-more='1'] a")
            if load_button and load_button.is_displayed():
                self.driver.execute_script("arguments[0].click();", load_button)
                time.sleep(2)
                return True
        except NoSuchElementException:
            pass
        return False

    def parse_all_news(self):
        """Парсит все новости на текущей странице"""
        news_items = []

        # Ищем все блоки новостей
        news_blocks = self.driver.find_elements(By.CSS_SELECTOR, "div[data-list-item='1']")

        for block in news_blocks:
            try:
                # Дата
                date_elem = block.find_element(By.CSS_SELECTOR, ".date")
                date_raw = date_elem.text.strip()

                # Заголовок и ссылка
                link = block.find_element(By.CSS_SELECTOR, ".text a")
                title = link.text.strip()
                href = link.get_attribute('href')

                # Извлекаем ID из URL
                id_match = re.search(r'id_4=(\d+)', href)
                news_id = id_match.group(1) if id_match else None

                # Парсим дату
                normalized_date = self._parse_date(date_raw)

                news_items.append({
                    'id': news_id,
                    'ticker': 'NVTK',
                    'company': 'Новатэк',
                    'date_raw': date_raw,
                    'date_normalized': normalized_date,
                    'title': title,
                    'url': href,
                    'source': 'novatek_official',
                    'collected_at': datetime.now().isoformat()
                })

            except Exception as e:
                continue

        return news_items

    def _parse_date(self, date_str):
        """Парсит дату в формате YYYY-MM-DD"""
        if not date_str:
            return None

        months = {
            'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04',
            'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08',
            'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12'
        }

        date_str = date_str.lower().strip()
        for month_rus, month_num in months.items():
            if month_rus in date_str:
                parts = date_str.split()
                if len(parts) >= 3:
                    day = parts[0].zfill(2)
                    year = parts[2]
                    return f"{year}-{month_num}-{day}"

        return None

    def collect_all(self, max_clicks=20):
        """
        Собирает все новости, нажимая кнопку 'Загрузить ещё'
        """
        print("\n" + "=" * 70)
        print("🚀 СБОР НОВОСТЕЙ НОВАТЭКА")
        print(f"   Максимум нажатий: {max_clicks}")
        print("=" * 70)

        self.start_driver()

        try:
            # Загружаем страницу
            print(f"\n📄 Загрузка страницы...")
            self.driver.get(self.base_url)
            time.sleep(5)

            # Парсим первый блок новостей
            all_news = []
            current_news = self.parse_all_news()
            all_news.extend(current_news)
            print(f"   📰 После загрузки: {len(all_news)} новостей")

            # Нажимаем кнопку max_clicks раз
            for click_num in range(1, max_clicks + 1):
                print(f"\n   🔄 Нажатие {click_num}/{max_clicks}...")

                if not self.click_load_more():
                    print(f"   ⏹️ Кнопка 'Загрузить ещё' не найдена")
                    break

                # Парсим новые новости
                new_news = self.parse_all_news()

                # Находим новые (которых ещё нет)
                existing_urls = {item['url'] for item in all_news}
                fresh_news = [item for item in new_news if item['url'] not in existing_urls]

                if fresh_news:
                    all_news.extend(fresh_news)
                    print(f"   📰 +{len(fresh_news)} новостей (всего: {len(all_news)})")
                else:
                    print(f"   ⏹️ Новых новостей нет, останавливаемся")
                    break

            print(f"\n✅ Всего собрано: {len(all_news)} новостей")

            # Сохраняем результаты
            self._save_results(all_news)
            return all_news

        finally:
            self.stop_driver()

    def _save_results(self, news):
        """Сохраняет результаты"""
        if not news:
            print("❌ Нет данных для сохранения")
            return

        df = pd.DataFrame(news)

        csv_file = self.output_dir / "novatek_official_news_all.csv"
        df.to_csv(csv_file, index=False, encoding='utf-8')

        json_file = self.output_dir / "novatek_official_news_all.json"
        df.to_json(json_file, orient='records', force_ascii=False, indent=2)

        print("\n" + "=" * 70)
        print("✅ СБОР НОВОСТЕЙ НОВАТЭКА ЗАВЕРШЁН")
        print("=" * 70)
        print(f"\n📁 Файлы сохранены:")
        print(f"   CSV: {csv_file}")
        print(f"   JSON: {json_file}")
        print(f"   Всего новостей: {len(df)}")

        # Статистика по годам
        if len(df) > 0 and 'date_normalized' in df.columns:
            df['year'] = pd.to_datetime(df['date_normalized'], errors='coerce').dt.year
            year_counts = df['year'].value_counts().sort_index()
            print(f"\n📊 СТАТИСТИКА ПО ГОДАМ:")
            for year, count in year_counts.items():
                print(f"   {int(year)}: {count} новостей")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--clicks', type=int, default=20, help='Максимум нажатий кнопки')

    args = parser.parse_args()

    collector = NovatekNewsCollector()
    collector.collect_all(max_clicks=args.clicks)


if __name__ == "__main__":
    main()