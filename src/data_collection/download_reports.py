# src/data_collection/download_reports.py
"""
Модуль для скачивания финансовых отчётов с защитой от блокировки
"""

import requests
import pandas as pd
import time
import sys
import random
import re
import json
from pathlib import Path
import zipfile
import io
from fake_useragent import UserAgent
from datetime import datetime

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR
from config.settings import REQUEST_DELAY


class ReportDownloader:
    """Скачивает финансовые отчёты с обходом защиты"""

    def __init__(self):
        self.links_file = RAW_DATA_DIR / "report_links" / "all_report_links.csv"
        self.output_dir = RAW_DATA_DIR / "reports_pdf"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Файлы для отслеживания состояния
        self.progress_file = self.output_dir / "download_progress.json"
        self.dead_links_file = self.output_dir / "dead_links.json"
        self.successful_links_file = self.output_dir / "successful_links.json"

        self.stats = {
            'total': 0,
            'downloaded': 0,
            'failed': 0,
            'skipped': 0,
            'dead_links': 0  # <-- ЕСТЬ В __init__
        }

        # Списки для отслеживания
        self.dead_links = []
        self.successful_links = []

        # Сессия с правильными заголовками
        self.session = requests.Session()
        self.ua = UserAgent()

        # Загружаем прогресс если есть
        self.load_progress()

    def get_headers(self):
        """Генерирует случайные заголовки для каждого запроса"""
        return {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'Referer': 'https://smart-lab.ru/',
            'Origin': 'https://smart-lab.ru',
        }

    def load_progress(self):
        """Загружает прогресс скачивания с проверкой ключей"""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r') as f:
                    loaded_stats = json.load(f)

                # Обновляем только существующие ключи, добавляя новые
                for key in self.stats:
                    if key in loaded_stats:
                        self.stats[key] = loaded_stats[key]

                print(f"📊 Загружен прогресс: скачано {self.stats['downloaded']} файлов")
            except Exception as e:
                print(f"⚠️ Ошибка загрузки прогресса: {e}")

        # Загружаем списки мёртвых ссылок
        if self.dead_links_file.exists():
            try:
                with open(self.dead_links_file, 'r') as f:
                    self.dead_links = json.load(f)
                print(f"   Мёртвых ссылок в истории: {len(self.dead_links)}")
            except:
                self.dead_links = []

        # Загружаем списки успешных
        if self.successful_links_file.exists():
            try:
                with open(self.successful_links_file, 'r') as f:
                    self.successful_links = json.load(f)
            except:
                self.successful_links = []

    def save_progress(self):
        """Сохраняет прогресс скачивания"""
        try:
            with open(self.progress_file, 'w') as f:
                json.dump(self.stats, f, indent=2)

            with open(self.dead_links_file, 'w') as f:
                json.dump(self.dead_links, f, indent=2, ensure_ascii=False)

            with open(self.successful_links_file, 'w') as f:
                json.dump(self.successful_links, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Ошибка сохранения прогресса: {e}")

    def is_already_processed(self, url):
        """Проверяет, не обрабатывалась ли уже эта ссылка"""
        # Проверяем в мёртвых ссылках
        for dead in self.dead_links:
            if dead['url'] == url:
                return True, 'dead'

        # Проверяем в успешных
        for success in self.successful_links:
            if success['url'] == url:
                return True, 'success'

        return False, None

    def download_file(self, url, filename, max_retries=2):
        """Скачивает файл с повторными попытками"""

        # Проверяем, не обрабатывали ли уже
        processed, status = self.is_already_processed(url)
        if processed:
            if status == 'dead':
                print(f" ⏭️ уже помечена как мёртвая", end='', flush=True)
                self.stats['dead_links'] += 1
                return None, 'dead'
            else:
                print(f" ⏭️ уже скачана", end='', flush=True)
                return None, 'skipped'

        # Проверяем, не скачан ли уже файл
        filepath = self.output_dir / filename
        if filepath.exists():
            self.successful_links.append({
                'url': url,
                'filename': filename,
                'date': datetime.now().isoformat()
            })
            return filepath, 'exists'

        for attempt in range(max_retries):
            try:
                # Случайная задержка перед запросом
                time.sleep(random.uniform(2, 4))

                headers = self.get_headers()

                # Делаем HEAD запрос сначала для проверки
                head_response = self.session.head(url, headers=headers, timeout=10, allow_redirects=True)

                if head_response.status_code == 404:
                    print(f" 🔍 404 (мёртвая ссылка)", end='', flush=True)
                    # Сохраняем в список мёртвых
                    self.dead_links.append({
                        'url': url,
                        'filename': filename,
                        'status': 404,
                        'date': datetime.now().isoformat()
                    })
                    self.stats['dead_links'] += 1
                    return None, 'dead'

                if head_response.status_code != 200:
                    print(f" 🔍 HTTP {head_response.status_code}", end='', flush=True)
                    if attempt == max_retries - 1:
                        self.dead_links.append({
                            'url': url,
                            'filename': filename,
                            'status': head_response.status_code,
                            'date': datetime.now().isoformat()
                        })
                        self.stats['dead_links'] += 1
                    continue

                print(f"\n      Попытка {attempt + 1}/{max_retries}...", end='', flush=True)

                # Скачиваем с потоком
                response = self.session.get(
                    url,
                    headers=headers,
                    timeout=30,
                    stream=True,
                    allow_redirects=True
                )

                if response.status_code == 200:
                    content_type = response.headers.get('content-type', '')
                    content_length = response.headers.get('content-length', 'unknown')

                    print(f" [{content_type}] [{content_length} bytes]", end='', flush=True)

                    # Если это ZIP, распаковываем
                    if 'zip' in content_type or url.endswith('.zip'):
                        result = self._handle_zip(response, filename)
                        if result:
                            self.successful_links.append({
                                'url': url,
                                'filename': result.name,
                                'date': datetime.now().isoformat()
                            })
                            return result, 'success'
                    else:
                        # Сохраняем PDF
                        with open(filepath, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)

                        self.successful_links.append({
                            'url': url,
                            'filename': filename,
                            'date': datetime.now().isoformat()
                        })
                        return filepath, 'success'
                else:
                    print(f" ❌ HTTP {response.status_code}")

            except requests.exceptions.ConnectionError as e:
                print(f" 🔌", end='', flush=True)
                time.sleep(random.uniform(5, 10))
            except Exception as e:
                print(f" ❌", end='', flush=True)
                time.sleep(random.uniform(3, 6))

        # Если все попытки провалились
        self.dead_links.append({
            'url': url,
            'filename': filename,
            'status': 'timeout',
            'date': datetime.now().isoformat()
        })
        self.stats['dead_links'] += 1
        return None, 'failed'

    def _handle_zip(self, response, original_filename):
        """Обрабатывает ZIP-архив"""
        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                # Ищем PDF в архиве
                pdf_files = [f for f in z.namelist() if f.lower().endswith('.pdf')]

                if pdf_files:
                    # Берём первый PDF
                    pdf_filename = pdf_files[0]
                    # Очищаем имя файла от путей
                    safe_filename = pdf_filename.replace('/', '_').replace('\\', '_')
                    pdf_path = self.output_dir / safe_filename

                    with z.open(pdf_files[0]) as pdf_file:
                        with open(pdf_path, 'wb') as f:
                            f.write(pdf_file.read())

                    return pdf_path
                else:
                    return None
        except Exception as e:
            return None

    def download_all(self, limit=None, start_from=0):
        """Скачивает все отчёты с возможностью возобновления"""

        print("\n" + "=" * 70)
        print("🚀 СКАЧИВАНИЕ ФИНАНСОВЫХ ОТЧЁТОВ")
        print("=" * 70)

        if not self.links_file.exists():
            print(f"❌ Файл {self.links_file} не найден")
            return

        df = pd.read_csv(self.links_file)
        self.stats['total'] = len(df)

        print(f"\n📊 Всего отчётов: {len(df)}")
        print(f"   Уже скачано: {self.stats.get('downloaded', 0)}")
        print(f"   Мёртвых ссылок: {self.stats.get('dead_links', 0)}")
        print(f"   Пропущено: {self.stats.get('skipped', 0)}")
        print(f"   Ошибок: {self.stats.get('failed', 0)}")

        # Если указан лимит, берём только первые N
        if limit:
            df = df.iloc[start_from:start_from + limit]
            print(f"\n🔍 Тестовый режим: скачиваем {limit} отчётов (начиная с {start_from})")

        print("\n📥 Начинаем скачивание...")

        for idx, row in df.iterrows():
            ticker = row['ticker']
            report_type = row['report_type']
            period = row['period'] if pd.notna(row['period']) else f"{row.get('date', 'unknown')}"
            url = row['url']

            # Очищаем период от недопустимых символов
            period = re.sub(r'[^\w\-_]', '', str(period))

            # Формируем имя файла
            filename = f"{ticker}_{report_type}_{period}.pdf"
            filepath = self.output_dir / filename

            print(f"\n   [{idx + 1}/{len(df)}] {filename} ...", end='', flush=True)

            result, status = self.download_file(url, filename)

            if status == 'success':
                self.stats['downloaded'] = self.stats.get('downloaded', 0) + 1
                print(f" ✅")
            elif status == 'dead':
                print(f" 💀 мёртвая ссылка")
            elif status == 'exists':
                print(f" ⏭️ уже есть")
                self.stats['skipped'] = self.stats.get('skipped', 0) + 1
            else:
                self.stats['failed'] = self.stats.get('failed', 0) + 1
                print(f" ❌")

            # Сохраняем прогресс после каждого файла
            if (idx + 1) % 5 == 0:
                self.save_progress()

            # Базовая задержка между файлами
            time.sleep(random.uniform(2, 4))

        self.save_progress()

        print(f"\n\n📊 РЕЗУЛЬТАТЫ СКАЧИВАНИЯ:")
        print(f"   Всего отчётов в списке: {self.stats['total']}")
        print(f"   Скачано успешно: {self.stats.get('downloaded', 0)}")
        print(f"   Мёртвых ссылок (404): {self.stats.get('dead_links', 0)}")
        print(f"   Пропущено (уже есть): {self.stats.get('skipped', 0)}")
        print(f"   Ошибок: {self.stats.get('failed', 0)}")
        print(f"\n📁 PDF сохранены в: {self.output_dir}")

        # Статистика по компаниям
        print(f"\n📊 ПО КОМПАНИЯМ:")
        for ticker in df['ticker'].unique():
            ticker_links = df[df['ticker'] == ticker]
            ticker_success = [s for s in self.successful_links if ticker in s['filename']]
            ticker_dead = [d for d in self.dead_links if ticker in d['filename']]
            print(f"   {ticker}: {len(ticker_success)}/{len(ticker_links)} скачано, {len(ticker_dead)} мёртвых")


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, help='Количество файлов для теста')
    parser.add_argument('--start', type=int, default=0, help='Начать с индекса')
    parser.add_argument('--retry-failed', action='store_true', help='Повторить только ошибки')

    args = parser.parse_args()

    downloader = ReportDownloader()

    if args.retry_failed:
        # TODO: реализовать повтор ошибок
        print("🔄 Функция повторения ошибок будет позже")
    else:
        downloader.download_all(limit=args.limit, start_from=args.start)


if __name__ == "__main__":
    # Тестовый запуск с 5 файлами
    downloader = ReportDownloader()
    downloader.download_all()