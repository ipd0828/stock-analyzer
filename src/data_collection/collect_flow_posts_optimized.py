# src/data_collection/collect_flow_posts_optimized.py

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import sys
import gc
from pathlib import Path
from datetime import datetime, timedelta
import json
import re

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR
from config.settings import REQUEST_DELAY


class FlowPostsCollectorOptimized:
    """
    Оптимизированный сборщик постов из потока (flow) на Smart-Lab.
    Сохраняет ТУ ЖЕ СТРУКТУРУ, что и оригинальный скрипт.
    """

    def __init__(self):
        self.base_url = "https://smart-lab.ru/flow/date"
        self.output_dir = RAW_DATA_DIR / "flow_posts"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        self.delay = REQUEST_DELAY * 2

        # Продолжаем с 1 февраля 2024
        self.start_date = datetime(2024, 3, 1)
        self.end_date = datetime.now()

        print(f"📅 Продолжаем сбор: {self.start_date.strftime('%Y-%m-%d')} - {self.end_date.strftime('%Y-%m-%d')}")
        print(f"⏱️ Задержка: {self.delay} сек")

    def get_page_html(self, date: str, page: int = 1):
        """Загружает страницу"""
        if page == 1:
            url = f"{self.base_url}/{date}/"
        else:
            url = f"{self.base_url}/{date}/page{page}/"

        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.encoding = 'utf-8'
            if response.status_code == 200:
                return response.text
            return None
        except:
            return None

    def get_total_pages(self, html: str) -> int:
        """Определяет количество страниц"""
        soup = BeautifulSoup(html, 'html.parser')
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

    def parse_page(self, html: str, date: str, page_num: int):
        """
        Парсит страницу - ТА ЖЕ СТРУКТУРА, ЧТО В ОРИГИНАЛЕ
        """
        soup = BeautifulSoup(html, 'html.parser')
        posts = []

        for topic in soup.find_all('div', class_='topic'):
            try:
                title_tag = topic.find('h2', class_='title')
                if not title_tag:
                    continue
                title_link = title_tag.find('a')
                if not title_link:
                    continue

                post_url = title_link.get('href')
                post_title = title_link.get_text(strip=True)

                # Автор и время
                author_name = None
                post_time = None
                action_list = topic.find('ul', class_='action')
                if action_list:
                    author_li = action_list.find('li', class_='author')
                    if author_li:
                        author_link = author_li.find('a')
                        if author_link:
                            author_name = author_link.get_text(strip=True)
                    date_li = action_list.find('li', class_='date')
                    if date_li:
                        post_time = date_li.get_text(strip=True)

                # Текст (превью)
                content_div = topic.find('div', class_='content')
                post_text_preview = None
                if content_div:
                    # Удаляем "Читать дальше" и картинки
                    for cut_link in content_div.find_all('a', href=True):
                        if cut_link.get_text(strip=True) == 'Читать дальше':
                            cut_link.decompose()
                    for img_link in content_div.find_all('a', class_='imgpreview'):
                        img_link.decompose()
                    post_text_preview = content_div.get_text(' ', strip=True)[:500]

                # Рейтинг
                rating = 0
                rating_ul = topic.find('ul', class_='voting')
                if rating_ul:
                    total_li = rating_ul.find('li', class_='total')
                    if total_li:
                        rating_link = total_li.find('a')
                        if rating_link:
                            rating_text = rating_link.get_text(strip=True)
                            if rating_text.isdigit():
                                rating = int(rating_text)

                # Просмотры и избранное
                views = 0
                favourites = 0
                comments_ul = topic.find('ul', class_='comments')
                if comments_ul:
                    views_li = comments_ul.find('li', class_='views-total')
                    if views_li:
                        views_span = views_li.find('span', class_='views-span')
                        if views_span:
                            views_text = views_span.get_text(strip=True).replace('К', '').replace('k', '')
                            try:
                                if 'K' in views_span.get_text(strip=True) or 'k' in views_span.get_text(strip=True):
                                    views = int(float(views_text) * 1000)
                                else:
                                    views = int(views_text) if views_text.isdigit() else 0
                            except:
                                views = 0

                        fav_span = views_li.find('span', class_='favourited_menu')
                        if fav_span:
                            fav_text = fav_span.get_text(strip=True).replace('★', '').strip()
                            if fav_text.isdigit():
                                favourites = int(fav_text)

                # Количество комментариев
                comments_count = 0
                if comments_ul:
                    comments_li = comments_ul.find('li', class_='comments-total')
                    if comments_li:
                        count_span = comments_li.find('span', class_='red')
                        if count_span:
                            count_text = count_span.get_text(strip=True)
                            if count_text.isdigit():
                                comments_count = int(count_text)

                # Категория
                category = None
                ext_tags_ul = topic.find('ul', class_='ext_tags')
                if ext_tags_ul:
                    first_li = ext_tags_ul.find('li')
                    if first_li and first_li.find('a'):
                        category = first_li.find('a').get_text(strip=True)

                # Упомянутые тикеры
                mentioned_tickers = []
                forum_tags_ul = topic.find('ul', class_='forum_tags')
                if forum_tags_ul:
                    for tag_li in forum_tags_ul.find_all('li'):
                        tag_link = tag_li.find('a')
                        if tag_link:
                            tag_text = tag_link.get_text(strip=True)
                            if tag_text and tag_text not in ['обсудить на форуме:', 'Акции']:
                                mentioned_tickers.append(tag_text)

                # СОХРАНЯЕМ ТУ ЖЕ СТРУКТУРУ
                posts.append({
                    'date': date,
                    'page': page_num,
                    'url': post_url,
                    'title': post_title[:500] if post_title else None,
                    'author': author_name,
                    'time': post_time,
                    'text_preview': post_text_preview[:500] if post_text_preview else None,
                    'rating': rating,
                    'views': views,
                    'favourites': favourites,
                    'comments_count': comments_count,
                    'category': category,
                    'mentioned_tickers': '|'.join(mentioned_tickers) if mentioned_tickers else None,
                    'collected_at': datetime.now().isoformat()
                })

            except Exception as e:
                continue

        return posts

    def collect_day(self, date: datetime):
        """Собирает посты за один день"""
        date_str = date.strftime("%Y-%m-%d")
        print(f"\n📅 {date_str}")

        first_page = self.get_page_html(date_str, 1)
        if not first_page:
            return []

        soup = BeautifulSoup(first_page, 'html.parser')
        if not soup.find('div', class_='topic'):
            return []

        total_pages = self.get_total_pages(first_page)
        all_posts = []

        for page in range(1, total_pages + 1):
            if page == 1:
                html = first_page
            else:
                html = self.get_page_html(date_str, page)
                if not html:
                    continue

            posts = self.parse_page(html, date_str, page)
            all_posts.extend(posts)

            # Пауза между страницами
            time.sleep(self.delay / 2)

            # Освобождаем память
            del posts
            if page > 1:
                del html
            gc.collect()

        return all_posts

    def collect_all(self):
        """Собирает все посты с паузами"""
        print("\n" + "=" * 70)
        print("🚀 ПРОДОЛЖЕНИЕ СБОРА ПОТОКА (ОПТИМИЗИРОВАННО)")
        print("=" * 70)

        current_date = self.start_date
        all_results = []
        batch_size = 7
        day_count = 0

        while current_date <= self.end_date:
            day_posts = self.collect_day(current_date)

            if day_posts:
                all_results.extend(day_posts)
                print(f"   ✅ +{len(day_posts)} постов (всего в батче: {len(all_results)})")

            day_count += 1

            # Сохраняем раз в неделю
            if day_count >= batch_size and all_results:
                self._save_batch(all_results, current_date)
                all_results = []
                day_count = 0
                gc.collect()

            current_date += timedelta(days=1)
            time.sleep(self.delay)

        # Сохраняем остатки
        if all_results:
            self._save_final(all_results)

        print("\n✅ Сбор завершён!")

    def _save_batch(self, results, date):
        """Сохраняет батч результатов"""
        if not results:
            return

        df = pd.DataFrame(results)
        filename = self.output_dir / f"flow_posts_batch_{date.strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False, encoding='utf-8')
        print(f"\n💾 Сохранён батч: {filename} ({len(results)} постов)")

    def _save_final(self, results):
        """Финальное сохранение"""
        if not results:
            return

        df = pd.DataFrame(results)
        csv_file = self.output_dir / "flow_posts_2024_part2.csv"
        df.to_csv(csv_file, index=False, encoding='utf-8')
        print(f"\n✅ Финальное сохранение: {csv_file} ({len(results)} постов)")


def main():
    collector = FlowPostsCollectorOptimized()
    collector.collect_all()


if __name__ == "__main__":
    main()