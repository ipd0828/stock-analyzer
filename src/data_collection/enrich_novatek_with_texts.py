# enrich_novatek_with_texts_force.py

"""
Принудительный досбор текстов для новостей Новатэка (перезаписывает существующие)
"""

import time
import pandas as pd
import sys
import re
from pathlib import Path
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


class NovatekTextEnricher:
    def __init__(self):
        self.input_file = RAW_DATA_DIR / "novatek_official_news" / "novatek_official_news_all.csv"
        self.output_dir = RAW_DATA_DIR / "novatek_official_news"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.driver = None

        self.options = Options()
        self.options.add_argument("--headless")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--window-size=1920,1080")
        self.options.add_argument("--disable-gpu")

    def start_driver(self):
        print("   🚀 Запуск браузера...")
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=self.options
        )

    def stop_driver(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def get_article_text(self, url):
        """Получает полный текст статьи"""
        try:
            self.driver.get(url)
            time.sleep(3)

            # Собираем текст
            text_parts = []

            # Ищем заголовок
            try:
                title = self.driver.find_element(By.CSS_SELECTOR, "h1, h2")
                title_text = title.text.strip()
                if title_text:
                    text_parts.append(title_text)
            except:
                pass

            # Ищем все параграфы
            paragraphs = self.driver.find_elements(By.TAG_NAME, "p")
            for p in paragraphs:
                p_text = p.text.strip()
                if p_text and len(p_text) > 20:  # Пропускаем короткие
                    text_parts.append(p_text)

            # Если нет параграфов, ищем div с текстом
            if not text_parts:
                try:
                    content = self.driver.find_element(By.CSS_SELECTOR, ".text, .content, .news-detail")
                    text_parts.append(content.text)
                except:
                    pass

            if text_parts:
                full_text = "\n\n".join(text_parts)
                full_text = re.sub(r'\n\s*\n', '\n\n', full_text)
                return full_text.strip()
            return None

        except Exception as e:
            return None

    def enrich_all(self):
        print("\n" + "=" * 70)
        print("🚀 ПРИНУДИТЕЛЬНЫЙ ДОСБОР ТЕКСТОВ НОВАТЭКА")
        print("=" * 70)

        if not self.input_file.exists():
            print(f"❌ Файл не найден: {self.input_file}")
            return

        df = pd.read_csv(self.input_file)
        print(f"📚 Загружено {len(df)} новостей")

        # Создаём поле text если его нет
        if 'text' not in df.columns:
            df['text'] = None
            df['text_length'] = 0
            print("   Создано поле text")
        else:
            # Проверяем, что в поле text (а не мусор)
            sample = df['text'].iloc[0] if len(df) > 0 else ""
            if sample and "соц. сетях" in str(sample):
                print("   ⚠️ Обнаружен мусор в поле text, будем перезаписывать")

        # Будем обрабатывать все новости
        print(f"   Будет обработано: {len(df)} новостей")

        self.start_driver()

        try:
            texts = []
            success = 0

            for idx, row in tqdm(df.iterrows(), total=len(df), desc="Загрузка"):
                url = row['url']
                text = self.get_article_text(url)

                if text:
                    success += 1
                    texts.append({
                        'index': idx,
                        'text': text,
                        'text_length': len(text)
                    })
                else:
                    texts.append({
                        'index': idx,
                        'text': None,
                        'text_length': 0
                    })

                time.sleep(0.5)

                if (idx + 1) % 50 == 0:
                    print(f"\n   📊 Прогресс: {success}/{idx + 1} успешно")
                    # Сохраняем промежуточный результат
                    temp_df = df.copy()
                    for t in texts:
                        temp_df.loc[t['index'], 'text'] = t['text']
                        temp_df.loc[t['index'], 'text_length'] = t['text_length']
                    temp_file = self.output_dir / f"novatek_progress_{idx + 1}.csv"
                    temp_df.to_csv(temp_file, index=False, encoding='utf-8')

            # Обновляем DataFrame
            for t in texts:
                df.loc[t['index'], 'text'] = t['text']
                df.loc[t['index'], 'text_length'] = t['text_length']

            # Сохраняем
            output_file = self.output_dir / "novatek_official_news_all.csv"
            df.to_csv(output_file, index=False, encoding='utf-8')

            print("\n" + "=" * 70)
            print("✅ ДОСБОР ЗАВЕРШЁН")
            print("=" * 70)
            print(f"   Всего новостей: {len(df)}")
            print(f"   С текстом: {success} ({success / len(df) * 100:.1f}%)")

            if success > 0:
                sample_text = df[df['text'].notna()]['text'].iloc[0]
                print(f"\n📰 Пример текста:")
                print(f"   {sample_text[:300]}...")

        finally:
            self.stop_driver()


if __name__ == "__main__":
    enricher = NovatekTextEnricher()
    enricher.enrich_all()