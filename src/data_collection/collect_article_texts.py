# src/data_collection/collect_article_texts.py

"""
Универсальный сборщик полных текстов статей для любой компании
"""

import time
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR

# Маппинг тикеров на имена папок и файлов
COMPANY_CONFIG = {
    'GAZP': {
        'folder': 'gazprom_official_news',
        'file_prefix': 'gazprom_official_news'
    },
    'SBER': {
        'folder': 'sber_official_news',
        'file_prefix': 'sber_official_news'
    },
    'LKOH': {
        'folder': 'lukoil_official_news',
        'file_prefix': 'lukoil_official_news'
    },
    'NVTK': {
        'folder': 'novatek_official_news',
        'file_prefix': 'novatek_official_news'
    },
    'VTBR': {
        'folder': 'vtb_official_news',
        'file_prefix': 'vtb_official_news'
    }
}


class ArticleTextCollector:
    """
    Универсальный сборщик текстов статей
    """

    def __init__(self, company):
        self.company = company.upper()
        self.config = COMPANY_CONFIG.get(self.company)

        if not self.config:
            raise ValueError(f"Неизвестная компания: {company}")

        self.folder_name = self.config['folder']
        self.file_prefix = self.config['file_prefix']

        self.input_file = RAW_DATA_DIR / self.folder_name / f"{self.file_prefix}_all.csv"
        self.output_dir = RAW_DATA_DIR / self.folder_name
        self.output_dir.mkdir(parents=True, exist_ok=True)

        print(f"📁 Папка: {self.folder_name}")
        print(f"📁 Входной файл: {self.input_file}")

        self.driver = None

        # Настройки Chrome
        self.options = Options()
        self.options.add_argument("--headless")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--window-size=1920,1080")
        self.options.add_argument("--disable-gpu")
        self.options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    def start_driver(self):
        """Запускает браузер"""
        print("🚀 Запуск браузера...")
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=self.options
        )
        self.wait = WebDriverWait(self.driver, 10)

    def stop_driver(self):
        """Закрывает браузер"""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def get_article_text(self, url):
        """Получает полный текст статьи"""
        try:
            self.driver.get(url)
            time.sleep(2)

            # Пробуем разные селекторы
            selectors = [
                ".content_wrapper",
                ".article-content",
                ".news-detail__content",
                ".text-block",
                "article",
                ".press-release__text",
                ".news-item__text"
            ]

            for selector in selectors:
                try:
                    content = self.driver.find_element(By.CSS_SELECTOR, selector)
                    text = content.text.strip()
                    if text and len(text) > 100:
                        return text
                except:
                    continue

            return None

        except Exception as e:
            return None

    def collect_all(self, max_articles=None, resume=True):
        """Собирает тексты всех статей"""

        print("\n" + "=" * 70)
        print(f"🚀 СБОР ТЕКСТОВ СТАТЕЙ {self.company}")
        print("=" * 70)

        if not self.input_file.exists():
            print(f"❌ Файл не найден: {self.input_file}")
            print(f"   Сначала соберите ссылки для {self.company}")
            return None

        df = pd.read_csv(self.input_file)
        print(f"📚 Загружено {len(df)} ссылок")

        # Проверяем, сколько уже собрано
        output_file = self.output_dir / f"{self.file_prefix}_with_text.csv"
        processed_urls = set()
        if resume and output_file.exists():
            existing = pd.read_csv(output_file)
            processed_urls = set(existing['url'].tolist())
            print(f"   Уже собрано: {len(processed_urls)} статей")
            df = df[~df['url'].isin(processed_urls)]

        if max_articles:
            df = df.head(max_articles)

        print(f"   Осталось собрать: {len(df)} статей")

        if len(df) == 0:
            print("✅ Все статьи уже собраны!")
            return

        self.start_driver()

        try:
            results = []

            for idx, row in tqdm(df.iterrows(), total=len(df), desc="Сбор текстов"):
                url = row['url']
                title = row.get('title', '')

                text = self.get_article_text(url)

                result = {
                    'url': url,
                    'title': title,
                    'date_raw': row.get('date_raw'),
                    'date_normalized': row.get('date_normalized'),
                    'text': text,
                    'text_length': len(text) if text else 0,
                    'collected_at': datetime.now().isoformat()
                }

                # Добавляем остальные поля
                for col in ['ticker', 'company', 'tags', 'source']:
                    if col in row:
                        result[col] = row[col]

                results.append(result)
                time.sleep(0.5)

            # Сохраняем результаты
            self._save_results(results, processed_urls)

        finally:
            self.stop_driver()

        return results

    def _save_results(self, new_results, processed_urls):
        """Сохраняет результаты, объединяя с уже собранными"""

        output_file = self.output_dir / f"{self.file_prefix}_with_text.csv"

        if output_file.exists():
            existing = pd.read_csv(output_file)
            final_df = pd.concat([existing, pd.DataFrame(new_results)], ignore_index=True)
        else:
            final_df = pd.DataFrame(new_results)

        final_df.to_csv(output_file, index=False, encoding='utf-8')

        json_file = self.output_dir / f"{self.file_prefix}_with_text.json"
        final_df.to_json(json_file, orient='records', force_ascii=False, indent=2)

        print("\n" + "=" * 70)
        print(f"✅ СБОР ТЕКСТОВ {self.company} ЗАВЕРШЁН")
        print("=" * 70)
        print(f"\n📁 Файлы сохранены:")
        print(f"   CSV: {output_file}")
        print(f"   JSON: {json_file}")
        print(f"   Всего статей: {len(final_df)}")

        with_text = final_df[final_df['text'].notna()]
        print(f"\n📊 СТАТИСТИКА:")
        print(f"   Статей с текстом: {len(with_text)} ({len(with_text) / len(final_df) * 100:.1f}%)")

        if len(with_text) > 0:
            avg_len = with_text['text_length'].mean()
            print(f"   Средняя длина текста: {avg_len:.0f} символов")

        return final_df

    def clean_text(self, text):
        """Очищает текст от служебной информации"""
        if not text:
            return None

        # Удаляем контактные данные
        import re
        patterns = [
            r'Контактная информация.*',
            r'\+7 \d{3} \d{3}-\d{2}-\d{2}',
            r'pr@gazprom\.ru',
            r'ir@gazprom\.ru',
            r'«Газпром» в социальных сетях.*',
            r'Управление информации.*',
            r'Пресс-центр.*',
            r'События.*',
            r'ОФИЦИАЛЬНОЕ СООБЩЕНИЕ.*',
            r'\n\s*\n'
        ]

        for pattern in patterns:
            text = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE)

        # Убираем множественные переносы строк
        text = re.sub(r'\n\s*\n', '\n\n', text)

        return text.strip()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--company', required=True, choices=['GAZP', 'SBER', 'LKOH', 'NVTK', 'VTBR'],
                        help='Компания')
    parser.add_argument('--max', type=int, help='Максимум статей для теста')
    parser.add_argument('--no-resume', action='store_true', help='Не продолжать, начать заново')

    args = parser.parse_args()

    collector = ArticleTextCollector(args.company)

    if args.max:
        print(f"\n🧪 ТЕСТ: {args.max} статей")
        collector.collect_all(max_articles=args.max, resume=not args.no_resume)
    else:
        print("\n🚀 ПОЛНЫЙ СБОР")
        collector.collect_all(resume=not args.no_resume)


if __name__ == "__main__":
    main()