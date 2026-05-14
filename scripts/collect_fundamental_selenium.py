# scripts/collect_fundamental_selenium.py

"""
Сбор фундаментальных данных через Selenium (обходит антибот)
"""

import time
import pandas as pd
import json
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
import sys

sys.path.append(str(Path(__file__).parent.parent))
from config.paths import FEATURES_DIR
from config.companies import TICKERS, TICKER_TO_COMPANY


class SeleniumFundamentalCollector:
    """Сбор фундаментальных данных через Selenium (обходит антибот)"""

    def __init__(self):
        self.output_dir = FEATURES_DIR / "fundamental_data"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # URL для сбора
        self.urls = {
            'SBER': {
                'MSFO_yearly': 'https://smart-lab.ru/q/SBER/f/y/MSFO/',
                'RSBU_yearly': 'https://smart-lab.ru/q/SBER/f/y/RSBU/',
            },
            'GAZP': {
                'MSFO_yearly': 'https://smart-lab.ru/q/GAZP/f/y/MSFO/',
                'RSBU_yearly': 'https://smart-lab.ru/q/GAZP/f/y/RSBU/',
            },
            'LKOH': {
                'MSFO_yearly': 'https://smart-lab.ru/q/LKOH/f/y/MSFO/',
                'RSBU_yearly': 'https://smart-lab.ru/q/LKOH/f/y/RSBU/',
            },
            'NVTK': {
                'MSFO_yearly': 'https://smart-lab.ru/q/NVTK/f/y/MSFO/',
                'RSBU_yearly': 'https://smart-lab.ru/q/NVTK/f/y/RSBU/',
            },
            'VTBR': {
                'MSFO_yearly': 'https://smart-lab.ru/q/VTBR/f/y/MSFO/',
                'RSBU_yearly': 'https://smart-lab.ru/q/VTBR/f/y/RSBU/',
            }
        }

        self.setup_driver()

    def setup_driver(self):
        """Настраивает Chrome драйвер с обходом антибота"""
        options = Options()
        options.add_argument("--headless")  # Убрать если нужен визуальный режим
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Добавляем User-Agent
        options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.wait = WebDriverWait(self.driver, 20)

    def wait_for_table(self, timeout=30):
        """Ждёт загрузки таблицы"""
        try:
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.simple-little-table, table.financials"))
            )
            return True
        except TimeoutException:
            return False

    def parse_table_data(self):
        """Парсит данные из таблицы"""
        try:
            # Находим таблицу
            table = self.driver.find_element(By.CSS_SELECTOR, "table.simple-little-table, table.financials")

            # Извлекаем периоды (годы) из заголовка
            periods = []
            header_row = table.find_element(By.CSS_SELECTOR, "tr.header_row")
            for td in header_row.find_elements(By.CSS_SELECTOR, "td"):
                strong = td.find_elements(By.TAG_NAME, "strong")
                if strong:
                    period_text = strong[0].text.strip()
                    if period_text and period_text.isdigit() and len(period_text) == 4:
                        periods.append(period_text)

            if not periods:
                print("      ⚠️ Не найдены периоды")
                return None

            print(f"      📅 Периоды: {', '.join(periods)}")

            # Собираем данные по строкам
            data = {period: {} for period in periods}

            # Все строки с атрибутом field
            rows = table.find_elements(By.CSS_SELECTOR, "tr[field]")

            for row in rows:
                field_name = row.get_attribute("field")
                if not field_name:
                    continue

                # Название показателя
                th = row.find_element(By.TAG_NAME, "th")
                metric_name = field_name

                # Значения
                values = []
                tds = row.find_elements(By.CSS_SELECTOR, "td")
                for td in tds:
                    # Пропускаем ячейки с графиками
                    if "chartrow" in td.get_attribute("class") or "ltm_spc" in str(td.get_attribute("class")):
                        continue

                    value_text = td.text.strip()
                    if value_text and value_text not in ['—', '', '&nbsp;']:
                        values.append(self.parse_value(value_text))
                    else:
                        values.append(None)

                # Сопоставляем с периодами
                for i, period in enumerate(periods):
                    if i < len(values) and values[i] is not None:
                        data[period][metric_name] = values[i]

            return data

        except Exception as e:
            print(f"      ❌ Ошибка парсинга: {e}")
            return None

    def parse_value(self, value_str):
        """Парсит значение"""
        if not value_str:
            return None

        # Очищаем
        value_str = value_str.replace('\xa0', '').replace(' ', '').replace(',', '.')

        # Проценты
        if '%' in value_str:
            value_str = value_str.replace('%', '')
            try:
                return float(value_str) / 100
            except:
                return None

        try:
            return float(value_str)
        except:
            return None

    def fetch_data(self, ticker, report_type, url):
        """Загружает данные для одного типа отчёта"""
        print(f"   Загрузка {ticker} - {report_type}...")

        try:
            self.driver.get(url)
            time.sleep(3)  # Ждём начальную загрузку

            # Проверяем, не попали ли на антибот
            if "antibot" in self.driver.current_url.lower() or "solar" in self.driver.page_source.lower():
                print(f"      🛡️ Попали на антибот-страницу")
                print(f"      📸 Скриншот сохранён: {self.output_dir}/antibot_{ticker}_{report_type}.png")
                self.driver.save_screenshot(f"{self.output_dir}/antibot_{ticker}_{report_type}.png")
                return None

            # Ждём таблицу
            if not self.wait_for_table():
                print(f"      ⏰ Таймаут ожидания таблицы")
                return None

            # Парсим данные
            data = self.parse_table_data()

            if data:
                periods_with_data = sum(1 for p in data.values() if p)
                print(f"      ✅ {periods_with_data}/{len(data)} периодов с данными")
                return data
            else:
                print(f"      ⚠️ Нет данных")
                return None

        except Exception as e:
            print(f"      ❌ Ошибка: {e}")
            return None

    def collect_all(self):
        """Собирает все данные"""
        print("\n" + "=" * 80)
        print("🚀 СБОР ФУНДАМЕНТАЛЬНЫХ ДАННЫХ (Selenium)")
        print("   МСФО + РСБУ, годовые отчёты")
        print("=" * 80)

        all_results = []

        try:
            for ticker in TICKERS:
                print(f"\n📊 {ticker} ({TICKER_TO_COMPANY.get(ticker, '')})")

                for report_type, url in self.urls[ticker].items():
                    data = self.fetch_data(ticker, report_type, url)

                    if data:
                        for period, metrics in data.items():
                            if metrics:
                                result = {
                                    'ticker': ticker,
                                    'company': TICKER_TO_COMPANY.get(ticker, ''),
                                    'report_type': report_type,
                                    'period': period,
                                    'date_collected': datetime.now().isoformat()
                                }
                                result.update(metrics)
                                all_results.append(result)

                    time.sleep(3)  # Пауза между запросами

        finally:
            self.driver.quit()

        self.save_results(all_results)
        return all_results

    def save_results(self, results):
        """Сохраняет результаты"""
        if not results:
            print("❌ Нет данных для сохранения")
            return

        df = pd.DataFrame(results)

        # Сортируем
        df = df.sort_values(['ticker', 'report_type', 'period'])

        # CSV
        csv_file = self.output_dir / "fundamental_all.csv"
        df.to_csv(csv_file, index=False, encoding='utf-8')

        # JSON
        json_file = self.output_dir / "fundamental_all.json"
        df.to_json(json_file, orient='records', force_ascii=False, indent=2)

        print("\n" + "=" * 80)
        print("✅ ДАННЫЕ СОХРАНЕНЫ")
        print("=" * 80)
        print(f"   CSV: {csv_file}")
        print(f"   JSON: {json_file}")
        print(f"   Всего записей: {len(df)}")

        # Статистика
        print(f"\n📊 ПО ТИПАМ ОТЧЁТОВ:")
        for rt in df['report_type'].unique():
            count = len(df[df['report_type'] == rt])
            print(f"   {rt}: {count}")

        print(f"\n📊 ПО КОМПАНИЯМ:")
        for ticker in df['ticker'].unique():
            count = len(df[df['ticker'] == ticker])
            print(f"   {ticker}: {count}")

        # Проверяем наличие 2025 года
        print(f"\n📊 НАЛИЧИЕ 2025 ГОДА:")
        for ticker in TICKERS:
            df_ticker = df[df['ticker'] == ticker]
            for rt in df_ticker['report_type'].unique():
                has_2025 = '2025' in df_ticker[df_ticker['report_type'] == rt]['period'].astype(str).values
                status = "✅" if has_2025 else "❌"
                print(f"   {ticker} - {rt}: {status}")


def main():
    collector = SeleniumFundamentalCollector()
    collector.collect_all()


if __name__ == "__main__":
    main()