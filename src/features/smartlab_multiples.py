# src/features/smartlab_multiples.py
import requests
import re
import pandas as pd
import time
import sys
from pathlib import Path
import json

sys.path.append(str(Path(__file__).parent.parent.parent))
from config import FEATURES_DIR
from config import TICKERS, TICKER_TO_COMPANY
from config import REQUEST_DELAY


class SmartLabMultiplesCollector:
    """Сборщик мультипликаторов со Smart-Lab (годовые и квартальные данные)"""

    def __init__(self):
        self.output_dir = FEATURES_DIR
        self.output_dir.mkdir(exist_ok=True)

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        }

        # URL для годовых и квартальных данных
        self.urls = {
            'yearly': {
                'SBER': 'https://smart-lab.ru/q/SBER/f/y/',
                'LKOH': 'https://smart-lab.ru/q/LKOH/f/y/',
                'GAZP': 'https://smart-lab.ru/q/GAZP/f/y/',
                'NVTK': 'https://smart-lab.ru/q/NVTK/f/y/',
                'VTBR': 'https://smart-lab.ru/q/VTBR/f/y/',
            },
            'quarterly': {
                'SBER': 'https://smart-lab.ru/q/SBER/f/q/',
                'LKOH': 'https://smart-lab.ru/q/LKOH/f/q/',
                'GAZP': 'https://smart-lab.ru/q/GAZP/f/q/',
                'NVTK': 'https://smart-lab.ru/q/NVTK/f/q/',
                'VTBR': 'https://smart-lab.ru/q/VTBR/f/q/',
            }
        }

        # Показатели для сбора
        self.target_indicators = {
            'p_e': {'field': 'p_e', 'name': 'P/E'},
            'p_bv': {'field': 'p_bv', 'name': 'P/BV'},
            'ev_ebitda': {'field': 'ev_ebitda', 'name': 'EV/EBITDA'},
            'dividend_yield': {'field': 'div_yield', 'name': 'Див доход'},
            'eps': {'field': 'eps', 'name': 'EPS'},
            'bv_share': {'field': 'bv_share', 'name': 'BV/акцию'},
            'market_cap': {'field': 'market_cap', 'name': 'Капитализация'},
            'revenue': {'field': 'revenue', 'name': 'Выручка'},
            'net_income': {'field': 'net_income', 'name': 'Чистая прибыль'},
            'ebitda': {'field': 'ebitda', 'name': 'EBITDA'},
        }

    def get_page_html(self, url):
        """Загружает HTML страницы"""
        print(f"   Загрузка {url}...")

        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.encoding = 'utf-8'

            if response.status_code == 200:
                print(f"   ✅ Страница загружена")
                return response.text
            else:
                print(f"   ❌ Ошибка HTTP {response.status_code}")
                return None
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            return None

    def extract_periods(self, html, data_type):
        """Извлекает периоды (годы или кварталы) из таблицы"""
        if data_type == 'yearly':
            # Для годовых - ищем года
            pattern = r'<td[^>]*><strong>(20\d{2})</strong></td>'
            periods = re.findall(pattern, html)
            if not periods:
                pattern = r'<th[^>]*>(20\d{2})</th>'
                periods = re.findall(pattern, html)
            periods = sorted(list(set([p for p in periods if 2020 <= int(p) <= 2024])))
        else:
            # Для квартальных - ищем форматы 2024Q1, 2024Q2, etc
            pattern = r'<td[^>]*><strong>(20\d{2}Q[1-4])</strong></td>'
            periods = re.findall(pattern, html)
            if not periods:
                pattern = r'<th[^>]*>(20\d{2}Q[1-4])</th>'
                periods = re.findall(pattern, html)
            # Оставляем только с 2024 года (актуальные данные)
            periods = sorted([p for p in periods if p.startswith('2024') or p.startswith('2025')])

        return periods

    def extract_indicator(self, html, field_name, periods):
        """Извлекает значения для конкретного показателя"""
        pattern = f'<tr[^>]*field="{field_name}"[^>]*>(.*?)</tr>'
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)

        if not match:
            return {}

        row_html = match.group(1)

        # Извлекаем все значения из ячеек
        value_pattern = r'<td[^>]*>(.*?)</td>'
        values = re.findall(value_pattern, row_html, re.DOTALL)

        # Первая ячейка - название показателя, пропускаем её
        values = values[1:] if len(values) > 1 else []

        # Сопоставляем с периодами
        result = {}
        for i, val in enumerate(values):
            if i < len(periods):
                # Очищаем значение от тегов
                clean_val = re.sub(r'<[^>]+>', '', val).strip()
                clean_val = clean_val.replace('&nbsp;', '').replace('\xa0', '')

                # Парсим число
                numeric_val = self._parse_number(clean_val)
                if numeric_val is not None:
                    result[periods[i]] = numeric_val

        return result

    def _parse_number(self, value_str):
        """Парсит число из строки"""
        if not value_str or value_str in ['-', '—', '?', '']:
            return None

        # Убираем проценты и пробелы
        value_str = value_str.replace('%', '').strip()
        value_str = value_str.replace(' ', '').replace('\xa0', '')
        value_str = value_str.replace(',', '.')

        # Ищем число
        match = re.search(r'-?\d+\.?\d*', value_str)
        if match:
            try:
                return float(match.group())
            except:
                return None
        return None

    def collect_ticker_data(self, ticker, data_type='yearly'):
        """Собирает данные по тикеру (годовые или квартальные)"""
        url = self.urls[data_type].get(ticker)
        if not url:
            return None

        type_name = "годовые" if data_type == 'yearly' else "квартальные"
        print(f"\n📊 {ticker} ({TICKER_TO_COMPANY.get(ticker, '')}) - {type_name}")

        html = self.get_page_html(url)
        if not html:
            return None

        # Извлекаем периоды
        periods = self.extract_periods(html, data_type)
        if not periods:
            print(f"   ⚠️ Нет данных")
            return None

        print(f"   📅 Периоды: {', '.join(periods[:5])}{'...' if len(periods) > 5 else ''}")

        # Собираем данные
        rows = []
        for period in periods:
            row = {
                'ticker': ticker,
                'company': TICKER_TO_COMPANY.get(ticker, ''),
                'period': period,
                'data_type': data_type
            }
            rows.append(row)

        # Заполняем показатели
        for key, info in self.target_indicators.items():
            values = self.extract_indicator(html, info['field'], periods)
            if values:
                print(f"   ✅ {info['name']}: {len(values)} значений")
                for row in rows:
                    if row['period'] in values:
                        row[key] = values[row['period']]

        return rows

    def collect_all_data(self):
        """Собирает все данные (годовые и квартальные) по всем тикерам"""
        print("\n" + "=" * 70)
        print("🚀 СБОР МУЛЬТИПЛИКАТОРОВ СО SMART-LAB")
        print("=" * 70)

        all_data = []

        for data_type in ['yearly', 'quarterly']:
            type_name = "ГОДОВЫЕ" if data_type == 'yearly' else "КВАРТАЛЬНЫЕ"
            print(f"\n📌 {type_name} ДАННЫЕ:")

            for ticker in TICKERS:
                data = self.collect_ticker_data(ticker, data_type)
                if data:
                    all_data.extend(data)
                time.sleep(REQUEST_DELAY)

        # Сохраняем результаты
        if all_data:
            df = pd.DataFrame(all_data)

            # Сохраняем в CSV
            csv_file = self.output_dir / "smartlab_multiples_all.csv"
            df.to_csv(csv_file, index=False, encoding='utf-8')

            # Сохраняем в JSON
            json_file = self.output_dir / "smartlab_multiples_all.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)

            print(f"\n✅ Данные сохранены:")
            print(f"   📄 CSV: {csv_file}")
            print(f"   📋 JSON: {json_file}")
            print(f"   📊 Всего записей: {len(df)}")

            # Статистика
            print(f"\n📊 СТАТИСТИКА:")
            for ticker in TICKERS:
                ticker_data = df[df['ticker'] == ticker]
                yearly = ticker_data[ticker_data['data_type'] == 'yearly']
                quarterly = ticker_data[ticker_data['data_type'] == 'quarterly']

                print(f"\n   {ticker}:")
                print(f"      Годовых записей: {len(yearly)}")
                if len(yearly) > 0:
                    print(f"      Период: {yearly['period'].min()}-{yearly['period'].max()}")
                print(f"      Квартальных записей: {len(quarterly)}")
                if len(quarterly) > 0:
                    print(f"      Период: {quarterly['period'].min()}-{quarterly['period'].max()}")

            return df
        else:
            print("❌ Не удалось собрать данные")
            return None


