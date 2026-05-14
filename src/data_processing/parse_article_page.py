# src/data_processing/parse_article_page.py (исправленная версия)

import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import json


def parse_article_page(url: str):
    """
    Парсит страницу со статьёй — исправленная версия
    """

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'

        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, 'html.parser')

        result = {
            'url': url,
            'title': None,
            'date_published': None,
            'author': None,
            'text': None,
            'views': None,
            'rating': None,
            'tags': [],
            'comments': []
        }

        # Заголовок
        title_elem = soup.find('h1', class_='title')
        if title_elem:
            title_span = title_elem.find('span')
            if title_span:
                result['title'] = title_span.get_text(strip=True)

        # Дата и автор
        action_list = soup.find('ul', class_='action')
        if action_list:
            date_li = action_list.find('li', class_='date')
            if date_li:
                result['date_published'] = date_li.get_text(strip=True)

            author_li = action_list.find('li', class_='author')
            if author_li:
                author_link = author_li.find('a')
                if author_link:
                    result['author'] = author_link.get_text(strip=True)

        # Текст статьи — ИЩЕМ ВСЕ div.content и берём тот, где есть реальный текст
        content_divs = soup.find_all('div', class_='content')
        for div in content_divs:
            text = div.get_text(strip=True)
            # Если в тексте больше 100 символов и нет слова "Авторизация", это наш текст
            if len(text) > 100 and 'Авторизация' not in text:
                # Убираем лишние элементы
                for unwanted in div.find_all(['script', 'style', 'ins']):
                    unwanted.decompose()
                result['text'] = div.get_text('\n', strip=True)
                break

        # Просмотры
        views_elem = soup.find('span', class_='views-span') or soup.find('span', class_='watchlater-views-indicator')
        if views_elem:
            views_text = views_elem.get_text(strip=True)
            if views_text.isdigit():
                result['views'] = int(views_text)

        # Рейтинг
        rating_elem = soup.find('li', class_='total')
        if rating_elem:
            rating_link = rating_elem.find('a')
            if rating_link:
                rating_text = rating_link.get_text(strip=True)
                if rating_text.isdigit():
                    result['rating'] = int(rating_text)

        # Теги
        tags_ul = soup.find('ul', class_='tags')
        if tags_ul:
            for tag_li in tags_ul.find_all('li'):
                tag_link = tag_li.find('a')
                if tag_link:
                    tag = tag_link.get_text(strip=True)
                    if tag and tag != 'Ключевые слова:':
                        result['tags'].append(tag)

        # Комментарии
        comments_div = soup.find('div', class_='comments')
        if comments_div:
            comments = comments_div.find_all('div', class_='comment')
            for comment in comments:
                try:
                    text_div = comment.find('div', class_='text')
                    if not text_div:
                        continue

                    author_elem = comment.find('div', class_='author')
                    author = author_elem.get_text(strip=True) if author_elem else None

                    date_elem = comment.find('li', class_='date')
                    comment_date = date_elem.get_text(strip=True) if date_elem else None

                    result['comments'].append({
                        'author': author,
                        'date': comment_date,
                        'text': text_div.get_text(strip=True)[:500],
                    })
                except:
                    continue

        return result

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None


# Функция для нормализации даты
def normalize_date(date_str: str) -> str:
    """Преобразует дату из формата 'ДД месяц ГГГГ, ЧЧ:ММ' в 'YYYY-MM-DD'"""
    if not date_str:
        return None

    # Пример: "03 марта 2026, 15:05"
    months = {
        'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04',
        'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08',
        'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12'
    }

    try:
        # Разбиваем строку
        parts = date_str.split(',')[0].strip().split()
        if len(parts) == 3:
            day, month_str, year = parts
            month = months.get(month_str.lower())
            if month:
                return f"{year}-{month}-{day.zfill(2)}"
    except:
        pass

    return date_str


# Тест
if __name__ == "__main__":
    url = "https://smart-lab.ru/blog/1272332.php"
    article = parse_article_page(url)

    if article:
        print(f"Заголовок: {article['title']}")
        print(f"Дата: {article['date_published']}")
        print(f"Нормализованная дата: {normalize_date(article['date_published'])}")
        print(f"Автор: {article['author']}")
        print(f"Просмотры: {article['views']}")
        print(f"Рейтинг: {article['rating']}")
        print(f"Теги: {', '.join(article['tags'])}")
        print(f"\nТекст (первые 500 символов):\n{article['text'][:500]}...")
        print(f"\nКомментариев: {len(article['comments'])}")
        if article['comments']:
            print(f"Первый комментарий: {article['comments'][0]['text'][:100]}...")