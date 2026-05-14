# src/data_collection/collect_company_news_links.py (ФИНАЛЬНАЯ ВЕРСИЯ 3.0)

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import sys
from pathlib import Path
from datetime import datetime
import json
import re

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR
from config.companies import TICKERS, TICKER_TO_COMPANY
from config.settings import REQUEST_DELAY


class CompanyNewsCollector:
    """Сборщик ссылок на новости компаний со Smart-Lab"""

    def __init__(self):
        self.base_url = "https://smart-lab.ru/forum/news"
        self.output_dir = RAW_DATA_DIR / "news_links"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        self.target_tickers = TICKERS

    def get_page(self, ticker: str, page: int = 1):
        """Загружает страницу с новостями"""
        if page == 1:
            url = f"{self.base_url}/{ticker}/"
        else:
            url = f"{self.base_url}/{ticker}/page{page}/"  # ВАЖНО: без слеша после page!

        print(f"   ⏳ Загружаю страницу {page}: {url}")

        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            resp.encoding = 'utf-8'

            if resp.status_code == 200:
                print(f"      ✅ Успешно ({len(resp.text)} bytes)")
                return resp.text
            else:
                print(f"      ❌ Ошибка HTTP {resp.status_code}")
                return None

        except Exception as e:
            print(f"      ❌ Ошибка загрузки: {e}")
            return None

    def get_total_pages(self, html: str) -> int:
        """Определяет общее количество страниц по ссылке '→'"""
        soup = BeautifulSoup(html, 'html.parser')
        pagination = soup.find('div', id='pagination') or soup.find('div', class_='pagination1')

        if not pagination:
            return 1

        # Ищем ссылку "→"
        next_link = pagination.find('a', string='→')
        if not next_link:
            # Если не нашли по тексту, ищем по классу
            last_links = pagination.find_all('a', class_='last')
            if last_links:
                next_link = last_links[-1]

        if next_link:
            href = next_link.get('href', '')
            print(f"      Найдена ссылка: {href}")

            # Простой способ: ищем число в конце URL
            # Например: /page125/ или /page/125/
            match = re.search(r'page[/]?(\d+)', href)
            if match:
                last_page = int(match.group(1))
                print(f"      → Последняя страница: {last_page}")
                return last_page

        # Если ничего не нашли, ищем максимальное число в пагинации
        max_page = 0
        for link in pagination.find_all('a'):
            text = link.get_text(strip=True)
            if text.isdigit():
                max_page = max(max_page, int(text))

        print(f"      → Использую максимальное число: {max_page}")
        return max_page if max_page > 0 else 1

        # 3. Если не нашли, ищем максимальное число
        max_page = 0
        for link in pagination.find_all('a'):
            text = link.get_text(strip=True)
            if text.isdigit():
                max_page = max(max_page, int(text))

        print(f"      → Использую максимальное число: {max_page}")
        return max_page if max_page > 0 else 1

    def parse_page(self, html: str, ticker: str, page_num: int):
        """Парсит страницу и возвращает список новостей"""
        soup = BeautifulSoup(html, 'html.parser')
        news_list = soup.find('ul', class_='temp_headers')

        if not news_list:
            return []

        items = news_list.find_all('li')
        news_items = []

        for item in items:
            try:
                # Комментарии
                comments_elem = item.find('b')
                comments = None
                if comments_elem:
                    text = comments_elem.get_text(strip=True).replace('\xa0', '').strip()
                    match = re.search(r'(\d+)', text)
                    if match:
                        comments = int(match.group(1))

                # Дата (в формате ДД/ММ)
                date = None
                for child in item.children:
                    if hasattr(child, 'name') and child.name == 'b':
                        continue
                    if isinstance(child, str) and child.strip():
                        date = child.strip()
                        break

                # Ссылка и заголовок
                link = item.find('a')
                if not link:
                    continue

                href = link.get('href')
                if not href:
                    continue

                # Полный URL
                if href.startswith('/'):
                    full_url = f"https://smart-lab.ru{href}"
                else:
                    full_url = href

                title = link.get('title') or link.get_text(strip=True)

                news_items.append({
                    'ticker': ticker,
                    'company': TICKER_TO_COMPANY.get(ticker, ''),
                    'page': page_num,
                    'url': full_url,
                    'article_id': href.split('/')[-1].replace('.php', ''),
                    'title': title[:500] if title else '',
                    'date': date,
                    'comments': comments,
                    'found_at': datetime.now().isoformat()
                })
            except Exception as e:
                print(f"      Ошибка парсинга: {e}")
                continue

        return news_items

    def collect_company_news(self, ticker: str):
        """Собирает все новости для компании от 1 до последней страницы"""
        print(f"\n📰 Сбор новостей для {ticker} ({TICKER_TO_COMPANY.get(ticker, '')})")

        # 1. Загружаем первую страницу
        first_page = self.get_page(ticker, 1)
        if not first_page:
            print(f"   ❌ Не удалось загрузить первую страницу")
            return []

        total_pages = self.get_total_pages(first_page)
        print(f"   📊 Всего страниц: {total_pages}")

        # 2. Парсим первую страницу
        all_news = []
        news_items = self.parse_page(first_page, ticker, 1)
        if news_items:
            print(f"   Страница 1: {len(news_items)} новостей")
            all_news.extend(news_items)

        # 3. Идём по всем остальным страницам
        for page in range(2, total_pages + 1):
            html = self.get_page(ticker, page)
            if not html:
                print(f"   ⚠️ Страница {page} не загрузилась, продолжаем...")
                continue

            news_items = self.parse_page(html, ticker, page)
            if news_items:
                print(f"   Страница {page}: {len(news_items)} новостей")
                all_news.extend(news_items)
            else:
                print(f"   Страница {page}: новостей нет")

            time.sleep(REQUEST_DELAY)

        print(f"   ✅ Всего собрано: {len(all_news)} новостей")
        return all_news

    def collect_all(self):
        """Собирает новости для всех компаний"""
        print("\n" + "=" * 70)
        print("🚀 СБОР НОВОСТЕЙ КОМПАНИЙ")
        print("=" * 70)

        all_results = []

        for ticker in self.target_tickers:
            news = self.collect_company_news(ticker)
            if news:
                all_results.extend(news)

                # Промежуточное сохранение
                temp_df = pd.DataFrame(all_results)
                temp_path = self.output_dir / "news_temp.csv"
                temp_df.to_csv(temp_path, index=False, encoding='utf-8')
                print(f"   💾 Промежуточно сохранено {len(all_results)} новостей")

            time.sleep(REQUEST_DELAY * 2)

        # Финальное сохранение
        if all_results:
            df = pd.DataFrame(all_results)

            csv_file = self.output_dir / "company_news_links.csv"
            df.to_csv(csv_file, index=False, encoding='utf-8')

            json_file = self.output_dir / "company_news_links.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(all_results, f, ensure_ascii=False, indent=2)

            print(f"\n✅ Сохранено {len(df)} новостей")
            print(f"   CSV: {csv_file}")
            print(f"   JSON: {json_file}")

            # Статистика
            print(f"\n📊 По компаниям:")
            for ticker in self.target_tickers:
                ticker_data = df[df['ticker'] == ticker]
                if len(ticker_data) > 0:
                    pages = ticker_data['page'].unique()
                    print(f"   {ticker}: {len(ticker_data)} новостей, страницы {min(pages)}-{max(pages)}")

            return df
        else:
            print("❌ Не удалось собрать новости")
            return None

if __name__ == "__main__":
    collector = CompanyNewsCollector()
    collector.collect_all()