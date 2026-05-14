# src/ml_models/structural_breaks_analysis.py
# РАСШИРЕННАЯ ВЕРСИЯ: анализ ВСЕХ компонент информационного фона

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import sys
import warnings
from scipy import stats
from scipy.stats import ttest_ind, mannwhitneyu
import statsmodels.api as sm

warnings.filterwarnings('ignore')

# === ИСПРАВЛЕННЫЙ ИМПОРТ ===
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import PROCESSED_DATA_DIR  # <-- ВОТ ЭТО БЫЛО ПРОПУЩЕНО

plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams['figure.figsize'] = (16, 10)
plt.rcParams['font.size'] = 11


class StructuralBreakAnalyzer:
    """Анализ структурных сдвигов во ВСЕХ компонентах информационного фона"""

    def __init__(self):
        self.data_path = PROCESSED_DATA_DIR / "gazp_financial_data/GAZP_complete_dataset.csv"
        self.df = None
        self.output_dir = Path("data/ml_models/structural_breaks")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Ключевые даты
        self.key_events = {
            'covid_start': '2020-03-11',
            'svo_start': '2022-02-24',
            'mobilization': '2022-09-21',
            'sanctions_peak': '2022-12-05',
            'dividend_cancel': '2023-05-23',
        }

        # === ВСЕ КОМПОНЕНТЫ ИНФОРМАЦИОННОГО ФОНА ===
        self.info_variables = {
            # Lenta - тематические категории
            'lenta_war': 'Военная тема',
            'lenta_political': 'Политика',
            'lenta_sanctions': 'Санкции',
            'lenta_oil_gas': 'Нефть/газ',
            'lenta_market': 'Рынок',
            'lenta_negative': 'Негатив (Lenta)',
            'lenta_positive': 'Позитив (Lenta)',
            'lenta_neutral': 'Нейтрально (Lenta)',
            'lenta_total': 'Всего (Lenta)',

            # SmartLab - тематические категории
            'comments_negative': 'Негатив (SmartLab)',
            'comments_positive': 'Позитив (SmartLab)',
            'comments_neutral': 'Нейтрально (SmartLab)',
            'comments_price': 'Обсуждение цены',
            'comments_dividends': 'Обсуждение дивидендов',
            'comments_reports': 'Обсуждение отчетов',
            'comments_macro': 'Макроэкономика',
            'comments_news': 'Новости',
            'comments_total': 'Всего (SmartLab)',
        }

        self.results = {}

    def load_data(self):
        """Загружает данные"""
        print("=" * 80)
        print("📥 ЗАГРУЗКА ДАННЫХ")
        print("=" * 80)

        self.df = pd.read_csv(self.data_path)
        self.df['date'] = pd.to_datetime(self.df['date'])
        self.df = self.df.sort_values('date').reset_index(drop=True)

        # Проверяем наличие всех переменных
        available_vars = []
        for var in self.info_variables:
            if var in self.df.columns:
                available_vars.append(var)
            else:
                print(f"   ⚠️ {var} не найден в датасете")

        self.available_vars = available_vars

        print(f"✅ Загружено {len(self.df)} записей")
        print(f"   Доступно переменных: {len(available_vars)}/{len(self.info_variables)}")

        return self.df

    def test_all_info_variables(self, event_date: str, window_days: int = 60):
        """
        Тестирует структурный сдвиг для ВСЕХ переменных информационного фона
        """
        event_dt = pd.to_datetime(event_date)

        before_mask = (self.df['date'] >= event_dt - pd.Timedelta(days=window_days)) & \
                      (self.df['date'] < event_dt)
        after_mask = (self.df['date'] > event_dt) & \
                     (self.df['date'] <= event_dt + pd.Timedelta(days=window_days))

        before = self.df[before_mask]
        after = self.df[after_mask]

        if len(before) < 10 or len(after) < 10:
            return None

        results = {}

        for var in self.available_vars:
            before_vals = before[var].dropna().values
            after_vals = after[var].dropna().values

            if len(before_vals) < 5 or len(after_vals) < 5:
                continue

            t_stat, t_p = ttest_ind(before_vals, after_vals)

            mean_before = np.mean(before_vals)
            mean_after = np.mean(after_vals)

            if mean_before != 0:
                change_pct = ((mean_after - mean_before) / mean_before) * 100
            else:
                change_pct = np.nan

            results[var] = {
                'mean_before': mean_before,
                'mean_after': mean_after,
                'change_pct': change_pct,
                't_pvalue': t_p,
                'significant': t_p < 0.05,
                'significance_level': '***' if t_p < 0.001 else ('**' if t_p < 0.01 else ('*' if t_p < 0.05 else ''))
            }

        return results

    def analyze_all_events_all_variables(self):
        """Анализирует все события для всех переменных"""
        print("\n" + "=" * 80)
        print("📊 ПОЛНЫЙ АНАЛИЗ: ВСЕ СОБЫТИЯ × ВСЕ ПЕРЕМЕННЫЕ")
        print("=" * 80)

        all_results = {}

        for event_name, event_date in self.key_events.items():
            print(f"\n📍 {event_name}: {event_date}")
            results = self.test_all_info_variables(event_date)

            if results:
                all_results[event_name] = results

                # Группируем значимые изменения
                significant_increases = []
                significant_decreases = []

                for var, stats in results.items():
                    if stats['significant']:
                        if stats['change_pct'] > 0:
                            significant_increases.append((var, stats))
                        else:
                            significant_decreases.append((var, stats))

                # Выводим топ-5 рост
                if significant_increases:
                    print(f"\n   📈 РОСТ:")
                    for var, stats in sorted(significant_increases, key=lambda x: -x[1]['change_pct'])[:5]:
                        print(
                            f"      {self.info_variables[var]:25s}: {stats['change_pct']:+.1f}% {stats['significance_level']}")

                # Выводим топ-5 падение
                if significant_decreases:
                    print(f"\n   📉 ПАДЕНИЕ:")
                    for var, stats in sorted(significant_decreases, key=lambda x: x[1]['change_pct'])[:5]:
                        print(
                            f"      {self.info_variables[var]:25s}: {stats['change_pct']:+.1f}% {stats['significance_level']}")

        self.results['all_events'] = all_results
        return all_results

    def create_heatmap_data(self):
        """Создает данные для heatmap структурных сдвигов"""
        print("\n" + "=" * 80)
        print("📊 HEATMAP СТРУКТУРНЫХ СДВИГОВ")
        print("=" * 80)

        if 'all_events' not in self.results:
            self.analyze_all_events_all_variables()

        all_results = self.results['all_events']

        # Собираем матрицу
        events = list(all_results.keys())

        # Выбираем наиболее важные переменные для отображения
        key_vars = ['lenta_war', 'lenta_sanctions', 'lenta_negative',
                    'comments_negative', 'comments_price', 'comments_dividends']
        key_vars = [v for v in key_vars if v in self.available_vars]

        # Создаем матрицу изменений
        matrix_data = []
        for event in events:
            row = []
            for var in key_vars:
                if var in all_results[event]:
                    change = all_results[event][var]['change_pct']
                    sig = all_results[event][var]['significant']
                    row.append(change if sig else 0)
                else:
                    row.append(0)
            matrix_data.append(row)

        df_matrix = pd.DataFrame(matrix_data, index=events, columns=key_vars)

        # Визуализация
        fig, ax = plt.subplots(figsize=(14, 8))

        # Маска для незначимых
        mask = np.zeros_like(df_matrix.values, dtype=bool)
        for i, event in enumerate(events):
            for j, var in enumerate(key_vars):
                if var in all_results[event]:
                    mask[i, j] = not all_results[event][var]['significant']

        sns.heatmap(df_matrix, annot=True, fmt='.1f', cmap='RdBu_r', center=0,
                    mask=mask, ax=ax, cbar_kws={'label': 'Изменение (%)'})

        ax.set_title('Структурные сдвиги в информационном фоне (% изменения)', fontsize=14, fontweight='bold')
        ax.set_xlabel('Переменные', fontsize=12)
        ax.set_ylabel('События', fontsize=12)

        plt.tight_layout()
        plt.savefig(self.output_dir / 'heatmap_structural_shifts.png', dpi=150, bbox_inches='tight')
        plt.close()
        print("   ✅ heatmap_structural_shifts.png сохранен")

        return df_matrix

    def analyze_category_groups(self):
        """Анализирует сдвиги по группам категорий"""
        print("\n" + "=" * 80)
        print("📊 АНАЛИЗ ПО ГРУППАМ КАТЕГОРИЙ")
        print("=" * 80)

        if 'all_events' not in self.results:
            self.analyze_all_events_all_variables()

        all_results = self.results['all_events']

        # Группируем переменные
        groups = {
            'Lenta - Негатив': ['lenta_negative'],
            'Lenta - Позитив': ['lenta_positive'],
            'Lenta - Тематики': ['lenta_war', 'lenta_political', 'lenta_sanctions', 'lenta_oil_gas', 'lenta_market'],
            'SmartLab - Негатив': ['comments_negative'],
            'SmartLab - Позитив': ['comments_positive'],
            'SmartLab - Тематики': ['comments_price', 'comments_dividends', 'comments_reports', 'comments_macro',
                                    'comments_news'],
        }

        for event_name, event_results in all_results.items():
            print(f"\n📍 {event_name}:")

            for group_name, group_vars in groups.items():
                group_vars = [v for v in group_vars if v in self.available_vars]
                if not group_vars:
                    continue

                changes = []
                sig_changes = []

                for var in group_vars:
                    if var in event_results:
                        changes.append(event_results[var]['change_pct'])
                        if event_results[var]['significant']:
                            sig_changes.append(event_results[var]['change_pct'])

                if changes:
                    avg_change = np.mean(changes)
                    print(
                        f"   {group_name:20s}: среднее {avg_change:+.1f}% (значимых: {len(sig_changes)}/{len(changes)})")

    def generate_comprehensive_report(self):
        """Генерирует полный отчет"""
        print("\n" + "=" * 80)
        print("📄 ПОЛНЫЙ ОТЧЕТ: СТРУКТУРНЫЕ СДВИГИ ВО ВСЕХ КОМПОНЕНТАХ")
        print("=" * 80)

        if 'all_events' not in self.results:
            self.analyze_all_events_all_variables()

        all_results = self.results['all_events']

        report = []
        report.append("=" * 80)
        report.append("ПОЛНЫЙ АНАЛИЗ СТРУКТУРНЫХ СДВИГОВ ИНФОРМАЦИОННОГО ФОНА")
        report.append("=" * 80)

        for event_name, event_results in all_results.items():
            report.append(f"\n{'=' * 40}")
            report.append(f"СОБЫТИЕ: {event_name}")
            report.append(f"{'=' * 40}")

            # Топ-10 значимых изменений
            sig_items = [(var, stats) for var, stats in event_results.items() if stats['significant']]
            sig_items.sort(key=lambda x: -abs(x[1]['change_pct']))

            if sig_items:
                report.append("\nТоп-10 значимых изменений:")
                for var, stats in sig_items[:10]:
                    var_name = self.info_variables.get(var, var)
                    report.append(f"   {var_name:30s}: {stats['change_pct']:+.1f}% (p={stats['t_pvalue']:.4f})")

            # Сводка по группам
            report.append("\nСводка по группам:")

            lenta_vars = [v for v in event_results if v.startswith('lenta_')]
            smartlab_vars = [v for v in event_results if v.startswith('comments_')]

            if lenta_vars:
                lenta_changes = [event_results[v]['change_pct'] for v in lenta_vars]
                report.append(f"   Lenta.ru: среднее {np.mean(lenta_changes):+.1f}%")

            if smartlab_vars:
                sl_changes = [event_results[v]['change_pct'] for v in smartlab_vars]
                report.append(f"   SmartLab: среднее {np.mean(sl_changes):+.1f}%")

        # Сохраняем
        report_text = "\n".join(report)
        print(report_text)

        with open(self.output_dir / 'comprehensive_report.txt', 'w', encoding='utf-8') as f:
            f.write(report_text)

        return report_text

    def run_full_analysis(self):
        """Запускает полный расширенный анализ"""
        self.load_data()
        self.analyze_all_events_all_variables()
        self.create_heatmap_data()
        self.analyze_category_groups()
        self.generate_comprehensive_report()

        print("\n" + "=" * 80)
        print("✅ ПОЛНЫЙ АНАЛИЗ ЗАВЕРШЕН!")
        print(f"   Результаты: {self.output_dir}")
        print("=" * 80)


def main():
    analyzer = StructuralBreakAnalyzer()
    analyzer.run_full_analysis()


if __name__ == "__main__":
    main()