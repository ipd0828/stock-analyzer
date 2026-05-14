# src/data_collection/collect_reports_from_smartlab.py

"""
Сбор ссылок на финансовые отчёты со Smart-Lab
Парсинг из div.externals_col
"""

import time
import pandas as pd
import requests
import re
import sys
from pathlib import Path
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR
from config.companies import TICKERS, TICKER_TO_COMPANY


class SmartLabReportsCollector:
    """
    Сборщик финансовых отчётов со Smart-Lab
    """

    def __init__(self):
        self.base_url = "https://smart-lab.ru/q"
        self.output_dir = RAW_DATA_DIR / "smartlab_reports"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.driver = None
        self.wait = None

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
        self.wait = WebDriverWait(self.driver, 20)

    def stop_driver(self):
        """Закрывает браузер"""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def get_reports_page(self, ticker):
        """Загружает страницу с отчётами"""
        url = f"{self.base_url}/{ticker}/f/l/"
        print(f"\n📄 Загрузка: {url}")
        self.driver.get(url)
        time.sleep(3)

        # Ждём загрузки контента
        try:
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".externals_col, .content_wrapper"))
            )
            return True
        except TimeoutException:
            print(f"   ⚠️ Таймаут загрузки для {ticker}")
            return False

    def parse_reports(self, ticker):
        """Парсит ссылки на отчёты из div.externals_col"""
        reports = []

        try:
            # Ищем все блоки с отчётами
            report_blocks = self.driver.find_elements(By.CSS_SELECTOR, ".externals_col")
            if not report_blocks:
                print(f"   ❌ Блоки отчётов не найдены")
                return reports

            for block in report_blocks:
                # Определяем тип отчёта из заголовка h2
                try:
                    header = block.find_element(By.TAG_NAME, "h2")
                    report_category = header.text.strip()
                except:
                    report_category = "unknown"

                # Ищем все ссылки в блоке
                links = block.find_elements(By.TAG_NAME, "a")

                for link in links:
                    try:
                        url = link.get_attribute('href')
                        if not url:
                            continue

                        # Пропускаем ссылки на другие страницы smart-lab
                        if 'smart-lab.ru' in url and '/q/' in url and '/f/l' not in url:
                            continue

                        title = link.text.strip()
                        if not title:
                            continue

                        # Определяем год и период из текста ссылки или URL
                        period = self._extract_period(title, url)

                        # Определяем формат файла
                        file_format = self._detect_format(url)

                        # Определяем подтип отчёта (годовой, квартальный, презентация)
                        report_type = self._detect_report_type(report_category, title)

                        reports.append({
                            'ticker': ticker,
                            'company': TICKER_TO_COMPANY.get(ticker, ''),
                            'category': report_category,
                            'report_type': report_type,
                            'period': period,
                            'title': title,
                            'url': url,
                            'file_format': file_format,
                            'collected_at': datetime.now().isoformat()
                        })

                    except Exception as e:
                        continue

            return reports

        except Exception as e:
            print(f"   ❌ Ошибка парсинга: {e}")
            return reports

    def _extract_period(self, title, url):
        """Извлекает период из названия или URL"""
        # Ищем год
        year_match = re.search(r'20\d{2}', title)
        if not year_match:
            year_match = re.search(r'20\d{2}', url)
        year = year_match.group(0) if year_match else None

        # Ищем квартал
        quarter_match = re.search(r'[1-4]\s*[кК][вВ]|[1-4]Q', title)
        if not quarter_match:
            quarter_match = re.search(r'[1-4]\s*[кК][вВ]|[1-4]Q', url)

        if quarter_match:
            quarter = re.search(r'[1-4]', quarter_match.group(0)).group(0)
            if year:
                return f"{year}Q{quarter}"
            return f"Q{quarter}"

        # Ищем месяц
        month_match = re.search(r'янв|фев|мар|апр|май|июн|июл|авг|сен|окт|ноя|дек', title, re.IGNORECASE)
        if month_match and year:
            return f"{year}_{month_match.group(0)}"

        return year if year else "unknown"

    def _detect_format(self, url):
        """Определяет формат файла"""
        if '.pdf' in url.lower():
            return 'PDF'
        elif '.xlsx' in url.lower() or '.xls' in url.lower():
            return 'EXCEL'
        elif '.zip' in url.lower():
            return 'ZIP'
        elif '.doc' in url.lower():
            return 'DOC'
        else:
            return 'LINK'

    def _detect_report_type(self, category, title, url):
        """Определяет тип отчёта по заголовку, категории и URL"""
        text = f"{category} {title}".lower()
        url_lower = url.lower()

        # Годовые отчёты
        if 'годовой отчет' in text or 'annual report' in text or 'годовой отчёт' in text:
            return 'annual'
        if 'годовая' in category.lower() and 'отчет' in category.lower():
            return 'annual'

        # Квартальные отчёты
        if 'квартальный' in text or 'quarterly' in text:
            return 'quarterly'
        if 'кв' in text and ('отчет' in text or 'отчёт' in text):
            return 'quarterly'

        # Презентации
        if 'презентац' in text or 'presentation' in text:
            return 'presentation'

        # МСФО
        if 'мсфо' in text or 'ifrs' in text:
            return 'ifrs'

        # РСБУ
        if 'рсбу' in text or 'ras' in text or 'ras' in url_lower:
            return 'ras'

        # По умолчанию
        return 'other'

    def parse_reports(self, ticker):
        """Парсит ссылки на отчёты из div.externals_col"""
        reports = []

        try:
            report_blocks = self.driver.find_elements(By.CSS_SELECTOR, ".externals_col")
            if not report_blocks:
                print(f"   ❌ Блоки отчётов не найдены")
                return reports

            for block in report_blocks:
                try:
                    header = block.find_element(By.TAG_NAME, "h2")
                    report_category = header.text.strip()
                except:
                    report_category = "unknown"

                links = block.find_elements(By.TAG_NAME, "a")

                for link in links:
                    try:
                        url = link.get_attribute('href')
                        if not url:
                            continue

                        # Пропускаем внутренние ссылки smart-lab
                        if 'smart-lab.ru' in url and '/q/' in url and '/f/l' not in url:
                            continue

                        title = link.text.strip()
                        if not title:
                            continue

                        # Определяем период
                        period = self._extract_period(title, url)

                        # Определяем тип отчёта
                        report_type = self._detect_report_type(report_category, title, url)

                        # Определяем формат
                        file_format = self._detect_format(url)

                        reports.append({
                            'ticker': ticker,
                            'company': TICKER_TO_COMPANY.get(ticker, ''),
                            'category': report_category,
                            'report_type': report_type,
                            'period': period,
                            'title': title,
                            'url': url,
                            'file_format': file_format,
                            'collected_at': datetime.now().isoformat()
                        })

                    except Exception as e:
                        continue

            return reports

        except Exception as e:
            print(f"   ❌ Ошибка парсинга: {e}")
            return reports

    def collect_all(self, download_files=False, limit_per_company=None):
        """Собирает ссылки на отчёты для всех компаний"""
        print("\n" + "=" * 70)
        print("🚀 СБОР ФИНАНСОВЫХ ОТЧЁТОВ СО SMART-LAB")
        print(f"   Скачивание файлов: {'Да' if download_files else 'Нет'}")
        print("=" * 70)

        self.start_driver()

        all_reports = []

        try:
            for ticker in TICKERS:
                print(f"\n📊 {ticker} ({TICKER_TO_COMPANY.get(ticker, '')})")

                if not self.get_reports_page(ticker):
                    continue

                reports = self.parse_reports(ticker)

                if limit_per_company:
                    reports = reports[:limit_per_company]

                print(f"   📄 Найдено отчётов: {len(reports)}")

                # Выводим первые 5 для проверки
                for r in reports[:5]:
                    print(f"      {r['period']} | {r['report_type']} | {r['title'][:50]}...")

                # Скачиваем файлы
                if download_files:
                    for report in tqdm(reports, desc="   Скачивание"):
                        self.download_report(
                            report['url'],
                            report['ticker'],
                            report['report_type'],
                            report['period']
                        )
                        time.sleep(1)

                all_reports.extend(reports)
                time.sleep(2)

            # Сохраняем список отчётов
            self._save_reports_list(all_reports)
            return all_reports

        finally:
            self.stop_driver()

    def download_report(self, url, ticker, report_type, period):
        """Скачивает файл отчёта"""
        if not url:
            return None

        # Формируем имя файла
        period_clean = re.sub(r'[^\w\-]', '_', str(period))
        filename = f"{ticker}_{report_type}_{period_clean}.pdf"
        filepath = self.output_dir / filename

        if filepath.exists():
            print(f"      ⏭️ Файл уже существует: {filename}")
            return filepath

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=30, stream=True)
            response.raise_for_status()

            # Проверяем Content-Type
            content_type = response.headers.get('content-type', '')
            if 'pdf' not in content_type and 'application' not in content_type:
                print(f"      ⚠️ Не PDF: {content_type}")
                return None

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"      ✅ Скачан: {filename} ({filepath.stat().st_size / 1024:.1f} KB)")
            return filepath

        except Exception as e:
            print(f"      ❌ Ошибка скачивания: {e}")
            return None

    def _save_reports_list(self, reports):
        """Сохраняет список отчётов"""
        if not reports:
            print("❌ Нет данных для сохранения")
            return

        df = pd.DataFrame(reports)

        csv_file = self.output_dir / "reports_list.csv"
        df.to_csv(csv_file, index=False, encoding='utf-8')

        json_file = self.output_dir / "reports_list.json"
        df.to_json(json_file, orient='records', force_ascii=False, indent=2)

        print("\n" + "=" * 70)
        print("✅ СБОР ЗАВЕРШЁН")
        print("=" * 70)
        print(f"\n📁 Файлы сохранены:")
        print(f"   CSV: {csv_file}")
        print(f"   JSON: {json_file}")
        print(f"   Всего отчётов: {len(df)}")

        print(f"\n📊 ПО КОМПАНИЯМ:")
        for ticker in TICKERS:
            count = len(df[df['ticker'] == ticker])
            print(f"   {ticker}: {count}")

        print(f"\n📊 ПО ТИПАМ ОТЧЁТОВ:")
        for rt, count in df['report_type'].value_counts().head(10).items():
            print(f"   {rt}: {count}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', action='store_true', help='Скачивать файлы отчётов')
    parser.add_argument('--limit', type=int, help='Ограничить количество отчётов на компанию')
    parser.add_argument('--test', action='store_true', help='Тестовый режим (только Сбер)')

    args = parser.parse_args()

    collector = SmartLabReportsCollector()

    if args.test:
        print("\n🧪 ТЕСТ: только Сбер")
        collector.start_driver()
        try:
            ticker = 'SBER'
            if collector.get_reports_page(ticker):
                reports = collector.parse_reports(ticker)
                print(f"\n📄 Найдено отчётов: {len(reports)}")
                for r in reports[:15]:
                    print(f"   {r['period']:12} | {r['report_type']:12} | {r['title'][:50]}...")
        finally:
            collector.stop_driver()
    else:
        collector.collect_all(download_files=args.download, limit_per_company=args.limit)


if __name__ == "__main__":
    main()