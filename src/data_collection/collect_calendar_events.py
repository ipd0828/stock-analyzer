# src/data_collection/collect_calendar_events.py

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import sys
import re
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR
from config.settings import REQUEST_DELAY


class CalendarEventsCollector:
    """
    Сборщик событий из календаря Smart-Lab.
    Собирает: дату, страну, описание, тикер, сумму дивидендов, ссылку.
    """

    def __init__(self):
        self.base_url = "https://smart-lab.ru/calendar/stocks"
        self.output_dir = RAW_DATA_DIR / "calendar_events"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        }

        self.event_types = [
            ('stocks_otsechka', 'dividends', 'Дивиденды'),
            ('company_reports', 'reports', 'Акции - отчет'),
            ('stocks_gosa', 'meetings', 'Собрания акционеров'),
            ('stocks_dirs', 'board', 'Акции - совет дир.'),
            ('stocks_ipo', 'ipo', 'Акции - IPO'),
            ('stocks_other', 'other', 'Акции - другое')
        ]

        self.start_date = "01.01.2020"
        self.end_date = datetime.now().strftime("%d.%m.%Y")

    def extract_dividend_amount(self, description: str) -> dict:
        """
        Извлекает размер дивиденда из описания.
        Возвращает сумму и валюту.
        """
        if not description:
            return {'amount': None, 'currency': None}

        # Паттерны для поиска сумм
        patterns = [
            r'(\d+(?:[.,]\d+)?)\s*(?:руб|р\.?)',  # 1000 руб, 15.5 р
            r'(\d+(?:[.,]\d+)?)\s*(?:₽)',  # 1000 ₽
            r'дивиденд[^\d]*(\d+(?:[.,]\d+)?)',  # дивиденд 12.5
            r'(\d+(?:[.,]\d+)?)\s*(?:USD|\$)',  # 0.5 USD
        ]

        for pattern in patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(',', '.')
                try:
                    amount = float(amount_str)

                    # Определяем валюту
                    if 'usd' in description.lower() or '$' in description:
                        currency = 'USD'
                    elif '₽' in description or 'руб' in description.lower():
                        currency = 'RUB'
                    else:
                        currency = 'RUB'  # По умолчанию рубли

                    return {'amount': amount, 'currency': currency}
                except:
                    pass

        return {'amount': None, 'currency': None}

    def extract_event_details(self, description: str) -> dict:
        """
        Извлекает детальную информацию о событии.
        """
        details = {
            'has_amount': False,
            'amount': None,
            'currency': None,
            'event_type_detail': None,
            'ticker': None
        }

        # Извлекаем тикер
        ticker_match = re.search(r'([A-Z]+):', description)
        if ticker_match:
            details['ticker'] = ticker_match.group(1)

        # Для дивидендов
        if 'дивиденд' in description.lower() or 'дивид' in description.lower():
            details['event_type_detail'] = 'dividend'
            div_info = self.extract_dividend_amount(description)
            if div_info['amount']:
                details['has_amount'] = True
                details['amount'] = div_info['amount']
                details['currency'] = div_info['currency']

        # Для отчётов
        elif 'отчет' in description.lower():
            details['event_type_detail'] = 'report'

        # Для собраний
        elif 'собрание' in description.lower() or 'gosa' in description.lower():
            details['event_type_detail'] = 'meeting'

        return details

    def get_total_pages(self, event_type: str) -> int:
        """Определяет общее количество страниц."""
        url = f"{self.base_url}/{event_type}/from_{self.start_date}/to_{self.end_date}/page1/"

        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.encoding = 'utf-8'

            if response.status_code != 200:
                return 0

            soup = BeautifulSoup(response.text, 'html.parser')
            pagination = soup.find('div', id='pagination') or soup.find('div', class_='pagination1')

            if not pagination:
                return 1

            next_link = pagination.find('a', string='сюда →')
            if next_link:
                href = next_link.get('href', '')
                match = re.search(r'/page(\d+)/', href)
                if match:
                    return int(match.group(1))

            return 1

        except Exception:
            return 0

    def parse_page(self, html: str, event_type: str, event_category: str, page_num: int):
        """Парсит страницу календаря."""
        soup = BeautifulSoup(html, 'html.parser')
        events = []

        table = soup.find('table', class_='simple-little-table')
        if not table:
            return events

        rows = table.find_all('tr')[1:]

        for row in rows:
            try:
                cols = row.find_all('td')
                if len(cols) < 4:
                    continue

                # Дата
                date = cols[0].get_text(strip=True)

                # Страна
                country_img = cols[1].find('img')
                country = country_img.get('title') if country_img else None

                # Описание
                desc_cell = cols[2]
                desc_link = desc_cell.find('a')
                description = desc_link.get_text(strip=True) if desc_link else desc_cell.get_text(strip=True)
                event_url = desc_link.get('href') if desc_link else None

                # Извлекаем детали
                details = self.extract_event_details(description)

                # Внешняя ссылка
                external_link = None
                ext_link_tag = cols[3].find('a')
                if ext_link_tag:
                    external_link = ext_link_tag.get('href')

                events.append({
                    'event_type': event_type,
                    'category': event_category,
                    'page': page_num,
                    'date': date,
                    'country': country,
                    'description': description,
                    'ticker': details.get('ticker'),
                    'event_detail': details.get('event_type_detail'),
                    'has_dividend_amount': details.get('has_amount'),
                    'dividend_amount': details.get('amount'),
                    'dividend_currency': details.get('currency'),
                    'event_url': event_url,
                    'external_link': external_link,
                    'collected_at': datetime.now().isoformat()
                })

            except Exception as e:
                print(f"      ⚠️ Ошибка: {e}")
                continue

        return events

    def collect_all(self, test_mode=False):
        """Собирает все события."""
        print("\n" + "=" * 70)
        print("🚀 СБОР СОБЫТИЙ ИЗ КАЛЕНДАРЯ")
        print("=" * 70)

        all_results = []

        for event_type, event_category, display_name in self.event_types:
            print(f"\n📊 {display_name}")

            if test_mode:
                # Тест: только первая страница
                url = f"{self.base_url}/{event_type}/from_{self.start_date}/to_{self.end_date}/page1/"
                response = requests.get(url, headers=self.headers, timeout=15)
                response.encoding = 'utf-8'

                if response.status_code == 200:
                    events = self.parse_page(response.text, event_type, event_category, 1)
                    all_results.extend(events)
                    print(f"   ✅ Найдено {len(events)} событий")
            else:
                # Полный сбор
                total_pages = self.get_total_pages(event_type)
                print(f"   📄 Всего страниц: {total_pages}")

                for page in range(1, total_pages + 1):
                    url = f"{self.base_url}/{event_type}/from_{self.start_date}/to_{self.end_date}/page{page}/"

                    try:
                        response = requests.get(url, headers=self.headers, timeout=15)
                        response.encoding = 'utf-8'

                        if response.status_code == 200:
                            events = self.parse_page(response.text, event_type, event_category, page)
                            all_results.extend(events)
                            print(f"      Страница {page}: {len(events)} событий")
                        else:
                            print(f"      ❌ Страница {page}: HTTP {response.status_code}")

                    except Exception as e:
                        print(f"      ❌ Страница {page}: {e}")

                    time.sleep(REQUEST_DELAY)

                print(f"   ✅ Всего: {len([e for e in all_results if e['category'] == event_category])} событий")

        # Сохраняем результаты
        self._save_results(all_results, test_mode)
        return all_results

    def _save_results(self, results, test_mode):
        """Сохраняет результаты."""
        if not results:
            print("❌ Нет данных")
            return

        df = pd.DataFrame(results)

        suffix = "_test" if test_mode else "_all"
        csv_file = self.output_dir / f"calendar_events{suffix}.csv"
        json_file = self.output_dir / f"calendar_events{suffix}.json"

        df.to_csv(csv_file, index=False, encoding='utf-8')
        df.to_json(json_file, orient='records', force_ascii=False, indent=2)

        print("\n" + "=" * 70)
        print("✅ СБОР ЗАВЕРШЁН")
        print("=" * 70)
        print(f"\n📁 Файлы сохранены:")
        print(f"   CSV: {csv_file}")
        print(f"   JSON: {json_file}")
        print(f"   Всего событий: {len(df)}")

        # Статистика по дивидендам
        dividends = df[df['category'] == 'dividends']
        with_amount = dividends[dividends['has_dividend_amount']]

        print(f"\n📊 СТАТИСТИКА ПО ДИВИДЕНДАМ:")
        print(f"   Всего дивидендных событий: {len(dividends)}")
        print(f"   С указанной суммой: {len(with_amount)} ({len(with_amount) / len(dividends) * 100:.1f}%)")

        if len(with_amount) > 0:
            print(f"\n   Примеры дивидендов:")
            for _, row in with_amount.head(5).iterrows():
                print(f"   {row['date']}: {row['ticker']} - {row['dividend_amount']} {row['dividend_currency']}")


def main():
    collector = CalendarEventsCollector()

    # Тест
    #print("\n🧪 ТЕСТОВЫЙ РЕЖИМ")
    #collector.collect_all(test_mode=True)

    # Полный сбор (раскомментируй)
    print("\n🚀 ПОЛНЫЙ СБОР")
    collector.collect_all(test_mode=False)


if __name__ == "__main__":
    main()