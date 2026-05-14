# src/llm_labeling/analyze_financial_news_advanced.py

"""
Расширенный финансовый анализ новостей
С учётом денежного потока, долга и качества роста
"""

import json
from openai import OpenAI
import pandas as pd
from tqdm import tqdm
import time
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR, FEATURES_DIR


class AdvancedFinancialAnalyzer:
    """
    Расширенный анализ финансовых новостей
    """

    def __init__(self, base_url="http://127.0.0.1:8001/v1"):
        self.client = OpenAI(
            base_url=base_url,
            api_key="sk-no-key-required"
        )

    def get_analysis_prompt(self):
        """Расширенный промпт с учётом финансовых метрик"""
        return """Ты — финансовый аналитик с опытом оценки публичных компаний. Проанализируй новость и дай количественную оценку влияния на акции.

Новость: {text}

Верни ТОЛЬКО JSON со следующей структурой:
{{
    "overall_assessment": {{
        "sentiment": "STRONG_POSITIVE|POSITIVE|NEUTRAL|NEGATIVE|STRONG_NEGATIVE",
        "score": -2 до +2,
        "expected_price_impact_percent": -15 до +15,
        "impact_horizon": "SHORT_TERM|MEDIUM_TERM|LONG_TERM"
    }},
    "financial_metrics": {{
        "revenue_growth_percent": null или число (год к году),
        "profit_growth_percent": null или число,
        "fcf_growth_percent": null или число (свободный денежный поток),
        "debt_change_percent": null или число (изменение долга),
        "net_debt_to_ebitda": null или число,
        "roe_percent": null или число,
        "roa_percent": null или число
    }},
    "quality_assessment": {{
        "profit_quality": "HIGH|MEDIUM|LOW",  # насколько прибыль обеспечена деньгами
        "debt_burden": "HIGH|MEDIUM|LOW",     # долговая нагрузка
        "growth_sustainability": "HIGH|MEDIUM|LOW"  # устойчивость роста
    }},
    "category": "EARNINGS|DIVIDENDS|GUIDANCE|MACRO|CORPORATE|REGULATORY|DEBT|CASHFLOW",
    "confidence": 0-1,
    "key_drivers": ["драйвер1", "драйвер2"],
    "risks": ["риск1", "риск2"],
    "reasoning": "краткое обоснование"
}}

Правила оценки качества:
1. profit_quality:
   - HIGH: FCF растёт быстрее или сопоставимо с прибылью
   - MEDIUM: FCF растёт, но медленнее прибыли
   - LOW: прибыль растёт, а FCF падает (бумажный рост)

2. debt_burden:
   - HIGH: Net Debt/EBITDA > 3 или долг растёт быстрее прибыли
   - MEDIUM: Net Debt/EBITDA 1-3
   - LOW: Net Debt/EBITDA < 1 или долг снижается

3. growth_sustainability:
   - HIGH: рост органический, FCF положительный, долг контролируемый
   - MEDIUM: рост за счёт приобретений или высокой закредитованности
   - LOW: рост неустойчивый, FCF отрицательный, долг растёт

Важно: учитывай соотношение роста прибыли и долга. Если прибыль выросла на 20%, а долг на 30% — это негативный сигнал."""

    def analyze_news(self, text, max_length=3000):
        """Анализирует одну новость"""
        if not text or len(text) < 50:
            return None

        prompt = self.get_analysis_prompt().format(text=text[:max_length])

        try:
            response = self.client.chat.completions.create(
                model="unsloth/Qwen3.5-9B-GGUF",
                messages=[
                    {"role": "system", "content": "You are a financial analyst. Return only JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                timeout=60
            )

            result_text = response.choices[0].message.content
            return json.loads(result_text)

        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            return None

    def analyze_batch(self, texts, delay=0.3):
        """Анализирует батч новостей"""
        results = []

        for text in tqdm(texts, desc="Анализ новостей"):
            result = self.analyze_news(text)
            results.append(result)
            time.sleep(delay)

        return results

    def analyze_sber_news(self):
        """Анализирует официальные новости Сбера"""

        print("\n" + "=" * 70)
        print("🚀 РАСШИРЕННЫЙ ФИНАНСОВЫЙ АНАЛИЗ НОВОСТЕЙ СБЕРА")
        print("   Учёт: денежный поток, долг, качество роста")
        print("=" * 70)

        # Загружаем новости
        input_file = RAW_DATA_DIR / "sber_official_news" / "sber_official_news_with_text.csv"

        if not input_file.exists():
            print(f"❌ Файл не найден: {input_file}")
            return None

        df = pd.read_csv(input_file)
        print(f"📚 Загружено {len(df)} новостей")

        # Анализируем
        print("\n🔄 Анализ (это может занять время)...")
        analyses = self.analyze_batch(df['text'].tolist())

        # Сохраняем результаты
        df['analysis'] = analyses

        # Извлекаем поля
        def extract_field(a, path, default=None):
            if not a:
                return default
            for key in path:
                if key not in a:
                    return default
                a = a[key]
            return a

        df['sentiment'] = [extract_field(a, ['overall_assessment', 'sentiment']) for a in analyses]
        df['score'] = [extract_field(a, ['overall_assessment', 'score']) for a in analyses]
        df['price_impact'] = [extract_field(a, ['overall_assessment', 'expected_price_impact_percent']) for a in
                              analyses]
        df['impact_horizon'] = [extract_field(a, ['overall_assessment', 'impact_horizon']) for a in analyses]

        df['revenue_growth'] = [extract_field(a, ['financial_metrics', 'revenue_growth_percent']) for a in analyses]
        df['profit_growth'] = [extract_field(a, ['financial_metrics', 'profit_growth_percent']) for a in analyses]
        df['fcf_growth'] = [extract_field(a, ['financial_metrics', 'fcf_growth_percent']) for a in analyses]
        df['debt_change'] = [extract_field(a, ['financial_metrics', 'debt_change_percent']) for a in analyses]
        df['net_debt_to_ebitda'] = [extract_field(a, ['financial_metrics', 'net_debt_to_ebitda']) for a in analyses]

        df['profit_quality'] = [extract_field(a, ['quality_assessment', 'profit_quality']) for a in analyses]
        df['debt_burden'] = [extract_field(a, ['quality_assessment', 'debt_burden']) for a in analyses]
        df['growth_sustainability'] = [extract_field(a, ['quality_assessment', 'growth_sustainability']) for a in
                                       analyses]

        df['category_detail'] = [extract_field(a, ['category']) for a in analyses]
        df['confidence'] = [extract_field(a, ['confidence']) for a in analyses]
        df['key_drivers'] = [
            json.dumps(extract_field(a, ['key_drivers'])) if extract_field(a, ['key_drivers']) else None for a in
            analyses]
        df['risks'] = [json.dumps(extract_field(a, ['risks'])) if extract_field(a, ['risks']) else None for a in
                       analyses]
        df['reasoning'] = [extract_field(a, ['reasoning']) for a in analyses]

        # Сохраняем
        output_file = FEATURES_DIR / "sber_news_advanced_analysis.csv"
        df.to_csv(output_file, index=False, encoding='utf-8')

        print(f"\n✅ Сохранено: {output_file}")

        # Статистика
        self._print_stats(df)

        return df

    def _print_stats(self, df):
        """Выводит статистику"""
        print("\n" + "=" * 70)
        print("📊 СТАТИСТИКА АНАЛИЗА")
        print("=" * 70)

        print("\n📈 ТОНАЛЬНОСТЬ:")
        if df['sentiment'].notna().any():
            for sent in ['STRONG_POSITIVE', 'POSITIVE', 'NEUTRAL', 'NEGATIVE', 'STRONG_NEGATIVE']:
                count = (df['sentiment'] == sent).sum()
                if count > 0:
                    pct = count / len(df) * 100
                    print(f"   {sent}: {count} ({pct:.1f}%)")

        print("\n💰 ФИНАНСОВЫЕ МЕТРИКИ:")
        if df['profit_growth'].notna().any():
            avg_profit = df['profit_growth'].mean()
            print(f"   Средний рост прибыли: {avg_profit:.1f}%")

        if df['fcf_growth'].notna().any():
            avg_fcf = df['fcf_growth'].mean()
            print(f"   Средний рост FCF: {avg_fcf:.1f}%")

        if df['debt_change'].notna().any():
            avg_debt = df['debt_change'].mean()
            print(f"   Среднее изменение долга: {avg_debt:.1f}%")

        print("\n📊 КАЧЕСТВО РОСТА:")
        if df['profit_quality'].notna().any():
            for q in ['HIGH', 'MEDIUM', 'LOW']:
                count = (df['profit_quality'] == q).sum()
                if count > 0:
                    pct = count / len(df) * 100
                    print(f"   Качество прибыли {q}: {count} ({pct:.1f}%)")

        print("\n💳 ДОЛГОВАЯ НАГРУЗКА:")
        if df['debt_burden'].notna().any():
            for b in ['HIGH', 'MEDIUM', 'LOW']:
                count = (df['debt_burden'] == b).sum()
                if count > 0:
                    pct = count / len(df) * 100
                    print(f"   Нагрузка {b}: {count} ({pct:.1f}%)")

        print("\n🎯 СРЕДНЯЯ ОЦЕНКА ВЛИЯНИЯ:")
        if df['price_impact'].notna().any():
            avg_impact = df['price_impact'].mean()
            print(f"   Ожидаемое влияние на цену: {avg_impact:.2f}%")

        if df['confidence'].notna().any():
            avg_conf = df['confidence'].mean()
            print(f"   Средняя уверенность: {avg_conf:.2f}")


def main():
    analyzer = AdvancedFinancialAnalyzer()
    analyzer.analyze_sber_news()


if __name__ == "__main__":
    main()