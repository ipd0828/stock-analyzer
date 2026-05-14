# src/data_collection/collect_forum_comments.py

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


class ForumCommentsCollector:
    """
    Сборщик комментариев с форумов компаний на Smart-Lab.
    Собирает: ник, текст комментария, дату, рейтинг, страницу.
    Идёт от последней страницы к первой.
    """

    def __init__(self):
        self.base_url = "https://smart-lab.ru/forum"
        self.output_dir = RAW_DATA_DIR / "forum_comments"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        # Компании для сбора
        self.target_tickers = TICKERS

        print(f"📁 Комментарии будут сохранены в: {self.output_dir}")

    def get_total_pages(self, ticker: str) -> int:
        """
        Определяет общее количество страниц форума по ссылке '→'.
        Заходит на первую страницу и смотрит последнюю ссылку.
        """
        url = f"{self.base_url}/{ticker}/"
        print(f"\n🔍 Определение числа страниц для {ticker}...")

        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.encoding = 'utf-8'

            if response.status_code != 200:
                print(f"   ❌ Не удалось загрузить первую страницу")
                return 0

            soup = BeautifulSoup(response.text, 'html.parser')
            pagination = soup.find('div', id='pagination') or soup.find('div', class_='pagination1')

            if not pagination:
                print(f"   ℹ️ Пагинация не найдена, вероятно только 1 страница")
                return 1

            # Ищем ссылку "→" (последняя страница)
            next_link = pagination.find('a', string='→')
            if next_link:
                href = next_link.get('href', '')
                # Извлекаем номер страницы из /forum/SBER/page14502/
                match = re.search(r'/page(\d+)/', href)
                if match:
                    total_pages = int(match.group(1))
                    print(f"   ✅ Всего страниц: {total_pages}")
                    return total_pages

            # Если не нашли, считаем видимые страницы
            page_links = pagination.find_all('a')
            pages = []
            for link in page_links:
                text = link.get_text(strip=True)
                if text.isdigit():
                    pages.append(int(text))

            if pages:
                total = max(pages)
                print(f"   ✅ Всего страниц (по видимым): {total}")
                return total

            return 1

        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            return 0

    def parse_page(self, html: str, ticker: str, page_num: int):
        """
        Парсит одну страницу форума, извлекая все комментарии.
        """
        soup = BeautifulSoup(html, 'html.parser')
        comments = []

        # Все комментарии на странице в ol с классом 'forum_cmts'
        comments_list = soup.find('ol', class_='forum_cmts')
        if not comments_list:
            return comments

        # Каждый комментарий в li с классом 'cm_wrap'
        items = comments_list.find_all('li', class_='cm_wrap')

        for item in items:
            try:
                # --- Автор ---
                author_link = item.find('a', class_='a_name') or item.find('a', href=re.compile(r'/profile/'))
                author = author_link.get_text(strip=True) if author_link else None

                # --- Дата и время ---
                time_tag = item.find('time')
                comment_time = time_tag.get('datetime') if time_tag else None
                comment_date = time_tag.get_text(strip=True) if time_tag else None

                # Если нет datetime, берём текст
                if not comment_time and comment_date:
                    comment_time = comment_date

                # --- Текст комментария ---
                text_div = item.find('div', class_='text')
                comment_text = text_div.get_text(strip=True) if text_div else None

                # --- Рейтинг комментария ---
                rating = 0
                rating_span = item.find('span', class_='cm_mrk')
                if rating_span:
                    rating_text = rating_span.get_text(strip=True).replace('+', '').strip()
                    if rating_text and rating_text != '0':
                        try:
                            rating = int(rating_text)
                        except:
                            pass

                # Альтернативный поиск рейтинга
                if rating == 0:
                    rating_link = item.find('a', class_='cm_mrk')
                    if rating_link:
                        rating_text = rating_link.get_text(strip=True).replace('+', '').strip()
                        if rating_text and rating_text != '0':
                            try:
                                rating = int(rating_text)
                            except:
                                pass

                # --- Уникальный ID комментария ---
                comment_id = None
                comment_link = item.find('a', href=re.compile(r'#comment'))
                if comment_link:
                    href = comment_link.get('href', '')
                    match = re.search(r'#comment(\d+)', href)
                    if match:
                        comment_id = match.group(1)

                # Если есть данные, добавляем
                if author or comment_text:
                    comments.append({
                        'ticker': ticker,
                        'company': TICKER_TO_COMPANY.get(ticker, ''),
                        'page': page_num,
                        'comment_id': comment_id,
                        'author': author,
                        'date_raw': comment_date,
                        'datetime': comment_time,
                        'text': comment_text[:1000] if comment_text else None,  # ограничиваем длину
                        'rating': rating,
                        'collected_at': datetime.now().isoformat()
                    })

            except Exception as e:
                print(f"      ⚠️ Ошибка парсинга комментария: {e}")
                continue

        return comments

    def get_page_html(self, ticker: str, page: int):
        """Загружает HTML страницы форума."""
        url = f"{self.base_url}/{ticker}/" if page == 1 else f"{self.base_url}/{ticker}/page{page}/"

        print(f"      Загрузка стр. {page}...", end='', flush=True)
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.encoding = 'utf-8'
            if response.status_code == 200:
                print(f" ✅ {len(response.text)} bytes")
                return response.text
            elif response.status_code == 404:
                print(f" ❌ 404")
                return None
            else:
                print(f" ❌ HTTP {response.status_code}")
                return None
        except Exception as e:
            print(f" ❌ Ошибка: {e}")
            return None

    def collect_ticker_comments(self, ticker: str):
        """
        Собирает все комментарии для одного тикера от последней страницы к первой.
        """
        print(f"\n📊 Сбор комментариев для {ticker} ({TICKER_TO_COMPANY.get(ticker, '')})")

        total_pages = self.get_total_pages(ticker)
        if total_pages == 0:
            print(f"   ❌ Не удалось определить число страниц")
            return []

        print(f"   📄 Всего страниц: {total_pages}")

        all_comments = []
        empty_pages = 0
        max_empty_pages = 3

        # Идём от последней страницы к первой
        for page in range(total_pages, 0, -1):
            html = self.get_page_html(ticker, page)

            if not html:
                empty_pages += 1
                print(f"      ⚠️ Страница {page} не загружена (пустых подряд: {empty_pages})")
                if empty_pages >= max_empty_pages:
                    print(f"      🛑 {max_empty_pages} ошибок подряд, останавливаемся")
                    break
                continue

            comments = self.parse_page(html, ticker, page)

            if comments:
                empty_pages = 0
                print(f"      ✅ Страница {page}: {len(comments)} комментариев")
                all_comments.extend(comments)
            else:
                empty_pages += 1
                print(f"      ⚠️ Страница {page}: комментариев нет (пустых подряд: {empty_pages})")
                if empty_pages >= max_empty_pages:
                    print(f"      🛑 {max_empty_pages} пустых страниц подряд, останавливаемся")
                    break

            time.sleep(REQUEST_DELAY)

        print(f"   📦 ИТОГО для {ticker}: {len(all_comments)} комментариев")
        return all_comments

    def collect_all_tickers(self, test_mode=False):
        """
        Собирает комментарии для всех тикеров.
        test_mode: если True, собирает только первую страницу для теста.
        """
        print("\n" + "=" * 70)
        print("🚀 СБОР КОММЕНТАРИЕВ С ФОРУМОВ КОМПАНИЙ")
        print("=" * 70)

        all_results = []

        for ticker in self.target_tickers:
            if test_mode:
                # Тестовый режим: только одна страница
                print(f"\n🧪 ТЕСТ: {ticker}")
                html = self.get_page_html(ticker, 1)
                if html:
                    comments = self.parse_page(html, ticker, 1)
                    if comments:
                        all_results.extend(comments)
                        print(f"   ✅ Найдено {len(comments)} комментариев")
            else:
                # Полный сбор
                comments = self.collect_ticker_comments(ticker)
                if comments:
                    all_results.extend(comments)

                    # Промежуточное сохранение после каждой компании
                    self._save_progress(all_results, ticker)

            time.sleep(REQUEST_DELAY * 2)

        # Финальное сохранение
        self._save_final(all_results, test_mode)

        return all_results

    def _save_progress(self, results, ticker):
        """Промежуточное сохранение после компании."""
        if not results:
            return

        df = pd.DataFrame(results)
        temp_file = self.output_dir / f"forum_comments_temp_{ticker}.csv"
        df.to_csv(temp_file, index=False, encoding='utf-8')
        print(f"   💾 Промежуточно сохранено {len(results)} комм. в {temp_file.name}")

    def _save_final(self, results, test_mode=False):
        """Финальное сохранение всех результатов."""
        if not results:
            print("❌ Нет данных для сохранения")
            return

        df = pd.DataFrame(results)

        suffix = "_test" if test_mode else "_all"
        csv_file = self.output_dir / f"forum_comments{suffix}.csv"
        json_file = self.output_dir / f"forum_comments{suffix}.json"

        df.to_csv(csv_file, index=False, encoding='utf-8')
        df.to_json(json_file, orient='records', force_ascii=False, indent=2)

        print("\n" + "=" * 70)
        print("✅ СБОР ЗАВЕРШЁН")
        print("=" * 70)
        print(f"\n📁 Файлы сохранены:")
        print(f"   CSV: {csv_file}")
        print(f"   JSON: {json_file}")
        print(f"   Всего комментариев: {len(df)}")

        # Статистика
        print(f"\n📊 СТАТИСТИКА:")
        print(f"   По компаниям:")
        for ticker in self.target_tickers:
            ticker_data = df[df['ticker'] == ticker]
            if len(ticker_data) > 0:
                pages = ticker_data['page'].unique()
                print(f"   {ticker}: {len(ticker_data)} комм., страницы {min(pages)}-{max(pages)}")

        print(f"\n   Уникальных авторов: {df['author'].nunique()}")
        print(f"   Комментариев с рейтингом >0: {len(df[df['rating'] > 0])}")

        # Диапазон дат
        valid_dates = df[df['datetime'].notna()]
        if len(valid_dates) > 0:
            print(f"   Период: {valid_dates['datetime'].min()} - {valid_dates['datetime'].max()}")


def main():
    print("\n" + "=" * 70)
    print("🎯 ЗАПУСК СБОРА КОММЕНТАРИЕВ С ФОРУМОВ")
    print("=" * 70)

    collector = ForumCommentsCollector()

    # Для теста (уже сделали)
    # collector.collect_all_tickers(test_mode=True)

    # ПОЛНЫЙ СБОР
    collector.collect_all_tickers(test_mode=False)


if __name__ == "__main__":
    main()