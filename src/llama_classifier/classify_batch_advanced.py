# src/llama_classifier/classify_batch_advanced.py

"""
Продвинутая пакетная классификация комментариев через llama-server
С чанковой записью, возобновлением и подробной статистикой
"""

import json
import pandas as pd
import numpy as np
from openai import OpenAI
from tqdm import tqdm
import time
import sys
import signal
from pathlib import Path
import argparse
from datetime import datetime
from collections import defaultdict

# Добавляем путь к проекту
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR, FEATURES_DIR


class AdvancedQwenClassifier:
    """
    Продвинутый классификатор с чанковой записью и возобновлением
    """

    def __init__(self, base_url="http://127.0.0.1:8001/v1", chunk_size=500):
        self.client = OpenAI(
            base_url=base_url,
            api_key="sk-no-key-required"
        )
        self.chunk_size = chunk_size
        self.output_dir = FEATURES_DIR / "qwen35_classified"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Статистика
        self.stats = {
            'sentiment': defaultdict(int),
            'category': defaultdict(int),
            'errors': 0,
            'total_processed': 0,
            'chunks_saved': 0,
            'start_time': None
        }

        self.interrupted = False
        signal.signal(signal.SIGINT, self._signal_handler)

        # Проверка сервера
        self._check_server()

    def _signal_handler(self, sig, frame):
        print("\n\n⚠️ Получен сигнал прерывания. Сохраняем прогресс...")
        self.interrupted = True

    def _check_server(self):
        """Проверяет доступность сервера"""
        try:
            self.client.models.list()
            print("✅ Сервер доступен")
            return True
        except Exception as e:
            print(f"❌ Сервер не доступен: {e}")
            print("   Запустите: src/llama_classifier/start_server.sh")
            return False

    def _get_last_processed(self):
        """Возвращает количество уже обработанных комментариев"""
        # Проверяем существующие чанки
        chunk_files = sorted(self.output_dir.glob("chunk_*.csv"))
        if chunk_files:
            total = 0
            for f in chunk_files:
                df = pd.read_csv(f)
                total += len(df)
            return total
        return 0

    def classify_comment(self, text, verbose=False):
        """Классифицирует один комментарий"""
        if not text or len(text.strip()) < 5:
            return {"s": "neu", "t": "other"}

        try:
            response = self.client.chat.completions.create(
                model="unsloth/Qwen3.5-9B-GGUF",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a classifier. Return ONLY JSON: {\"s\":\"pos|neg|neu\", \"t\":\"price|div|rep|macro|news|other\"}"
                    },
                    {"role": "user", "content": f'Analyze: "{text[:500]}"'}
                ],
                temperature=0,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                timeout=30
            )

            result_text = response.choices[0].message.content
            if verbose:
                print(f"   Ответ: {result_text}")

            return json.loads(result_text)

        except Exception as e:
            if verbose:
                print(f"   ❌ Ошибка: {e}")
            self.stats['errors'] += 1
            return {"s": "neu", "t": "other"}

    def process_chunk(self, chunk, chunk_num, verbose=False):
        """Обрабатывает один чанк"""
        results = []
        start_time = time.time()

        with tqdm(total=len(chunk), desc=f"   Чанк {chunk_num}",
                  unit="комм", position=0, leave=False) as pbar:

            for idx, row in chunk.iterrows():
                if self.interrupted:
                    return None

                text = str(row['text']) if pd.notna(row['text']) else ''
                result = self.classify_comment(text, verbose and idx < 3)

                s = result.get('s', 'neu')
                t = result.get('t', 'other')

                sentiment = {'pos': 'POSITIVE', 'neg': 'NEGATIVE', 'neu': 'NEUTRAL'}.get(s, 'NEUTRAL')
                category = {
                    'price': 'PRICE', 'div': 'DIVIDENDS', 'rep': 'REPORTS',
                    'macro': 'MACRO', 'news': 'NEWS', 'other': 'OTHER'
                }.get(t, 'OTHER')

                record = {
                    'comment_id': row.get('comment_id', idx),
                    'ticker': row['ticker'],
                    'company': row.get('company', ''),
                    'date': row.get('datetime', row.get('date_raw', '')),
                    'text': text[:300],
                    'rating': row.get('rating', 0),
                    'sentiment': sentiment,
                    'category': category,
                    'classified_at': datetime.now().isoformat()
                }
                results.append(record)

                self.stats['sentiment'][sentiment] += 1
                self.stats['category'][category] += 1
                self.stats['total_processed'] += 1

                pbar.set_postfix({
                    'P': self.stats['sentiment'].get('POSITIVE', 0),
                    'N': self.stats['sentiment'].get('NEGATIVE', 0),
                    'Err': self.stats['errors']
                })

                pbar.update(1)
                time.sleep(0.05)

        if results:
            chunk_file = self.output_dir / f"chunk_{chunk_num:04d}.csv"
            df_chunk = pd.DataFrame(results)
            df_chunk.to_csv(chunk_file, index=False, encoding='utf-8')
            self.stats['chunks_saved'] += 1

            elapsed = time.time() - start_time
            speed = len(results) / elapsed if elapsed > 0 else 0

            print(f"\n   ✅ Чанк {chunk_num}: {len(results)} записей | {speed:.2f} комм/сек")
            print(f"      👍 POSITIVE: {self.stats['sentiment']['POSITIVE']} | "
                  f"👎 NEGATIVE: {self.stats['sentiment']['NEGATIVE']} | "
                  f"😐 NEUTRAL: {self.stats['sentiment']['NEUTRAL']}")
            print(f"      ❌ Ошибок: {self.stats['errors']}")

        return results

    def classify_all(self, sample_size=None, verbose=False):
        """Основной метод классификации с автоматическим продолжением"""

        print("\n" + "=" * 70)
        print("🚀 КЛАССИФИКАЦИЯ КОММЕНТАРИЕВ (QWEN3.5)")
        print(f"   Чанк: {self.chunk_size} записей")
        print("=" * 70)

        input_file = RAW_DATA_DIR / "forum_comments" / "forum_comments_all.csv"

        if not input_file.exists():
            print(f"❌ Файл не найден: {input_file}")
            return None

        # Загружаем данные
        print(f"\n📚 Загрузка данных...")
        df = pd.read_csv(input_file)
        df = df[df['text'].notna() & (df['text'].str.len() > 10)]

        # Определяем, сколько уже обработано
        already_processed = self._get_last_processed()
        print(f"   Уже обработано: {already_processed:,} комментариев")

        if sample_size:
            df = df.head(sample_size)

        # Пропускаем уже обработанные
        if already_processed > 0:
            df = df.iloc[already_processed:]
            print(f"   Осталось обработать: {len(df):,} комментариев")

        print(f"   Всего к обработке: {len(df):,}")

        if sample_size and sample_size <= 100:
            print("\n🔍 ТЕСТОВЫЙ РЕЖИМ С ОТЛАДКОЙ")
            verbose = True

        # Оценка времени
        if len(df) > 0:
            est_seconds = len(df) * 0.45
            print(f"⏱️ Оценочное время: {est_seconds / 60:.1f} мин")
        else:
            print("✅ Все комментарии уже обработаны!")
            return None

        # Обрабатываем чанками
        self.stats['start_time'] = time.time()
        all_results = []
        chunk_num = already_processed // self.chunk_size + 1

        for i in range(0, len(df), self.chunk_size):
            if self.interrupted:
                break

            chunk = df.iloc[i:i + self.chunk_size]

            print(f"\n📦 Чанк {chunk_num} ({len(chunk)} записей)")

            results = self.process_chunk(chunk, chunk_num, verbose)
            if results:
                all_results.extend(results)

            chunk_num += 1

        # Финальное сохранение
        if all_results:
            self._save_final()

        self._print_stats()

        return True

    def _save_final(self):
        """Сохраняет финальный объединённый файл"""
        chunk_files = sorted(self.output_dir.glob("chunk_*.csv"))

        if not chunk_files:
            return

        print(f"\n📦 Объединение {len(chunk_files)} чанков...")

        all_dfs = []
        for f in chunk_files:
            df = pd.read_csv(f)
            all_dfs.append(df)

        final_df = pd.concat(all_dfs, ignore_index=True)

        csv_file = self.output_dir / "qwen35_classified_all.csv"
        final_df.to_csv(csv_file, index=False, encoding='utf-8')

        json_file = self.output_dir / "qwen35_classified_all.json"
        final_df.to_json(json_file, orient='records', force_ascii=False, indent=2)

        print(f"\n✅ Финальное сохранение:")
        print(f"   CSV: {csv_file}")
        print(f"   JSON: {json_file}")
        print(f"   Всего: {len(final_df):,} комментариев")

    def _print_stats(self):
        """Выводит статистику"""
        total = self.stats['total_processed']
        if total == 0:
            return

        elapsed = time.time() - self.stats['start_time']

        print("\n" + "=" * 70)
        print("📊 ИТОГОВАЯ СТАТИСТИКА")
        print("=" * 70)

        print(f"\n⏱️ Общее время: {elapsed / 60:.1f} мин")
        if total > 0:
            print(f"🚀 Средняя скорость: {total / elapsed:.2f} комм/сек")

        print("\n📈 ТОНАЛЬНОСТЬ:")
        for sent, count in sorted(self.stats['sentiment'].items(), key=lambda x: -x[1]):
            pct = count / total * 100
            bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
            print(f"   {sent:10}: {count:6,} ({pct:5.1f}%) {bar}")

        print("\n📂 КАТЕГОРИИ:")
        for cat, count in sorted(self.stats['category'].items(), key=lambda x: -x[1]):
            pct = count / total * 100
            print(f"   {cat:12}: {count:6,} ({pct:5.1f}%)")

        print(f"\n✅ Успешно: {total:,}")
        print(f"❌ Ошибок: {self.stats['errors']:,}")
        print(f"📦 Сохранено чанков: {self.stats['chunks_saved']}")


def main():
    parser = argparse.ArgumentParser(description='Классификация комментариев через Qwen3.5')
    parser.add_argument('--sample', type=int, default=None, help='Количество комментариев')
    parser.add_argument('--full', action='store_true', help='Полная классификация всех комментариев')
    parser.add_argument('--chunk', type=int, default=500, help='Размер чанка')
    parser.add_argument('--verbose', action='store_true', help='Подробный вывод')

    args = parser.parse_args()

    classifier = AdvancedQwenClassifier(chunk_size=args.chunk)

    if args.full:
        print("\n🚀 ПОЛНАЯ КЛАССИФИКАЦИЯ ВСЕХ КОММЕНТАРИЕВ")
        confirm = input("   Продолжить? (y/n): ")
        if confirm.lower() == 'y':
            classifier.classify_all(verbose=args.verbose)
    elif args.sample:
        print(f"\n🧪 ТЕСТ: {args.sample} комментариев")
        classifier.classify_all(sample_size=args.sample, verbose=args.verbose)
    else:
        print("\n🧪 ТЕСТ ПО УМОЛЧАНИЮ: 100 комментариев")
        classifier.classify_all(sample_size=100, verbose=args.verbose)


if __name__ == "__main__":
    main()