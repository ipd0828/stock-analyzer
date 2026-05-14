# src/llm_labeling/analyze_official_news.py

"""
Расширенный анализ тональности официальных новостей (без пауз)
"""

import json
import pandas as pd
import time
import sys
from pathlib import Path
from tqdm import tqdm
from openai import OpenAI

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import PROCESSED_DATA_DIR, FEATURES_DIR


class NewsAnalyzer:
    """
    Анализ тональности официальных новостей
    """

    def __init__(self, base_url="http://127.0.0.1:8001/v1"):
        self.client = OpenAI(
            base_url=base_url,
            api_key="sk-no-key-required"
        )
        self.input_file = PROCESSED_DATA_DIR / "official_news_all.csv"
        self.output_dir = FEATURES_DIR / "news_sentiment"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Файл для прогресса
        self.progress_file = self.output_dir / "analysis_progress.json"

    def get_analysis_prompt(self):
        """Промпт для анализа новости"""
        return '''Ты — финансовый аналитик. Проанализируй новость и верни JSON:

{{
    "sentiment_intensity": "STRONG_POSITIVE|POSITIVE|NEUTRAL|NEGATIVE|STRONG_NEGATIVE",
    "numeric_score": -2 до +2,
    "expected_price_impact_percent": -15 до +15,
    "impact_horizon": "SHORT_TERM|MEDIUM_TERM|LONG_TERM",
    "category": "EARNINGS|DIVIDENDS|GUIDANCE|MACRO|CORPORATE|REGULATORY|OTHER",
    "key_drivers": ["драйвер1", "драйвер2"],
    "risks": ["риск1", "риск2"],
    "confidence": 0-1,
    "reasoning": "обоснование"
}}

Новость: {text}'''

    def analyze_news(self, text, max_length=3000):
        """Анализирует одну новость"""
        if not text or len(text.strip()) < 50:
            return {
                'sentiment_intensity': 'NEUTRAL',
                'numeric_score': 0,
                'expected_price_impact_percent': 0,
                'impact_horizon': 'SHORT_TERM',
                'category': 'OTHER',
                'key_drivers': [],
                'risks': [],
                'confidence': 0.0,
                'reasoning': 'Недостаточно текста'
            }

        prompt = self.get_analysis_prompt().format(text=text[:max_length])

        try:
            response = self.client.chat.completions.create(
                model="unsloth/Qwen3.5-9B-GGUF",
                messages=[
                    {"role": "system", "content": "You are a financial analyst. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                timeout=60
            )

            result_text = response.choices[0].message.content
            # Очищаем от возможных Markdown
            result_text = result_text.strip()
            if result_text.startswith('```json'):
                result_text = result_text[7:]
            if result_text.startswith('```'):
                result_text = result_text[3:]
            if result_text.endswith('```'):
                result_text = result_text[:-3]

            return json.loads(result_text)

        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            return {
                'sentiment_intensity': 'NEUTRAL',
                'numeric_score': 0,
                'expected_price_impact_percent': 0,
                'impact_horizon': 'SHORT_TERM',
                'category': 'OTHER',
                'key_drivers': [],
                'risks': [],
                'confidence': 0.0,
                'reasoning': f'Ошибка: {e}'
            }

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

    def analyze_all(self, limit=None, start_year=None):
        """Анализирует все новости (без пауз)"""

        print("\n" + "=" * 70)
        print("🚀 АНАЛИЗ ТОНАЛЬНОСТИ ОФИЦИАЛЬНЫХ НОВОСТЕЙ")
        print("=" * 70)

        if not self.input_file.exists():
            print(f"❌ Файл не найден: {self.input_file}")
            return

        df = pd.read_csv(self.input_file)
        print(f"📚 Загружено {len(df)} новостей")

        # Фильтруем по году
        if start_year:
            df['year'] = pd.to_datetime(df['date']).dt.year
            df = df[df['year'] >= start_year]
            print(f"   С {start_year} года: {len(df)}")

        # Фильтруем только с текстом
        df = df[df['text'].notna() & (df['text'].str.len() > 50)]
        print(f"   С текстом: {len(df)}")

        if limit:
            df = df.head(limit)
            print(f"   Тестовый режим: {limit}")

        # Загружаем прогресс
        progress = self.load_progress()
        processed_ids = set(progress.get('processed', []))

        # Фильтруем необработанные
        df_to_process = df[~df.index.isin(processed_ids)]
        print(f"   Осталось обработать: {len(df_to_process)}")

        if len(df_to_process) == 0:
            print("✅ Все новости уже обработаны!")
            return

        # Результаты
        results = []
        success_count = 0
        start_time = time.time()

        for idx, row in tqdm(df_to_process.iterrows(), total=len(df_to_process), desc="Анализ"):
            print(f"\n   📰 {row['ticker']} | {row['title'][:60]}...")

            analysis = self.analyze_news(row['text'])

            # Сохраняем результат
            result = {
                'ticker': row['ticker'],
                'company': row['company'],
                'date': row['date'],
                'title': row['title'],
                'url': row['url'],
                'sentiment_intensity': analysis.get('sentiment_intensity', 'NEUTRAL'),
                'numeric_score': analysis.get('numeric_score', 0),
                'expected_price_impact': analysis.get('expected_price_impact_percent', 0),
                'impact_horizon': analysis.get('impact_horizon', 'SHORT_TERM'),
                'category': analysis.get('category', 'OTHER'),
                'key_drivers': json.dumps(analysis.get('key_drivers', []), ensure_ascii=False),
                'risks': json.dumps(analysis.get('risks', []), ensure_ascii=False),
                'confidence': analysis.get('confidence', 0),
                'reasoning': analysis.get('reasoning', ''),
                'analyzed_at': pd.Timestamp.now().isoformat()
            }
            results.append(result)

            if analysis.get('confidence', 0) > 0.5:
                success_count += 1

            # Обновляем прогресс
            processed_ids.add(idx)
            progress['processed'] = list(processed_ids)
            progress['last_index'] = idx
            self.save_progress(progress)

            # Показываем скорость
            elapsed = time.time() - start_time
            speed = len(results) / elapsed if elapsed > 0 else 0
            print(
                f"      ✅ {analysis.get('sentiment_intensity')} | влияние: {analysis.get('expected_price_impact_percent', 0):+.1f}% | скор: {speed:.1f}/сек")

        # Финальное сохранение
        self._save_final(df, results, success_count)

        # Выводим статистику
        self._print_stats(results)

    def _save_final(self, original_df, results, success_count):
        """Сохраняет финальные результаты"""
        df_results = pd.DataFrame(results)

        # Сохраняем отдельно
        csv_file = self.output_dir / "news_sentiment_all.csv"
        df_results.to_csv(csv_file, index=False, encoding='utf-8')

        json_file = self.output_dir / "news_sentiment_all.json"
        df_results.to_json(json_file, orient='records', force_ascii=False, indent=2)

        print(f"\n📁 Сохранено: {csv_file}")

        # Объединяем с исходными данными
        merged = original_df.merge(
            df_results[['url', 'sentiment_intensity', 'numeric_score', 'expected_price_impact',
                        'impact_horizon', 'category', 'confidence']],
            on='url',
            how='left'
        )

        full_file = self.output_dir / "official_news_with_sentiment.csv"
        merged.to_csv(full_file, index=False, encoding='utf-8')
        print(f"📁 Полный файл: {full_file}")
        print(f"\n✅ Успешно обработано: {success_count}/{len(results)}")

    def _print_stats(self, results):
        """Выводит статистику"""
        df = pd.DataFrame(results)

        print("\n" + "=" * 70)
        print("📊 СТАТИСТИКА АНАЛИЗА")
        print("=" * 70)

        print("\n📈 РАСПРЕДЕЛЕНИЕ ПО ТОНАЛЬНОСТИ:")
        sentiment_counts = df['sentiment_intensity'].value_counts()
        for sent, count in sentiment_counts.items():
            pct = count / len(df) * 100
            print(f"   {sent}: {count} ({pct:.1f}%)")

        print("\n📂 ПО КАТЕГОРИЯМ:")
        category_counts = df['category'].value_counts()
        for cat, count in category_counts.head(10).items():
            pct = count / len(df) * 100
            print(f"   {cat}: {count} ({pct:.1f}%)")

        print("\n🎯 ОЖИДАЕМОЕ ВЛИЯНИЕ НА ЦЕНУ:")
        print(f"   Среднее: {df['expected_price_impact'].mean():.2f}%")
        print(f"   Медиана: {df['expected_price_impact'].median():.2f}%")
        print(f"   Макс: {df['expected_price_impact'].max():.2f}%")
        print(f"   Мин: {df['expected_price_impact'].min():.2f}%")

        print("\n⏱️ ГОРИЗОНТ ВЛИЯНИЯ:")
        horizon_counts = df['impact_horizon'].value_counts()
        for horizon, count in horizon_counts.items():
            pct = count / len(df) * 100
            print(f"   {horizon}: {count} ({pct:.1f}%)")

        print(f"\n🎯 СРЕДНЯЯ УВЕРЕННОСТЬ: {df['confidence'].mean():.2f}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', type=int, help='Тестовый режим (N новостей)')
    parser.add_argument('--year', type=int, help='Анализировать только с указанного года')

    args = parser.parse_args()

    analyzer = NewsAnalyzer()

    if args.test:
        print(f"\n🧪 ТЕСТ: {args.test} новостей")
        analyzer.analyze_all(limit=args.test, start_year=args.year)
    else:
        print("\n🚀 ПОЛНЫЙ АНАЛИЗ")
        analyzer.analyze_all(start_year=args.year)


if __name__ == "__main__":
    main()