def main():
    """Основная функция"""
    print("\n" + "=" * 70)
    print("🧪 SMART-LAB ПАРСЕР - ПОЛНАЯ ВЕРСИЯ")
    print("=" * 70)

    collector = SmartLabMultiplesCollector()

    # Тест для Газпрома (квартальные)
    print("\n🔍 Тест для GAZP (квартальные):")
    gazp_quarterly = collector.collect_ticker_data('GAZP', 'quarterly')

    if gazp_quarterly:
        print(f"\n   ✅ Собрано {len(gazp_quarterly)} записей")
        print("\n   📊 Пример данных:")
        for row in gazp_quarterly[:3]:
            print(f"      {row['period']}: P/E={row.get('p_e', 'N/A')}, "
                  f"P/B={row.get('p_bv', 'N/A')}, "
                  f"EV/EBITDA={row.get('ev_ebitda', 'N/A')}")

    # Полный сбор
    print("\n🔍 Полный сбор всех данных:")
    df = collector.collect_all_data()

    print("\n" + "=" * 70)
    print("✅ РАБОТА ЗАВЕРШЕНА")
    print("=" * 70)

    if df is not None:
        print("\n🎉 Данные успешно собраны!")
        print(f"   Всего строк: {len(df)}")
        print(f"   Годовых: {len(df[df['data_type'] == 'yearly'])}")
        print(f"   Квартальных: {len(df[df['data_type'] == 'quarterly'])}")
        print("\n📁 Файлы сохранены в data/features/")


if __name__ == "__main__":
    main()