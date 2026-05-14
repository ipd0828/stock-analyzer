# src/data_collection/collect_sber_official_news_selenium.py

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import time
import sys
from pathlib import Path
from datetime import datetime
import re

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR
from config.settings import REQUEST_DELAY


class SberOfficialNewsSeleniumCollector:
    """
    Сборщик официальных новостей с сайта Сбербанка через Selenium
    """

    def __init__(self):
        self.url = "https://www.sberbank.com/ru/investor-relations/ir/news"
        self.output_dir = RAW_DATA_DIR / "sber_official_news"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Настройка Chrome
        self.options = Options()
        self.options.add_argument("--headless")  # Без GUI
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--window-size=1920,1080")
        self.options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        self.driver = None
        self.wait = None

    def start_driver(self):
        """Запускает браузер"""
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=self.options
        )
        self.wait = WebDriverWait(self.driver, 10)

    def stop_driver(self):
        """Закрывает браузер"""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def wait_for_news(self):
        """Ждёт загрузки новостей"""
        try:
            # Ждём появления хотя бы одной новости
            self.wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, "news-archive-list__article"))
            )
            return True
        except TimeoutException:
            print("   ⚠️ Таймаут ожидания новостей")
            return False

    def get_total_pages(self):
        """Определяет общее количество страниц"""
        try:
            # Ищем пагинацию
            paginator = self.driver.find_element(By.CSS_SELECTOR, "nav.list-paginator")
            pages = paginator.find_elements(By.CSS_SELECTOR, "li[role='button']")

            max_page = 0
            for page in pages:
                text = page.text.strip()
                if text and text.isdigit():
                    max_page = max(max_page, int(text))

            if max_page > 0:
                print(f"   📊 Всего страниц: {max_page}")
                return max_page

        except Exception as e:
            print(f"   ⚠️ Не удалось определить страницы: {e}")

        return 1

    def go_to_page(self, page_num):
        """Переходит на указанную страницу"""
        if page_num == 1:
            self.driver.get(self.url)
        else:
            self.driver.get(f"{self.url}?page={page_num}")

        time.sleep(2)  # Даём время на загрузку
        return self.wait_for_news()

    def extract_news_from_page(self):
        """Извлекает новости с текущей страницы"""
        news_items = []

        # Находим все статьи
        articles = self.driver.find_elements(By.CLASS_NAME, "news-archive-list__article")

        for article in articles:
            try:
                # Дата
                date_elem = article.find_element(By.CSS_SELECTOR, ".sta-date__date-text")
                date_text = date_elem.text.strip() if date_elem else None

                # Заголовок и ссылка
                link_elem = article.find_element(By.CSS_SELECTOR, "a.news-archive-list__title")
                title_elem = link_elem.find_element(By.CSS_SELECTOR, ".dk-sbol-text")
                title = title_elem.text.strip() if title_elem else None

                href = link_elem.get_attribute('href')

                # UUID из ссылки
                uuid = None
                if href:
                    match = re.search(r'newsID=([a-f0-9-]+)', href)
                    if match:
                        uuid = match.group(1)

                # Парсим дату
                news_date = None
                if date_text:
                    try:
                        # Пример: "11 марта 2026"
                        news_date = datetime.strptime(date_text.replace(' года', ''), '%d %B %Y')
                    except:
                        pass

                news_items.append({
                    'uuid': uuid,
                    'date': news_date.isoformat() if news_date else None,
                    'date_raw': date_text,
                    'title': title,
                    'url': href,
                    'collected_at': datetime.now().isoformat()
                })

            except Exception as e:
                print(f"      ⚠️ Ошибка парсинга статьи: {e}")
                continue

        return news_items

    def collect_all_news(self, max_pages=None):
        """
        Собирает все новости
        """
        print("\n" + "=" * 70)
        print("🚀 СБОР ОФИЦИАЛЬНЫХ НОВОСТЕЙ СБЕРБАНКА (SELENIUM)")
        print("=" * 70)

        all_news = []

        try:
            self.start_driver()

            # Загружаем первую страницу
            print(f"\n📄 Загрузка страницы 1...")
            if not self.go_to_page(1):
                print("❌ Не удалось загрузить первую страницу")
                return []

            # Определяем общее количество страниц
            total_pages = self.get_total_pages()
            if max_pages:
                total_pages = min(total_pages, max_pages)
                print(f"   🧪 Тестовый режим: максимум {max_pages} страниц")

            # Собираем новости со всех страниц
            for page in range(1, total_pages + 1):
                if page > 1:
                    print(f"\n📄 Загрузка страницы {page}...")
                    if not self.go_to_page(page):
                        print(f"   ⚠️ Не удалось загрузить страницу {page}")
                        continue

                news = self.extract_news_from_page()
                print(f"   ✅ Найдено новостей: {len(news)}")
                all_news.extend(news)

                # Промежуточное сохранение
                if page % 5 == 0:
                    self._save_progress(all_news, page)

                time.sleep(REQUEST_DELAY)

        finally:
            self.stop_driver()

        # Финальное сохранение
        self._save_results(all_news)
        return all_news

    def _save_progress(self, news, page):
        """Промежуточное сохранение"""
        df = pd.DataFrame(news)
        temp_file = self.output_dir / f"sber_news_temp_page_{page}.csv"
        df.to_csv(temp_file, index=False, encoding='utf-8')
        print(f"   💾 Промежуточно сохранено {len(news)} новостей")

    def _save_results(self, news):
        """Финальное сохранение"""
        if not news:
            print("❌ Нет данных для сохранения")
            return

        df = pd.DataFrame(news)

        csv_file = self.output_dir / "sber_official_news_all.csv"
        json_file = self.output_dir / "sber_official_news_all.json"

        df.to_csv(csv_file, index=False, encoding='utf-8')
        df.to_json(json_file, orient='records', force_ascii=False, indent=2)

        print("\n" + "=" * 70)
        print("✅ СБОР ЗАВЕРШЁН")
        print("=" * 70)
        print(f"\n📁 Файлы сохранены:")
        print(f"   CSV: {csv_file}")
        print(f"   JSON: {json_file}")
        print(f"   Всего новостей: {len(df)}")

        # Статистика
        print(f"\n📊 СТАТИСТИКА:")

        # Группировка по годам
        df['year'] = pd.to_datetime(df['date']).dt.year
        year_stats = df['year'].value_counts().sort_index()
        for year, count in year_stats.items():
            print(f"   {year}: {count} новостей")


def main():
    """Основная функция."""
    collector = SberOfficialNewsSeleniumCollector()

    # Тест (3 страницы)
    #print("\n🧪 ТЕСТОВЫЙ РЕЖИМ")
    #collector.collect_all_news(max_pages=3)

    # Полный сбор (раскомментируй)
    print("\n🚀 ПОЛНЫЙ СБОР")
    collector.collect_all_news()


if __name__ == "__main__":
    main()