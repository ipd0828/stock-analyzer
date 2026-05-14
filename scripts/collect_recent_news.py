#!/usr/bin/env python3
# scripts/collect_recent_news.py
"""
Сбор свежих новостей SmartLab за последние N дней.
Только заголовок + текст статьи, без комментариев.
"""

import re
import os
import time
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm

sys.path.append(str(Path(__file__).parent.parent))
from config.paths import RAW_DATA_DIR


def parse_smartlab_date(date_str: str) -> datetime:
    """Парсит даты: "30 апреля 2026, 13:13" или "08/05" (ДД/ММ)"""
    if not date_str or not date_str.strip():
        return None

    date_str = date_str.strip()
    current_year = datetime.now().year

    months = {
        'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
        'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
        'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
    }

    for month_name, month_num in months.items():
        if month_name in date_str.lower():
            match = re.search(r'(\d{1,2})\s*' + month_name + r'\s*(\d{4})', date_str.lower())
            if match:
                return datetime(int(match.group(2)), month_num, int(match.group(1)))

    match = re.match(r'^(\d{1,2})/(\d{1,2})$', date_str)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        year = current_year if month <= datetime.now().month else current_year - 1
        return datetime(year, month, day)

    return None


class SmartLabNewsCollector:
    """Сборщик новостей SmartLab через Selenium"""

    def __init__(self):
        self.options = Options()
        self.options.add_argument("--headless")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--window-size=1920,1080")
        self.options.add_argument("--disable-gpu")
        self.options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
        self.driver = None

    def start_driver(self):
        if not self.driver:
            self.options.binary_location = os.environ.get('CHROMIUM_BIN', '/usr/bin/chromium')
            self.driver = webdriver.Chrome(options=self.options)

    def stop_driver(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def collect_news_list(self, ticker: str, days: int) -> list:
        """Собирает список новостей с главной страницы"""
        url = f"https://smart-lab.ru/forum/news/{ticker}/"
        print(f"📰 Загрузка: {url}")

        all_news = []
        cutoff_date = datetime.now() - timedelta(days=days)
        page = 1

        while True:
            page_url = url if page == 1 else f"{url}page{page}/"
            print(f"   Страница {page}")

            try:
                self.driver.get(page_url)
                time.sleep(2)
            except Exception as e:
                print(f"   ❌ Ошибка: {e}")
                break

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            items = soup.select('ul.temp_headers li')

            if not items:
                break

            found_recent = False

            for item in items:
                full_text = item.get_text(strip=True)
                date_match = re.match(r'(\d{1,2}/\d{1,2})', full_text)
                if not date_match:
                    continue

                news_date = parse_smartlab_date(date_match.group(1))

                if news_date and news_date < cutoff_date:
                    print(f"   ⏹️ {news_date.date()} < {cutoff_date.date()}")
                    return all_news

                link = item.find('a')
                if not link:
                    continue

                href = link.get('href', '')
                title = link.get('title') or link.get_text(strip=True)

                if href and title:
                    full_url = f"https://smart-lab.ru{href}" if href.startswith('/') else href
                    all_news.append({
                        'ticker': ticker,
                        'date': news_date.strftime('%Y-%m-%d'),
                        'date_raw': date_match.group(1),
                        'title': title,
                        'url': full_url,
                        'content': ''
                    })
                    found_recent = True
                    print(f"   ✅ {news_date.strftime('%d/%m')}: {title[:60]}...")

            if not found_recent:
                break

            pagination = soup.find('div', id='pagination')
            if pagination and pagination.find('a', string='→'):
                page += 1
                time.sleep(1)
            else:
                break

        return all_news

    def fetch_article_text(self, url: str) -> str:
        """Загружает текст статьи через мобильную версию"""
        topic_id = None
        match = re.search(r'/(\d+)\.php', url)
        if match:
            topic_id = match.group(1)

        if not topic_id:
            return ''

        mobile_url = f"https://smart-lab.ru/mobile/topic/{topic_id}/"

        try:
            self.driver.get(mobile_url)
            time.sleep(2)
        except:
            return ''

        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        parts = []

        # Заголовок
        title_tag = soup.find('h1')
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            title_text = re.sub(r'^.*?\|\s*', '', title_text)
            parts.append(title_text)

        # Текст статьи
        content_div = soup.find('div', class_='content')
        if content_div:
            for unwanted in content_div.find_all(['script', 'style', 'ins', 'iframe', 'div.block-dosmotra']):
                unwanted.decompose()

            paragraphs = content_div.find_all('p')
            if paragraphs:
                for p in paragraphs:
                    p_text = p.get_text(strip=True)
                    if p_text and len(p_text) > 30 and 'Данная публикация является личным мнением' not in p_text:
                        parts.append(p_text)
            else:
                text = content_div.get_text('\n', strip=True)
                text = re.sub(r'Данная публикация.*$', '', text, flags=re.DOTALL)
                if len(text) > 100:
                    parts.append(text)

        # Если пусто — ищем любой текстовый блок
        if len(parts) <= 1:
            best_text = ''
            for div in soup.find_all('div'):
                text = div.get_text('\n', strip=True)
                if (len(text) > 200 and
                        'Авторизация' not in text and
                        'PREMIUM' not in text[:50] and
                        'Ленты' not in text[:50]):
                    text = re.sub(r'Данная публикация.*$', '', text, flags=re.DOTALL)
                    text = re.sub(r'Читайте на SMART-LAB:.*', '', text, flags=re.DOTALL)
                    text = re.sub(r'\n{3,}', '\n\n', text)
                    if len(text) > len(best_text):
                        best_text = text
            if best_text:
                parts.append(best_text)

        text = '\n\n'.join(parts)

        # Финальная очистка
        text = re.sub(r'^Новости рынков\s*', '', text)
        text = re.sub(r'^\d{1,2}\s+\w+\s+\d{4},\s+\d{1,2}:\d{2}\s*', '', text)
        text = re.sub(r'^\+\s*Подписаться\s*', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()

        return text[:5000]


def collect_recent_news(ticker: str, days: int = 3) -> list:
    """Основная функция: сбор новостей с текстами"""
    collector = SmartLabNewsCollector()

    print(f"\n{'=' * 60}")
    print(f"📰 СБОР НОВОСТЕЙ {ticker} ЗА {days} ДНЕЙ")
    print(f"{'=' * 60}")

    try:
        collector.start_driver()

        # 1. Список новостей
        news_list = collector.collect_news_list(ticker, days)
        print(f"\n📊 Найдено: {len(news_list)} новостей")

        if not news_list:
            return []

        # 2. Загрузка текстов
        for news in tqdm(news_list, desc="Загрузка текстов"):
            news['content'] = collector.fetch_article_text(news['url'])
            time.sleep(1)

        # 3. Сохраняем
        output_dir = RAW_DATA_DIR / "recent_news"
        output_dir.mkdir(parents=True, exist_ok=True)
        json_file = output_dir / f"{ticker}_recent_{datetime.now().strftime('%Y%m%d_%H%M')}.json"

        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(news_list, f, ensure_ascii=False, indent=2)

        print(f"\n✅ Сохранено: {json_file}")

        with_text = sum(1 for n in news_list if len(n.get('content', '')) > 100)
        print(f"   С текстом: {with_text}/{len(news_list)}")

        return news_list

    finally:
        collector.stop_driver()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--ticker', default='SBER', choices=['GAZP', 'SBER', 'LKOH', 'NVTK', 'VTBR'])
    parser.add_argument('--days', type=int, default=3)
    args = parser.parse_args()

    news = collect_recent_news(args.ticker, args.days)

    if news and news[0].get('content'):
        print(f"\n{'=' * 60}")
        print("ПРИМЕР:")
        print(f"Заголовок: {news[0]['title']}")
        print(f"Текст ({len(news[0]['content'])} симв.):")
        print(news[0]['content'][:400])