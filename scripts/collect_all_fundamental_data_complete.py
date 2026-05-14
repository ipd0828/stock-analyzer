# scripts/collect_all_fundamental_data_complete.py

"""
Полный сбор всех фундаментальных данных со Smart-Lab
- Годовые и квартальные отчёты (МСФО и РСБУ)
- Все доступные показатели (bank_assets, capital, debt, cash, number_of_shares и т.д.)
- Сохраняет в CSV для дальнейшего использования
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


class CompleteFundamentalCollector:
    """Полный сбор всех фундаментальных данных со Smart-Lab"""

    def __init__(self):
        self.output_dir = FEATURES_DIR / "fundamental_data"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Все типы отчётов для сбора
        self.report_types = [
            ('MSFO_yearly', '/f/y/MSFO/'),
            ('MSFO_quarterly', '/f/q/MSFO/'),
            ('RSBU_yearly', '/f/y/RSBU/'),
            ('RSBU_quarterly', '/f/q/RSBU/'),
        ]

        self.all_data = []
        self.setup_driver()

    def setup_driver(self):
        """Настраивает Chrome драйвер"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        self.wait = WebDriverWait(self.driver, 30)

    def wait_for_table(self):
        """Ждёт загрузки таблицы"""
        try:
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.simple-little-table, table.financials"))
            )
            return True
        except TimeoutException:
            return False

    def parse_table(self, ticker, report_type):
        """Парсит всю таблицу и возвращает все показатели"""

        try:
            table = self.driver.find_element(By.CSS_SELECTOR, "table.simple-little-table, table.financials")

            # Извлекаем периоды (годы/кварталы)
            periods = []
            header_row = table.find_element(By.CSS_SELECTOR, "tr.header_row")
            for td in header_row.find_elements(By.CSS_SELECTOR, "td"):
                strong = td.find_elements(By.TAG_NAME, "strong")
                if strong:
                    period_text = strong[0].text.strip()
                    if period_text:
                        periods.append(period_text)

            if not periods:
                return None

            print(f"      📅 Периоды: {', '.join(periods[:6])}{'...' if len(periods) > 6 else ''}")

            # Собираем все данные
            data = {period: {} for period in periods}

            # Проходим по всем строкам с атрибутом field
            rows = table.find_elements(By.CSS_SELECTOR, "tr[field]")

            for row in rows:
                field_name = row.get_attribute("field")
                if not field_name:
                    continue

                # Получаем все значения
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
                        data[period][field_name] = values[i]

            return data

        except Exception as e:
            print(f"      ❌ Ошибка парсинга: {e}")
            return None

    def parse_value(self, value_str):
        """Парсит значение"""
        if not value_str:
            return None

        value_str = value_str.replace('\xa0', '').replace(' ', '').replace(',', '.')

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

    def fetch_company_data(self, ticker):
        """Собирает все данные для одной компании"""
        print(f"\n📊 {ticker} ({TICKER_TO_COMPANY.get(ticker, '')})")

        for report_name, url_path in self.report_types:
            url = f"https://smart-lab.ru/q/{ticker}{url_path}"
            print(f"   🔄 {report_name}...")

            try:
                self.driver.get(url)
                time.sleep(3)

                if not self.wait_for_table():
                    print(f"      ⏰ Таймаут, пропускаем")
                    continue

                data = self.parse_table(ticker, report_name)

                if data:
                    for period, metrics in data.items():
                        if metrics:
                            record = {
                                'ticker': ticker,
                                'company': TICKER_TO_COMPANY.get(ticker, ''),
                                'report_type': report_name,
                                'period': period,
                                'date_collected': datetime.now().isoformat()
                            }
                            record.update(metrics)
                            self.all_data.append(record)
                            print(f"      ✅ {period}: {len(metrics)} показателей")
                    else:
                        print(f"      ⚠️ Нет данных")
                else:
                    print(f"      ❌ Не удалось распарсить")

                time.sleep(2)

            except Exception as e:
                print(f"      ❌ Ошибка: {e}")

    def collect_all(self):
        """Собирает данные для всех компаний"""
        print("=" * 80)
        print("🚀 ПОЛНЫЙ СБОР ФУНДАМЕНТАЛЬНЫХ ДАННЫХ")
        print("   Все типы отчётов, все показатели")
        print("=" * 80)

        for ticker in TICKERS:
            self.fetch_company_data(ticker)

        self.driver.quit()
        self.save_results()

    def save_results(self):
        """Сохраняет все собранные данные"""
        if not self.all_data:
            print("❌ Нет данных для сохранения")
            return

        df = pd.DataFrame(self.all_data)

        # Сохраняем CSV
        csv_file = self.output_dir / "fundamental_all_complete.csv"
        df.to_csv(csv_file, index=False, encoding='utf-8')

        # Сохраняем JSON
        json_file = self.output_dir / "fundamental_all_complete.json"
        df.to_json(json_file, orient='records', force_ascii=False, indent=2)

        print("\n" + "=" * 80)
        print("✅ СБОР ЗАВЕРШЁН")
        print("=" * 80)
        print(f"   CSV: {csv_file}")
        print(f"   JSON: {json_file}")
        print(f"   Всего записей: {len(df)}")
        print(f"   Колонок: {len(df.columns)}")

        # Статистика
        print(f"\n📊 ПО ТИПАМ ОТЧЁТОВ:")
        for rt in df['report_type'].unique():
            count = len(df[df['report_type'] == rt])
            print(f"   {rt}: {count}")

        print(f"\n📊 ПО КОМПАНИЯМ:")
        for ticker in df['ticker'].unique():
            count = len(df[df['ticker'] == ticker])
            print(f"   {ticker}: {count}")

        # Проверяем наличие ключевых колонок
        key_cols = ['bank_assets', 'capital', 'number_of_shares', 'debt', 'cash']
        print(f"\n📊 НАЛИЧИЕ КЛЮЧЕВЫХ КОЛОНОК:")
        for col in key_cols:
            if col in df.columns:
                non_null = df[col].notna().sum()
                print(f"   ✅ {col}: {non_null} записей с данными")
            else:
                print(f"   ❌ {col}: отсутствует")


if __name__ == "__main__":
    collector = CompleteFundamentalCollector()
    collector.collect_all()