# src/data_collection/collect_sber_article_texts.py

"""
Сбор полных текстов статей Сбера с защитой от блокировки
"""

import time
import pandas as pd
import sys
import random
from pathlib import Path
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR


class SberArticleTextCollector:
    """
    Сборщик полных текстов статей Сбербанка с защитой от блокировки
    """

    def __init__(self):
        self.input_file = RAW_DATA_DIR / "sber_official_news" / "sber_official_news_with_text.csv"
        self.output_dir = RAW_DATA_DIR / "sber_official_news"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Файл для сохранения прогресса
        self.progress_file = self.output_dir / "sber_texts_progress.json"

        self.driver = None

        self.options = Options()
        self.options.add_argument("--headless")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--window-size=1920,1080")
        self.options.add_argument("--disable-gpu")
        self.options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

    def start_driver(self):
        """Запускает браузер"""
        print("   🚀 Запуск браузера...")
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=self.options
        )
        self.wait = WebDriverWait(self.driver, 15)

    def stop_driver(self):
        """Закрывает браузер"""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def load_progress(self):
        """Загружает прогресс"""
        if self.progress_file.exists():
            import json
            with open(self.progress_file, 'r') as f:
                return json.load(f)
        return {'processed': [], 'last_index': 0}

    def save_progress(self, progress):
        """Сохраняет прогресс"""
        import json
        with open(self.progress_file, 'w') as f:
            json.dump(progress, f)

    def get_article_text(self, url, retries=3):
        """Получает полный текст статьи с повторными попытками"""
        for attempt in range(retries):
            try:
                self.driver.get(url)
                # Случайная задержка 3-5 секунд
                time.sleep(random.uniform(3, 5))

                # Пробуем разные селекторы
                text = None

                # Вариант 1: article-content
                try:
                    content = self.driver.find_element(By.CLASS_NAME, "article-content")
                    text = content.text.strip()
                except:
                    pass

                # Вариант 2: news-detail__content
                if not text:
                    try:
                        content = self.driver.find_element(By.CLASS_NAME, "news-detail__content")
                        text = content.text.strip()
                    except:
                        pass

                # Вариант 3: все параграфы
                if not text:
                    paragraphs = self.driver.find_elements(By.TAG_NAME, "p")
                    texts = [p.text.strip() for p in paragraphs if p.text.strip()]
                    if texts:
                        text = "\n\n".join(texts)

                # Вариант 4: ищем любой div с текстом
                if not text:
                    divs = self.driver.find_elements(By.TAG_NAME, "div")
                    for div in divs:
                        div_text = div.text.strip()
                        if len(div_text) > 200 and "JavaScript" not in div_text:
                            text = div_text
                            break

                return text

            except Exception as e:
                print(f"      ⚠️ Попытка {attempt + 1} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(random.uniform(5, 10))  # Ждём дольше перед повтором
                else:
                    return None
        return None

    def collect_all(self, batch_size=10, pause_between_batches=60):
        """Собирает тексты пакетами с паузами между ними"""

        print("\n" + "=" * 70)
        print("🚀 СБОР ТЕКСТОВ СБЕРБАНКА (с защитой от блокировки)")
        print(f"   Пакет: {batch_size} статей, пауза {pause_between_batches} сек")
        print("=" * 70)

        if not self.input_file.exists():
            print(f"❌ Файл не найден: {self.input_file}")
            return None

        df = pd.read_csv(self.input_file)
        print(f"📚 Загружено {len(df)} записей")

        # Определяем, какие статьи нуждаются в тексте
        if 'text' in df.columns:
            df['has_text'] = df['text'].notna() & (df['text'].str.len() > 100)
            articles_needed = df[~df['has_text']].copy()
            print(f"   Уже есть текст: {df['has_text'].sum()}")
            print(f"   Нужно собрать: {len(articles_needed)}")
        else:
            articles_needed = df.copy()
            print(f"   Нужно собрать текст для всех {len(articles_needed)} статей")

        if len(articles_needed) == 0:
            print("✅ Все статьи уже собраны!")
            return

        # Загружаем прогресс
        progress = self.load_progress()
        processed_urls = set(progress.get('processed', []))

        # Фильтруем уже обработанные
        articles_needed = articles_needed[~articles_needed['url'].isin(processed_urls)]
        print(f"   Осталось собрать: {len(articles_needed)}")

        self.start_driver()

        try:
            all_processed = []
            success_count = 0

            # Разбиваем на пакеты
            total_batches = (len(articles_needed) + batch_size - 1) // batch_size

            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min(start_idx + batch_size, len(articles_needed))
                batch = articles_needed.iloc[start_idx:end_idx]

                print(f"\n📦 ПАКЕТ {batch_num + 1}/{total_batches} ({len(batch)} статей)")

                for idx, row in tqdm(batch.iterrows(), total=len(batch), desc="   Сбор"):
                    url = row['url']
                    title = row.get('title', '')[:50]

                    print(f"\n   📄 {title}...")
                    text = self.get_article_text(url)

                    if text:
                        success_count += 1
                        print(f"      ✅ Текст получен ({len(text)} симв.)")
                    else:
                        print(f"      ❌ Текст не найден")

                    # Сохраняем результат
                    df.loc[idx, 'text'] = text
                    df.loc[idx, 'text_length'] = len(text) if text else 0

                    # Обновляем прогресс
                    processed_urls.add(url)
                    progress['processed'] = list(processed_urls)
                    progress['last_index'] = idx
                    self.save_progress(progress)

                    # Сохраняем промежуточный файл после каждой статьи
                    df.to_csv(self.input_file, index=False, encoding='utf-8')

                # Пауза между пакетами
                if batch_num < total_batches - 1:
                    print(f"\n   ⏸️ Пауза {pause_between_batches} сек перед следующим пакетом...")
                    time.sleep(pause_between_batches)

            print("\n" + "=" * 70)
            print("✅ СБОР ТЕКСТОВ ЗАВЕРШЁН")
            print("=" * 70)
            print(f"\n📁 Файл: {self.input_file}")
            print(f"   Всего статей: {len(df)}")
            print(f"   С текстом: {df['text'].notna().sum()}")
            print(f"   Успешно собрано в этом запуске: {success_count}")

        finally:
            self.stop_driver()
            # Удаляем файл прогресса
            if self.progress_file.exists():
                self.progress_file.unlink()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', type=int, default=10, help='Размер пакета')
    parser.add_argument('--pause', type=int, default=60, help='Пауза между пакетами (сек)')
    parser.add_argument('--test', type=int, help='Тестовый режим (N статей)')

    args = parser.parse_args()

    collector = SberArticleTextCollector()

    if args.test:
        print(f"\n🧪 ТЕСТ: {args.test} статей")
        # Создаём временный файл с тестовыми данными
        df = pd.read_csv(collector.input_file)
        test_df = df.head(args.test)
        test_df.to_csv(collector.input_file, index=False)

    collector.collect_all(batch_size=args.batch, pause_between_batches=args.pause)


if __name__ == "__main__":
    main()