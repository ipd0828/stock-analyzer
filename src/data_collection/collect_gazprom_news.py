# src/data_collection/collect_gazprom_news.py

"""
Сбор официальных новостей Газпрома (с 2020 года)
Новости идут от текущего месяца назад
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
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR


class GazpromNewsCollector:
    """
    Сборщик новостей с сайта Газпрома (с 2020 года)
    """

    def __init__(self, start_year=2020):
        self.base_url = "https://www.gazprom.ru/press/news/"
        self.start_year = start_year
        self.output_dir = RAW_DATA_DIR / "gazprom_official_news"
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
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    def start_driver(self):
        """Запускает браузер"""
        print("   🚀 Запуск браузера...")
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=self.options
        )
        self.wait = WebDriverWait(self.driver, 15)

    def stop_driver(self):
        """Закрывает браузер"""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def get_page(self, url):
        """Загружает страницу по URL"""
        print(f"   Загрузка: {url}")

        try:
            self.driver.get(url)
            time.sleep(3)

            # Ждём загрузки новостей
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".news-list li"))
            )
            return True
        except TimeoutException:
            print(f"      ⚠️ Таймаут загрузки")
            return False
        except Exception as e:
            print(f"      ❌ Ошибка: {e}")
            return False

    def _extract_year_from_url(self, url):
        """Извлекает год из URL"""
        match = re.search(r'/(\d{4})/', url)
        if match:
            return int(match.group(1))
        return None

    def _extract_month_from_url(self, url):
        """Извлекает месяц из URL"""
        match = re.search(r'/(\d{4})/([a-z]+)/', url)
        if match:
            return match.group(2)
        return None

    def parse_page(self, url):
        """Парсит текущую страницу и извлекает новости"""
        news_items = []

        # Проверяем год страницы
        page_year = self._extract_year_from_url(url)
        if page_year and page_year < self.start_year:
            print(f"   ⏹️ Достигнут {page_year} год (< {self.start_year}), останавливаемся")
            return news_items, None, True  # stop_flag = True

        if not self.get_page(url):
            return news_items, None, False

        try:
            # Находим все новости
            articles = self.driver.find_elements(By.CSS_SELECTOR, ".news-list li")

            for article in articles:
                try:
                    # Дата
                    date_elem = article.find_element(By.CSS_SELECTOR, "time.date")
                    date_raw = date_elem.text.strip()

                    # Заголовок и ссылка
                    link_elem = article.find_element(By.CSS_SELECTOR, "h4 a")
                    title = link_elem.text.strip()
                    href = link_elem.get_attribute('href')

                    # Теги (если есть)
                    tags = []
                    tag_elems = article.find_elements(By.CSS_SELECTOR, "a.news-item-tag")
                    for tag in tag_elems:
                        tags.append(tag.text.strip())

                    # Нормализация даты
                    normalized_date = self._normalize_date(date_raw, page_year)

                    news_items.append({
                        'ticker': 'GAZP',
                        'company': 'Газпром',
                        'date_raw': date_raw,
                        'date_normalized': normalized_date,
                        'title': title,
                        'url': href,
                        'tags': '|'.join(tags),
                        'source': 'gazprom_official',
                        'collected_at': datetime.now().isoformat()
                    })

                except NoSuchElementException:
                    continue
                except Exception as e:
                    print(f"      ⚠️ Ошибка парсинга статьи: {e}")
                    continue

            # Ищем ссылку на предыдущий месяц (назад)
            next_url = None
            try:
                next_link = self.driver.find_element(By.CSS_SELECTOR, "p.prev-month-link a")
                next_url = next_link.get_attribute('href')
                if next_url:
                    next_year = self._extract_year_from_url(next_url)
                    print(f"   → Следующая страница: {next_url} (год: {next_year})")

                    # Если следующий год меньше start_year, останавливаемся
                    if next_year and next_year < self.start_year:
                        print(f"   ⏹️ Следующий год {next_year} < {self.start_year}, останавливаемся")
                        return news_items, None, True
            except:
                pass

            return news_items, next_url, False

        except Exception as e:
            print(f"      ❌ Ошибка парсинга страницы: {e}")
            return news_items, None, False

    def _normalize_date(self, date_str, year=None):
        """Нормализует дату в формат YYYY-MM-DD"""
        if not date_str:
            return None

        try:
            # Формат: "22 марта, 23:20"
            parts = date_str.split(',')[0].strip().split()
            if len(parts) == 2:
                day, month_str = parts
                months = {
                    'января': '01', 'февраля': '02', 'марта': '03',
                    'апреля': '04', 'мая': '05', 'июня': '06',
                    'июля': '07', 'августа': '08', 'сентября': '09',
                    'октября': '10', 'ноября': '11', 'декабря': '12'
                }
                month = months.get(month_str.lower())
                if month:
                    if year is None:
                        year = datetime.now().year
                    return f"{year}-{month}-{day.zfill(2)}"
        except:
            pass

        return date_str

    def get_article_text(self, url):
        """Получает полный текст статьи"""
        try:
            self.driver.get(url)
            time.sleep(2)

            text = None
            selectors = [
                ".content_wrapper",
                ".article-content",
                ".news-detail__content",
                ".text-block"
            ]

            for selector in selectors:
                try:
                    content = self.driver.find_element(By.CSS_SELECTOR, selector)
                    text = content.text.strip()
                    if text and len(text) > 200:
                        break
                except:
                    continue

            return text

        except Exception as e:
            print(f"      ❌ Ошибка загрузки текста: {e}")
            return None

    def collect_all(self, max_months=None, get_full_text=False):
        """Собирает все новости, переходя по месяцам назад"""

        print("\n" + "=" * 70)
        print("🚀 СБОР ОФИЦИАЛЬНЫХ НОВОСТЕЙ ГАЗПРОМА (с 2020 года)")
        print("=" * 70)

        self.start_driver()

        try:
            all_news = []
            current_url = self.base_url
            month_count = 0

            while current_url and (max_months is None or month_count < max_months):
                month_count += 1
                print(f"\n📅 Месяц {month_count}: {current_url}")

                news, next_url, stop_flag = self.parse_page(current_url)
                print(f"   Найдено новостей: {len(news)}")

                # Загружаем полные тексты (опционально)
                if get_full_text and news:
                    print(f"   Загрузка текстов...")
                    for i, item in enumerate(tqdm(news, desc="      Тексты", leave=False)):
                        if item['url']:
                            content = self.get_article_text(item['url'])
                            if content:
                                item['content'] = content
                        time.sleep(0.5)

                all_news.extend(news)
                current_url = next_url

                if stop_flag:
                    print(f"\n⏹️ Остановка: достигнут {self.start_year} год")
                    break

                time.sleep(1)

            # Сохраняем результаты
            self._save_results(all_news, get_full_text)
            return all_news

        finally:
            self.stop_driver()

    def _save_results(self, news, with_content=False):
        """Сохраняет результаты"""
        if not news:
            print("❌ Нет данных для сохранения")
            return

        df = pd.DataFrame(news)

        csv_file = self.output_dir / "gazprom_official_news_all.csv"
        df.to_csv(csv_file, index=False, encoding='utf-8')

        json_file = self.output_dir / "gazprom_official_news_all.json"
        df.to_json(json_file, orient='records', force_ascii=False, indent=2)

        print("\n" + "=" * 70)
        print("✅ СБОР НОВОСТЕЙ ГАЗПРОМА ЗАВЕРШЁН")
        print("=" * 70)
        print(f"\n📁 Файлы сохранены:")
        print(f"   CSV: {csv_file}")
        print(f"   JSON: {json_file}")
        print(f"   Всего новостей: {len(df)}")

        # Статистика по годам
        if 'date_normalized' in df.columns:
            df['year'] = pd.to_datetime(df['date_normalized'], errors='coerce').dt.year
            print(f"\n📊 СТАТИСТИКА ПО ГОДАМ:")
            years = sorted(df['year'].dropna().unique())
            for year in years:
                count = (df['year'] == year).sum()
                print(f"   {int(year)}: {count} новостей")

        return df


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-months', type=int, help='Максимум месяцев для теста')
    parser.add_argument('--full-text', action='store_true', help='Собирать полные тексты')
    parser.add_argument('--start-year', type=int, default=2020, help='Год начала сбора (по умолчанию 2020)')

    args = parser.parse_args()

    collector = GazpromNewsCollector(start_year=args.start_year)

    if args.max_months:
        print(f"\n🧪 ТЕСТ: {args.max_months} месяцев")
        collector.collect_all(max_months=args.max_months, get_full_text=args.full_text)
    else:
        print("\n🚀 ПОЛНЫЙ СБОР (с 2020 года)")
        collector.collect_all(get_full_text=args.full_text)


if __name__ == "__main__":
    main()