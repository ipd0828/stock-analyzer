# src/data_collection/collect_lenta_headers.py
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime, timedelta
import time
import json
import os
import re
from pathlib import Path
from tqdm import tqdm
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from config import COMPANIES, CHROME_OPTIONS, USER_AGENT


class HeaderCollector:
    """Сбор заголовков с Lenta.ru (Owl-дизайн 2026)"""

    def __init__(self):
        self.options = Options()
        self.options.add_argument("--headless")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--window-size=1920,1080")
        self.options.add_argument("--disable-gpu")
        self.options.add_argument("--disable-extensions")
        self.options.add_argument(f"--user-agent={USER_AGENT}")

        self.driver = None
        self.companies = COMPANIES
        self.logs = []

        self.archive_dir = Path("data/lenta_archive")
        self.debug_dir = Path("data/debug_logs")
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.debug_dir.mkdir(parents=True, exist_ok=True)

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        self.logs.append(log_entry)
        print(log_entry)

    def save_logs(self, date_str):
        log_file = self.debug_dir / f"{date_str}_debug.json"
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(self.logs, f, ensure_ascii=False, indent=2)
        self.logs = []

    def start_driver(self):
        if not self.driver:
            self.log("Запуск браузера...")
            self.driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=self.options
            )
            self.driver.set_page_load_timeout(15)  # меньше — быстрее перезапуск
            self.driver.set_script_timeout(15)

    def stop_driver(self):
        if self.driver:
            self.log("Остановка браузера")
            self.driver.quit()
            self.driver = None

    def get_total_materials(self):
        try:
            total_elem = self.driver.find_element(By.CSS_SELECTOR, ".archive-page__total")
            total_text = total_elem.text
            numbers = re.findall(r'\d+', total_text)
            if numbers:
                return int(numbers[0])
        except:
            pass
        return None

    def get_next_page_url(self):
        """Ищет кнопку Дальше в новом дизайне"""
        try:
            time.sleep(0.5)
            # Новый дизайн: a.loadmore с href
            buttons = self.driver.find_elements(By.CSS_SELECTOR, "a.loadmore")
            for btn in buttons:
                text = btn.text.strip()
                href = btn.get_attribute('href')
                if "Дальше" in text and href:
                    return href
            return None
        except:
            return None

    def parse_day(self, date):
        """Парсит один день"""
        year, month, day_num = date.year, date.month, date.day
        date_str = date.strftime("%Y-%m-%d")

        filename = self.archive_dir / f"{date_str}.json"
        if filename.exists():
            self.log(f"📅 {date_str}: уже существует, пропускаем", "SKIP")
            return None

        self.log(f"\n{'='*70}")
        self.log(f"📅 {date_str}")
        self.log(f"{'='*70}")

        base_url = f"https://lenta.ru/{year}/{month:02d}/{day_num:02d}/"
        current_url = base_url
        page_num = 1
        all_articles = []
        seen_titles = set()

        try:
            ## Первая страница — без защиты от таймаута
            self.driver.get(current_url)
            time.sleep(3)

            total_materials = self.get_total_materials()
            if total_materials:
                self.log(f"Всего материалов: {total_materials}")


            while True:
                self.log(f"Страница {page_num}")

                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".archive-page__item h3"))
                    )
                except:
                    pass

                items = self.driver.find_elements(By.CSS_SELECTOR, ".archive-page__item")
                self.log(f"  Элементов: {len(items)}")

                types_count = {}
                page_new = 0

                for item in items:
                    try:
                        item_class = item.get_attribute('class') or ''

                        if '_more' in item_class:
                            continue

                        if '_news' in item_class:
                            item_type = "news"
                            link = item.find_element(By.CSS_SELECTOR, "a.card-full-news")
                            title_elem = item.find_element(By.CSS_SELECTOR, "h3.card-full-news__title")
                        elif '_article' in item_class:
                            item_type = "article"
                            link = item.find_element(By.CSS_SELECTOR, "a.card-full-other")
                            title_elem = item.find_element(By.CSS_SELECTOR, "h3.card-full-other__title")
                        elif '_extlink' in item_class:
                            item_type = "extlink"
                            link = item.find_element(By.CSS_SELECTOR, "a.card-full-other")
                            title_elem = item.find_element(By.CSS_SELECTOR, "h3.card-full-other__title")
                        elif '_twz' in item_class:
                            item_type = "twz"
                            link = item.find_element(By.CSS_SELECTOR, "a.card-full-other")
                            title_elem = item.find_element(By.CSS_SELECTOR, "h3.card-full-other__title")
                        else:
                            try:
                                link = item.find_element(By.CSS_SELECTOR, "a")
                                title_elem = item.find_element(By.CSS_SELECTOR, "h3")
                                item_type = "other"
                            except:
                                continue

                        types_count[item_type] = types_count.get(item_type, 0) + 1

                        url = link.get_attribute('href')
                        title = title_elem.text.strip()

                        if not title or title in seen_titles:
                            continue

                        seen_titles.add(title)
                        page_new += 1

                        try:
                            time_elem = item.find_element(By.CSS_SELECTOR, "time")
                            pub_time = time_elem.text.strip()
                        except:
                            pub_time = ""

                        try:
                            rubric = item.find_element(By.CSS_SELECTOR, ".card-full-news__rubric").text.strip()
                        except:
                            rubric = ""

                        all_articles.append({
                            'url': url,
                            'title': title,
                            'time': pub_time,
                            'rubric': rubric,
                            'type': item_type,
                            'page': page_num
                        })

                    except:
                        continue

                self.log(f"  Типы: {types_count}")
                self.log(f"  Новых: {page_new}, всего: {len(all_articles)}")

                if total_materials:
                    self.log(f"  Прогресс: {len(all_articles)}/{total_materials}")

                # Сохраняем промежуточный результат каждые 10 страниц
                if page_num % 10 == 0:
                    temp_file = self.archive_dir / f"{date_str}_temp.json"
                    with open(temp_file, 'w', encoding='utf-8') as f:
                        json.dump({'date': date_str, 'collected': len(all_articles), 'articles': all_articles}, f, ensure_ascii=False)
                    self.log(f"  💾 Промежуточное сохранение ({len(all_articles)} статей)")

                if page_new == 0:
                    self.log(f"  ⏹️ Новых заголовков нет — сбор завершён")
                    break

                next_url = self.get_next_page_url()

                if next_url and next_url != current_url:
                    self.log(f"  ➡️ Страница {page_num + 1}")
                    current_url = next_url

                    # Загружаем с защитой от таймаута
                    loaded = False
                    for attempt in range(3):
                        try:
                            self.driver.get(current_url)
                            WebDriverWait(self.driver, 10).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, ".archive-page__item h3"))
                            )
                            time.sleep(1)
                    if not loaded:
                        self.log(f"  ⏹️ Не удалось загрузить страницу {page_num+1}")
                        break

                    page_num += 1
                else:
                    self.log(f"  ⏹️ Кнопка Дальше не найдена")
                    break

            # Сохраняем финальный результат
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump({
                    'date': date_str,
                    'total_materials': total_materials,
                    'collected': len(all_articles),
                    'pages': page_num,
                    'articles': all_articles
                }, f, ensure_ascii=False, indent=2)

            # Удаляем временный файл если есть
            temp_file = self.archive_dir / f"{date_str}_temp.json"
            if temp_file.exists():
                temp_file.unlink()

            self.log(f"✅ Сохранено: {filename} ({len(all_articles)} статей)")
            self.save_logs(date_str)
            return all_articles

        except Exception as e:
            self.log(f"❌ Ошибка: {e}", "ERROR")
            self.save_logs(f"{date_str}_ERROR")
            return None


    def collect_period(self, start_date, end_date):
        print("\n" + "=" * 70)
        print("🚀 СБОР ЗАГОЛОВКОВ LENTA.RU")
        print(f"Период: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}")
        print(f"Дней: {(end_date - start_date).days + 1}")
        print("=" * 70)

        self.start_driver()

        try:
            current_date = start_date
            pbar = tqdm(total=(end_date - start_date).days + 1, desc="Прогресс", unit="день")

            stats = {'processed': 0, 'success': 0, 'empty': 0, 'errors': 0}

            while current_date <= end_date:
                result = self.parse_day(current_date)

                stats['processed'] += 1
                if result is None:
                    stats['errors'] += 1
                elif len(result) == 0:
                    stats['empty'] += 1
                else:
                    stats['success'] += 1

                pbar.set_postfix(stats)
                pbar.update(1)
                current_date += timedelta(days=1)
                time.sleep(1)

            pbar.close()

            print(f"\n✅ ГОТОВО: {stats['success']} дней, {stats['errors']} ошибок")
            return stats

        finally:
            self.stop_driver()


def main():
    collector = HeaderCollector()
    test_date = datetime(2026, 3, 19)
    collector.parse_day(test_date)


if __name__ == "__main__":
    main()