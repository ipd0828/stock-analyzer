# src/data_collection/collect_fundamental_smartlab.py

"""
Сбор всех фундаментальных данных со Smart-Lab для всех компаний
Поддерживает: МСФО (годовые/квартальные) и РСБУ (годовые/квартальные)
Сохраняет в структурированном формате для дальнейших расчётов
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

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import FEATURES_DIR, RAW_DATA_DIR
from config.companies import TICKERS, TICKER_TO_COMPANY

# Типы отчётов для сбора
REPORT_TYPES = [
    {'name': 'msfo_yearly', 'url_path': 'f/y/MSFO/', 'description': 'МСФО годовой'},
    {'name': 'msfo_quarterly', 'url_path': 'f/q/MSFO/', 'description': 'МСФО квартальный'},
    {'name': 'rsbu_yearly', 'url_path': 'f/y/RSBU/', 'description': 'РСБУ годовой'},
    {'name': 'rsbu_quarterly', 'url_path': 'f/q/RSBU/', 'description': 'РСБУ квартальный'},
]


class SmartLabFundamentalCollector:
    """Сборщик фундаментальных данных со Smart-Lab"""

    def __init__(self):
        self.output_dir = FEATURES_DIR / "fundamental_raw"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.all_data = []
        self.driver = None

        # Настройки Chrome
        self.options = Options()
        self.options.add_argument("--headless")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--window-size=1920,1080")
        self.options.add_argument("--disable-gpu")
        self.options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
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

    def get_page(self, url):
        """Загружает страницу"""
        try:
            self.driver.get(url)
            time.sleep(3)
            return True
        except Exception as e:
            print(f"      ❌ Ошибка загрузки: {e}")
            return False

    def get_table_data(self):
        """Извлекает данные из таблицы на странице"""
        try:
            # Ждём загрузки таблицы
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.simple-little-table, table.financials"))
            )
        except TimeoutException:
            return None

        try:
            table = self.driver.find_element(By.CSS_SELECTOR, "table.simple-little-table, table.financials")

            # Извлекаем периоды (годы/кварталы) из заголовка
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

            # Собираем все показатели
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
                    if value_text and value_text not in ['—', '', '&nbsp;', '?']:
                        values.append(self._parse_value(value_text))
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

    def _parse_value(self, value_str):
        """Парсит значение из строки"""
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

        # Числа с суффиксами (млрд, млн)
        if 'млрд' in value_str:
            value_str = value_str.replace('млрд', '')
            try:
                return float(value_str) * 1e9
            except:
                return None

        if 'млн' in value_str:
            value_str = value_str.replace('млн', '')
            try:
                return float(value_str) * 1e6
            except:
                return None

        # Обычное число
        try:
            return float(value_str)
        except:
            return None

    def collect_company_data(self, ticker):
        """Собирает все данные для одной компании"""
        print(f"\n📊 {ticker} ({TICKER_TO_COMPANY.get(ticker, '')})")

        company_data = []

        for report in REPORT_TYPES:
            url = f"https://smart-lab.ru/q/{ticker}/{report['url_path']}"
            print(f"   🔄 {report['description']}...")

            if not self.get_page(url):
                continue

            data = self.get_table_data()

            if data:
                for period, metrics in data.items():
                    if metrics:
                        record = {
                            'ticker': ticker,
                            'company': TICKER_TO_COMPANY.get(ticker, ''),
                            'report_type': report['name'],
                            'report_description': report['description'],
                            'period': period,
                            'collected_at': datetime.now().isoformat()
                        }
                        record.update(metrics)
                        company_data.append(record)
                        print(f"      ✅ {period}: {len(metrics)} показателей")
            else:
                print(f"      ⚠️ Нет данных")

            time.sleep(2)

        return company_data

    def collect_all(self):
        """Собирает данные для всех компаний"""
        print("\n" + "=" * 80)
        print("🚀 СБОР ФУНДАМЕНТАЛЬНЫХ ДАННЫХ СО SMART-LAB")
        print("=" * 80)

        self.start_driver()

        try:
            for ticker in TICKERS:
                data = self.collect_company_data(ticker)
                self.all_data.extend(data)

                # Промежуточное сохранение
                self._save_intermediate(ticker, data)

                time.sleep(3)

        finally:
            self.stop_driver()

        # Финальное сохранение
        self._save_final()

        return self.all_data

    def _save_intermediate(self, ticker, data):
        """Промежуточное сохранение"""
        if not data:
            return

        df = pd.DataFrame(data)
        temp_file = self.output_dir / f"{ticker}_temp.csv"
        df.to_csv(temp_file, index=False, encoding='utf-8')
        print(f"   💾 Промежуточно сохранено: {temp_file}")

    def _save_final(self):
        """Финальное сохранение всех данных"""
        if not self.all_data:
            print("❌ Нет данных для сохранения")
            return

        df = pd.DataFrame(self.all_data)

        # Сохраняем CSV
        csv_file = self.output_dir / "fundamental_all_raw.csv"
        df.to_csv(csv_file, index=False, encoding='utf-8')

        # Сохраняем JSON
        json_file = self.output_dir / "fundamental_all_raw.json"
        df.to_json(json_file, orient='records', force_ascii=False, indent=2)

        print("\n" + "=" * 80)
        print("✅ СБОР ЗАВЕРШЁН")
        print("=" * 80)
        print(f"\n📁 Файлы сохранены:")
        print(f"   CSV: {csv_file}")
        print(f"   JSON: {json_file}")
        print(f"   Всего записей: {len(df)}")

        # Статистика
        print(f"\n📊 СТАТИСТИКА ПО КОМПАНИЯМ:")
        for ticker in TICKERS:
            ticker_data = df[df['ticker'] == ticker]
            print(f"   {ticker}: {len(ticker_data)} записей")

        print(f"\n📊 ПО ТИПАМ ОТЧЁТОВ:")
        for rt in df['report_type'].unique():
            count = len(df[df['report_type'] == rt])
            print(f"   {rt}: {count}")


def main():
    collector = SmartLabFundamentalCollector()
    collector.collect_all()


if __name__ == "__main__":
    main()