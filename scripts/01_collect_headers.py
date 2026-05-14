# scripts/01_collect_headers.py
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime, timedelta
import time
import json
import os
import re
from tqdm import tqdm
import sys

# Определяем папку для данных
DATA_DIR = os.environ.get('LENTA_DATA_DIR', 'data')
print(f"📁 Директория данных: {DATA_DIR}")

# Создаём необходимые папки
os.makedirs(f"{DATA_DIR}/lenta_archive", exist_ok=True)
os.makedirs(f"{DATA_DIR}/lenta_logs", exist_ok=True)
os.makedirs(f"{DATA_DIR}/debug_logs", exist_ok=True)

# Импортируем настройки
try:
    from project_config import START_DATE, END_DATE, COMPANIES
    print(f"✅ Загружены настройки из config.py")
    print(f"   Период: {START_DATE.strftime('%Y-%m-%d')} - {END_DATE.strftime('%Y-%m-%d')}")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("   Создай файл project_config.py в корне проекта с настройками:")
    print("   from config.settings import START_DATE, END_DATE")
    print("   from config.companies import COMPANIES")
    sys.exit(1)


class HeaderCollector:
    """Сбор заголовков с Lenta.ru (полная рабочая версия)"""

    def __init__(self):
        self.options = Options()
        self.options.add_argument("--headless")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--window-size=1920,1080")
        self.options.add_argument("--disable-gpu")
        self.options.add_argument("--disable-extensions")

        self.driver = None
        self.companies = COMPANIES
        self.logs = []

        os.makedirs("data/lenta_archive", exist_ok=True)
        os.makedirs("data/lenta_logs", exist_ok=True)
        os.makedirs("data/debug_logs", exist_ok=True)

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        self.logs.append(log_entry)
        print(log_entry)

    def save_logs(self, date_str):
        log_file = f"data/debug_logs/{date_str}_debug.json"
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

    def stop_driver(self):
        if self.driver:
            self.log("Остановка браузера")
            self.driver.quit()
            self.driver = None

    def get_total_materials(self):
        try:
            total_elem = self.driver.find_element(By.CSS_SELECTOR, ".archive-page__total")
            total_text = total_elem.text
            self.log(f"Найден элемент .archive-page__total: '{total_text}'")
            numbers = re.findall(r'\d+', total_text)
            if numbers:
                return int(numbers[0])
        except Exception as e:
            self.log(f"Не удалось получить total: {e}", "ERROR")
        return None

    def get_next_page_url(self):
        try:
            time.sleep(1)
            buttons = self.driver.find_elements(By.CSS_SELECTOR, ".loadmore__button")
            self.log(f"Найдено кнопок .loadmore__button: {len(buttons)}")

            for i, button in enumerate(buttons):
                button_text = ""
                for _ in range(4):
                    button_text = button.text.strip()
                    if button_text:
                        break
                    time.sleep(0.5)

                self.log(f"  Кнопка {i + 1}: текст='{button_text}'")

                if "Дальше" in button_text:
                    parent = button.find_element(By.XPATH, "..")
                    next_url = parent.get_attribute('href')
                    self.log(f"  ✅ Найдена кнопка 'Дальше' → {next_url}")
                    return next_url

            self.log("  ❌ Кнопка 'Дальше' не найдена")
            return None
        except Exception as e:
            self.log(f"Ошибка при поиске следующей страницы: {e}", "ERROR")
            return None

    def parse_day(self, date):
        year, month, day_num = date.year, date.month, date.day
        date_str = date.strftime("%Y-%m-%d")

        filename = f"data/lenta_archive/{date_str}.json"
        if os.path.exists(filename):
            self.log(f"📅 {date_str}: файл уже существует, пропускаем", "SKIP")
            return None

        self.log(f"\n{'=' * 70}")
        self.log(f"📅 НАЧАЛО ОБРАБОТКИ ДНЯ: {date_str}")
        self.log(f"{'=' * 70}")

        base_url = f"https://lenta.ru/{year}/{month:02d}/{day_num:02d}/"
        self.log(f"Базовый URL: {base_url}")

        current_url = base_url
        page_num = 1
        all_articles = []
        seen_urls = set()
        page_stats = {}

        try:
            self.driver.get(current_url)
            time.sleep(2)
            self.log(f"Страница загружена")

            total_materials = self.get_total_materials()
            if total_materials:
                self.log(f"Всего материалов по сайту: {total_materials}")
            else:
                self.log("Не удалось определить общее количество материалов", "WARN")

            while True:
                self.log(f"\n--- СТРАНИЦА {page_num} ---")

                items = self.driver.find_elements(By.CSS_SELECTOR, ".archive-page__item")
                self.log(f"Найдено элементов .archive-page__item: {len(items)}")

                types_count = {}
                page_new = 0

                for item in items:
                    try:
                        item_class = item.get_attribute('class')

                        if '_article' in item_class:
                            item_type = "article"
                        elif '_news' in item_class:
                            item_type = "news"
                        elif '_extlink' in item_class:
                            item_type = "extlink"
                        elif '_photo' in item_class:
                            item_type = "photo"
                        else:
                            item_type = "other"

                        types_count[item_type] = types_count.get(item_type, 0) + 1

                        link = item.find_element(By.CSS_SELECTOR, "a")
                        url = link.get_attribute('href')
                        title = item.find_element(By.CSS_SELECTOR, "h3").text.strip()

                        try:
                            time_elem = item.find_element(By.CSS_SELECTOR, "time")
                            pub_time = time_elem.text.strip()
                        except:
                            pub_time = ""

                        try:
                            rubric = item.find_element(By.CSS_SELECTOR, ".card-full-news__rubric").text.strip()
                        except:
                            rubric = ""

                        if url not in seen_urls:
                            seen_urls.add(url)
                            page_new += 1
                            all_articles.append({
                                'url': url,
                                'title': title,
                                'time': pub_time,
                                'rubric': rubric,
                                'type': item_type,
                                'page': page_num
                            })

                    except Exception as e:
                        self.log(f"Ошибка парсинга элемента: {e}", "ERROR")
                        continue

                self.log(f"Типы на странице: {types_count}")
                self.log(f"Новых URL на странице: {page_new}")
                self.log(f"Всего уникальных статей после страницы: {len(all_articles)}")

                page_stats[page_num] = {
                    'total_found': len(items),
                    'new_urls': page_new,
                    'types': types_count,
                    'running_total': len(all_articles)
                }

                if total_materials:
                    self.log(f"Прогресс: {len(all_articles)}/{total_materials}")

                self.log("Поиск следующей страницы...")
                next_url = self.get_next_page_url()

                if next_url and next_url != current_url:
                    self.log(f"➡️ Переход на страницу {page_num + 1}")
                    self.log(f"   URL: {next_url}")
                    current_url = next_url
                    self.driver.get(current_url)
                    time.sleep(2)
                    page_num += 1
                else:
                    self.log("⏹️ Достигнут конец - нет следующей страницы")
                    break

            self.log(f"\n{'=' * 70}")
            self.log(f"📊 ИТОГ ДНЯ {date_str}")
            self.log(f"{'=' * 70}")
            self.log(f"Всего собрано статей: {len(all_articles)}")
            self.log(f"Всего страниц: {page_num}")

            if total_materials:
                diff = total_materials - len(all_articles)
                self.log(f"По сайту должно быть: {total_materials}")
                self.log(f"Разница: {diff}")

            self.log("Сохранение данных...")

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump({
                    'date': date_str,
                    'total_materials': total_materials,
                    'collected': len(all_articles),
                    'pages': page_num,
                    'page_stats': page_stats,
                    'articles': all_articles
                }, f, ensure_ascii=False, indent=2)

            self.log(f"✅ Данные сохранены в {filename}")

            # Считаем упоминания компаний
            company_stats = {comp: 0 for comp in self.companies}
            for article in all_articles:
                title_lower = article['title'].lower()
                for comp, keywords in self.companies.items():
                    if any(keyword in title_lower for keyword in keywords):
                        company_stats[comp] += 1

            log_entry = {
                'date': date_str,
                'total_articles': len(all_articles),
                'total_materials': total_materials,
                'company_mentions': company_stats,
                'pages': page_num
            }

            log_file = f"data/lenta_logs/mentions_{date.year}_{date.month:02d}.json"
            existing = []
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)

            existing.append(log_entry)
            existing.sort(key=lambda x: x['date'])

            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

            if sum(company_stats.values()) > 0:
                self.log(f"Упоминания компаний: {company_stats}")

            self.save_logs(date_str)

            return all_articles

        except Exception as e:
            self.log(f"КРИТИЧЕСКАЯ ОШИБКА: {e}", "ERROR")
            self.save_logs(f"{date_str}_ERROR")
            return None

    def collect_period(self, start_date, end_date):
        print("\n" + "=" * 70)
        print("🚀 ЭТАП 1: СБОР ЗАГОЛОВКОВ LENTA.RU")
        print("=" * 70)
        print(f"Период: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}")
        total_days = (end_date - start_date).days + 1
        print(f"Всего дней: {total_days}")
        print("=" * 70)

        self.start_driver()

        try:
            current_date = start_date
            pbar = tqdm(total=total_days, desc="Прогресс", unit="день")

            stats = {
                'processed': 0,
                'success': 0,
                'empty': 0,
                'errors': 0,
                'skipped': 0
            }

            while current_date <= end_date:
                result = self.parse_day(current_date)

                stats['processed'] += 1
                if result is None:
                    stats['errors'] += 1
                elif result == []:
                    stats['empty'] += 1
                elif result:
                    stats['success'] += 1

                pbar.set_postfix(stats)
                pbar.update(1)

                current_date += timedelta(days=1)
                time.sleep(1)

            pbar.close()

            print("\n" + "=" * 70)
            print("✅ СБОР ЗАГОЛОВКОВ ЗАВЕРШЁН")
            print("=" * 70)
            print(f"📊 Статистика:")
            print(f"   Дней обработано: {stats['processed']}")
            print(f"   Дней с данными: {stats['success']}")
            print(f"   Дней без статей: {stats['empty']}")
            print(f"   Ошибок: {stats['errors']}")
            print(f"   Пропущено: {stats['skipped']}")

            return stats

        finally:
            self.stop_driver()


def main():
    collector = HeaderCollector()
    collector.collect_period(START_DATE, END_DATE)


if __name__ == "__main__":
    main()