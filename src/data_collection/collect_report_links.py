# src/data_collection/collect_report_links.py
"""
Модуль для сбора ссылок на финансовые отчёты компаний со Smart-Lab
Источник: https://smart-lab.ru/q/<TICKER>/f/l/
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import sys
from pathlib import Path
from datetime import datetime
import json

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR
from config.companies import TICKERS, TICKER_TO_COMPANY
from config.settings import REQUEST_DELAY


class ReportLinksCollector:
    """Сборщик ссылок на финансовые отчёты"""

    def __init__(self):
        self.base_url = "https://smart-lab.ru/q"
        self.output_dir = RAW_DATA_DIR / "report_links"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        }

        # Типы отчётов
        self.report_types = {
            'msfo_yearly': 'МСФО годовой',
            'msfo_quarterly': 'МСФО квартальный',
            'rsbu_yearly': 'РСБУ годовой',
            'rsbu_quarterly': 'РСБУ квартальный',
            'presentation': 'Презентация',
            'annual_report': 'Годовой отчёт',
        }

    def get_reports_page(self, ticker):
        """Получает страницу с отчётами"""
        url = f"{self.base_url}/{ticker}/f/l/"
        print(f"\n📄 Загрузка страницы отчётов для {ticker} ({TICKER_TO_COMPANY.get(ticker, '')})")
        print(f"   URL: {url}")

        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.encoding = 'utf-8'

            if response.status_code == 200:
                print(f"   ✅ Страница загружена ({len(response.text)} символов)")
                return response.text
            else:
                print(f"   ❌ Ошибка HTTP {response.status_code}")
                return None
        except Exception as e:
            print(f"   ❌ Ошибка загрузки: {e}")
            return None

    def parse_reports(self, html, ticker):
        """Парсит страницу и извлекает ссылки на отчёты"""
        soup = BeautifulSoup(html, 'html.parser')

        reports = []

        # Ищем все ссылки
        for link in soup.find_all('a', href=True):
            href = link['href']

            # Нас интересуют PDF и ZIP файлы
            if href.endswith('.pdf') or href.endswith('.zip'):
                # Полный URL
                if href.startswith('http'):
                    full_url = href
                else:
                    full_url = f"https://smart-lab.ru{href}"

                # Текст ссылки
                link_text = link.text.strip()

                # Пытаемся найти дату и тип отчёта
                parent = link.find_parent('tr') or link.find_parent('div')
                parent_text = parent.get_text() if parent else ""

                # Ищем дату
                date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', parent_text)
                date = date_match.group(0) if date_match else None

                # Определяем тип отчёта
                report_type = self._detect_report_type(link_text, parent_text)

                # Определяем период (год/квартал)
                period = self._detect_period(link_text, parent_text)

                report = {
                    'ticker': ticker,
                    'company': TICKER_TO_COMPANY.get(ticker, ''),
                    'url': full_url,
                    'filename': href.split('/')[-1],
                    'file_type': 'pdf' if href.endswith('.pdf') else 'zip',
                    'link_text': link_text,
                    'date': date,
                    'report_type': report_type,
                    'period': period,
                    'found_at': datetime.now().isoformat()
                }
                reports.append(report)

        # Убираем дубликаты по URL
        unique_reports = {r['url']: r for r in reports}.values()
        reports = list(unique_reports)

        print(f"   ✅ Найдено {len(reports)} отчётов")

        # Группировка по типам
        type_stats = {}
        for r in reports:
            rt = r['report_type']
            type_stats[rt] = type_stats.get(rt, 0) + 1

        for rt, count in type_stats.items():
            print(f"      {rt}: {count}")

        return reports

    def _detect_report_type(self, link_text, parent_text):
        """Определяет тип отчёта по тексту"""
        text = (link_text + ' ' + parent_text).lower()

        if 'мсфо' in text:
            if 'кварт' in text:
                return 'msfo_quarterly'
            else:
                return 'msfo_yearly'
        elif 'рсбу' in text:
            if 'кварт' in text:
                return 'rsbu_quarterly'
            else:
                return 'rsbu_yearly'
        elif 'презентац' in text:
            return 'presentation'
        elif 'годов' in text and 'отч' in text:
            return 'annual_report'
        else:
            return 'other'

    def _detect_period(self, link_text, parent_text):
        """Определяет период отчёта"""
        text = link_text + ' ' + parent_text

        # Ищем год
        year_match = re.search(r'20\d{2}', text)
        year = year_match.group(0) if year_match else None

        # Ищем квартал
        quarter_match = re.search(r'([1-4])\s*кв', text.lower())
        quarter = quarter_match.group(1) if quarter_match else None

        if quarter and year:
            return f"{year}Q{quarter}"
        elif year:
            return str(year)
        else:
            return None

    def collect_all_tickers(self):
        """Собирает ссылки для всех тикеров"""
        print("\n" + "=" * 70)
        print("🚀 СБОР ССЫЛОК НА ФИНАНСОВЫЕ ОТЧЁТЫ")
        print("=" * 70)

        all_reports = []

        for ticker in TICKERS:
            html = self.get_reports_page(ticker)
            if html:
                reports = self.parse_reports(html, ticker)
                all_reports.extend(reports)

            time.sleep(REQUEST_DELAY)

        # Сохраняем результаты
        if all_reports:
            df = pd.DataFrame(all_reports)

            # Сохраняем в CSV
            csv_file = self.output_dir / "all_report_links.csv"
            df.to_csv(csv_file, index=False, encoding='utf-8')

            # Сохраняем в JSON
            json_file = self.output_dir / "all_report_links.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(all_reports, f, ensure_ascii=False, indent=2)

            print(f"\n✅ Ссылки сохранены:")
            print(f"   CSV: {csv_file}")
            print(f"   JSON: {json_file}")
            print(f"   Всего ссылок: {len(df)}")

            # Статистика
            print(f"\n📊 СТАТИСТИКА ПО КОМПАНИЯМ:")
            for ticker in TICKERS:
                ticker_reports = df[df['ticker'] == ticker]
                print(f"\n   {ticker}: {len(ticker_reports)} отчётов")
                if len(ticker_reports) > 0:
                    type_counts = ticker_reports['report_type'].value_counts()
                    for rt, count in type_counts.items():
                        print(f"      {rt}: {count}")

            return df
        else:
            print("❌ Не удалось собрать ссылки")
            return None


def main():
    """Основная функция"""
    collector = ReportLinksCollector()
    df = collector.collect_all_tickers()

    if df is not None:
        print("\n🎉 Сбор ссылок завершён!")
        print(f"   Всего отчётов: {len(df)}")
        print(f"   Уникальных компаний: {df['ticker'].nunique()}")
        print("\n📁 Файлы сохранены в data/raw/report_links/")


if __name__ == "__main__":
    main()