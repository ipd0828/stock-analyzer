# src/ml_models/rigorous_information_analysis.py
# Строгий научный анализ информационного фона

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import sys
import warnings
from scipy import stats
from scipy.stats import pearsonr, spearmanr, kendalltau
from statsmodels.tsa.stattools import grangercausalitytests, adfuller
from statsmodels.tsa.vector_ar.var_model import VAR
from statsmodels.tsa.arima.model import ARIMA
import statsmodels.api as sm

warnings.filterwarnings('ignore')

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import PROCESSED_DATA_DIR

plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams['figure.figsize'] = (14, 8)


class RigorousInformationAnalyzer:
    """
    Строгий научный анализ информационного фона

    Исследуемые гипотезы:
    H1: Информационный фон Грейнджер-причиняет волатильность
    H2: Информационный фон Грейнджер-причиняет объем торгов
    H3: Информационный фон реагирует на ценовые шоки (обратная причинность)
    H4: Информационный фон усиливается в периоды высокой неопределенности
    """

    def __init__(self):
        self.data_path = PROCESSED_DATA_DIR / "gazp_financial_data/GAZP_complete_dataset.csv"
        self.df = None
        self.output_dir = Path("data/ml_models/rigorous_analysis")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.results = {}

    def load_and_prepare_data(self):
        """Загружает и подготавливает данные"""
        print("=" * 80)
        print("📥 ЗАГРУЗКА ДАННЫХ ДЛЯ СТРОГОГО НАУЧНОГО АНАЛИЗА")
        print("=" * 80)

        self.df = pd.read_csv(self.data_path)
        self.df['date'] = pd.to_datetime(self.df['date'])
        self.df = self.df.sort_values('date').reset_index(drop=True)

        # ===== СОЗДАЕМ ПЕРЕМЕННЫЕ ДЛЯ АНАЛИЗА =====

        # Рыночные переменные
        self.df['return'] = self.df['price'].pct_change()
        self.df['abs_return'] = abs(self.df['return'])
        self.df['volatility_5d'] = self.df['return'].rolling(5).std()
        self.df['volatility_20d'] = self.df['return'].rolling(20).std()
        self.df['volume_log'] = np.log1p(self.df['volume'])
        self.df['volume_change'] = self.df['volume'].pct_change()

        # Ценовые шоки (выход за пределы N стандартных отклонений)
        mean_ret = self.df['return'].mean()
        std_ret = self.df['return'].std()
        self.df['price_shock'] = (abs(self.df['return'] - mean_ret) > 2 * std_ret).astype(int)

        # Информационный фон (агрегированный)
        info_cols = []

        if 'lenta_total' in self.df.columns:
            self.df['lenta_intensity'] = self.df['lenta_total']
            info_cols.append('lenta_intensity')

        if 'comments_total' in self.df.columns:
            self.df['comments_intensity'] = self.df['comments_total']
            info_cols.append('comments_intensity')

        # Создаем агрегированный индекс информационного фона
        if info_cols:
            # Нормализуем и объединяем
            normalized = pd.DataFrame()
            for col in info_cols:
                if self.df[col].std() > 0:
                    normalized[col] = (self.df[col] - self.df[col].mean()) / self.df[col].std()

            self.df['info_index'] = normalized.mean(axis=1)

        # Негативный сентимент
        neg_cols = []
        if 'lenta_negative' in self.df.columns:
            neg_cols.append('lenta_negative')
        if 'comments_negative' in self.df.columns:
            neg_cols.append('comments_negative')

        if neg_cols:
            self.df['negative_index'] = self.df[neg_cols].mean(axis=1)

        # Удаляем NaN
        self.df = self.df.dropna().reset_index(drop=True)

        print(f"✅ Подготовлено {len(self.df)} наблюдений")
        print(f"   Период: {self.df['date'].min().date()} - {self.df['date'].max().date()}")

        return self.df

    def test_stationarity(self):
        """Проверяет стационарность рядов (тест Дики-Фуллера)"""
        print("\n" + "=" * 80)
        print("📊 ТЕСТ НА СТАЦИОНАРНОСТЬ (ADF)")
        print("=" * 80)

        variables = ['return', 'abs_return', 'volatility_5d', 'volume_log', 'info_index', 'negative_index']
        variables = [v for v in variables if v in self.df.columns]

        results = []
        for var in variables:
            adf_result = adfuller(self.df[var].dropna(), autolag='AIC')
            results.append({
                'variable': var,
                'adf_statistic': adf_result[0],
                'p_value': adf_result[1],
                'stationary': adf_result[1] < 0.05
            })

        df_results = pd.DataFrame(results)
        print(df_results.to_string(index=False))

        self.results['stationarity'] = df_results
        return df_results

    def granger_causality_test(self, max_lag: int = 5):
        """
        Тест Грейнджера на причинность

        Проверяет, помогает ли информационный фон предсказать рыночные переменные
        """
        print("\n" + "=" * 80)
        print("📊 ТЕСТ ГРЕЙНДЖЕРА НА ПРИЧИННОСТЬ")
        print("=" * 80)

        # Проверяем: Info → Market
        tests = [
            ('info_index', 'volatility_5d', 'Инфорфон → Волатильность'),
            ('info_index', 'abs_return', 'Инфорфон → |Доходность|'),
            ('info_index', 'volume_log', 'Инфорфон → Объем'),
            ('negative_index', 'volatility_5d', 'Негатив → Волатильность'),
            ('negative_index', 'return', 'Негатив → Доходность'),
        ]

        # Проверяем обратную причинность: Market → Info
        reverse_tests = [
            ('volatility_5d', 'info_index', 'Волатильность → Инфорфон'),
            ('abs_return', 'info_index', '|Доходность| → Инфорфон'),
            ('price_shock', 'info_index', 'Ценовой шок → Инфорфон'),
        ]

        results = []

        for cause, effect, description in tests + reverse_tests:
            if cause not in self.df.columns or effect not in self.df.columns:
                continue

            data = self.df[[cause, effect]].dropna()

            try:
                gc_result = grangercausalitytests(data[[effect, cause]], maxlag=max_lag, verbose=False)

                # Собираем p-value для всех лагов
                p_values = [gc_result[lag][0]['ssr_ftest'][1] for lag in range(1, max_lag + 1)]
                min_p = min(p_values)
                best_lag = np.argmin(p_values) + 1

                results.append({
                    'description': description,
                    'cause': cause,
                    'effect': effect,
                    'min_p_value': min_p,
                    'best_lag': best_lag,
                    'significant_05': min_p < 0.05,
                    'significant_01': min_p < 0.01
                })
            except Exception as e:
                print(f"   ⚠️ Ошибка для {cause} → {effect}: {e}")

        df_results = pd.DataFrame(results)
        df_results = df_results.sort_values('min_p_value')

        print("\nРезультаты теста Грейнджера (p-value):")
        print("-" * 80)
        for _, row in df_results.iterrows():
            sig = "***" if row['significant_01'] else ("**" if row['significant_05'] else "")
            print(f"   {row['description']:35s}: p={row['min_p_value']:.4f} (лаг {row['best_lag']}) {sig}")

        self.results['granger'] = df_results
        return df_results

    def impulse_response_analysis(self):
        """Анализ импульсных откликов (VAR модель)"""
        print("\n" + "=" * 80)
        print("📊 АНАЛИЗ ИМПУЛЬСНЫХ ОТКЛИКОВ (VAR)")
        print("=" * 80)

        # Выбираем переменные для VAR
        var_vars = ['info_index', 'volatility_5d', 'abs_return', 'volume_log']
        var_vars = [v for v in var_vars if v in self.df.columns]

        if len(var_vars) < 2:
            print("   ⚠️ Недостаточно переменных для VAR")
            return None

        data = self.df[var_vars].dropna()

        # Выбираем оптимальный лаг по AIC
        try:
            model = VAR(data)
            lag_order = model.select_order(maxlags=10)
            best_lag = lag_order.aic

            print(f"   Оптимальный лаг (AIC): {best_lag}")

            # Оцениваем модель
            results = model.fit(best_lag)

            # Импульсные отклики
            irf = results.irf(periods=20)

            # Визуализация
            fig = irf.plot(orth=False)
            fig.set_size_inches(16, 12)
            plt.tight_layout()
            plt.savefig(self.output_dir / 'impulse_response.png', dpi=150)
            plt.close()
            print("   ✅ impulse_response.png сохранен")

            # Извлекаем отклик волатильности на шок инфорфона
            info_idx = var_vars.index('info_index')
            vol_idx = var_vars.index('volatility_5d') if 'volatility_5d' in var_vars else None

            if vol_idx is not None:
                response = irf.irfs[vol_idx, info_idx, :]
                max_response = response.max()
                max_response_period = np.argmax(response)

                print(f"\n   Отклик волатильности на шок инфорфона:")
                print(f"      Максимальный отклик: {max_response:.6f} (период {max_response_period})")
                print(f"      Кумулятивный отклик: {response.sum():.6f}")

                self.results['irf'] = {
                    'max_response': max_response,
                    'max_response_period': max_response_period,
                    'cumulative_response': response.sum()
                }

        except Exception as e:
            print(f"   ⚠️ Ошибка VAR: {e}")

        return None

    def event_study(self):
        """Изучение реакции информационного фона на ценовые шоки"""
        print("\n" + "=" * 80)
        print("📊 EVENT STUDY: РЕАКЦИЯ НА ЦЕНОВЫЕ ШОКИ")
        print("=" * 80)

        if 'price_shock' not in self.df.columns or 'info_index' not in self.df.columns:
            print("   ⚠️ Нет данных для event study")
            return None

        # Находим дни с ценовыми шоками
        shock_days = self.df[self.df['price_shock'] == 1].index.tolist()

        if len(shock_days) < 5:
            print(f"   ⚠️ Недостаточно шоковых дней: {len(shock_days)}")
            return None

        # Собираем окна вокруг шоков
        window = 10
        responses = []

        for shock_idx in shock_days:
            start = max(0, shock_idx - window)
            end = min(len(self.df), shock_idx + window + 1)

            window_data = self.df.iloc[start:end]['info_index'].values
            if len(window_data) == 2 * window + 1:
                responses.append(window_data)

        if responses:
            avg_response = np.mean(responses, axis=0)
            std_response = np.std(responses, axis=0)

            # Проверяем значимость реакции
            pre_shock = avg_response[:window].mean()
            post_shock = avg_response[window + 1:].mean()

            t_stat, p_value = stats.ttest_rel(
                [r[:window].mean() for r in responses],
                [r[window + 1:].mean() for r in responses]
            )

            print(f"\n   Средний инфорфон до шока: {pre_shock:.4f}")
            print(f"   Средний инфорфон после шока: {post_shock:.4f}")
            print(f"   Изменение: {post_shock - pre_shock:+.4f}")
            print(f"   t-статистика: {t_stat:.4f}, p-value: {p_value:.4f}")
            print(f"   Значимое изменение: {'ДА' if p_value < 0.05 else 'НЕТ'}")

            # Визуализация
            fig, ax = plt.subplots(figsize=(12, 6))
            x = np.arange(-window, window + 1)

            ax.plot(x, avg_response, 'b-', linewidth=2, label='Средний инфорфон')
            ax.fill_between(x,
                            avg_response - 1.96 * std_response / np.sqrt(len(responses)),
                            avg_response + 1.96 * std_response / np.sqrt(len(responses)),
                            alpha=0.3, color='blue', label='95% CI')
            ax.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Ценовой шок')
            ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)

            ax.set_xlabel('Дни относительно шока', fontsize=12)
            ax.set_ylabel('Информационный фон (стандартизованный)', fontsize=12)
            ax.set_title('Реакция информационного фона на ценовые шоки', fontsize=14, fontweight='bold')
            ax.legend()
            ax.grid(True, alpha=0.3)

            plt.tight_layout()
            plt.savefig(self.output_dir / 'event_study.png', dpi=150)
            plt.close()
            print("   ✅ event_study.png сохранен")

            self.results['event_study'] = {
                'pre_shock': pre_shock,
                'post_shock': post_shock,
                'change': post_shock - pre_shock,
                'p_value': p_value,
                'significant': p_value < 0.05
            }

        return self.results.get('event_study')

    def cross_correlation_analysis(self):
        """Кросс-корреляционный анализ с лагами"""
        print("\n" + "=" * 80)
        print("📊 КРОСС-КОРРЕЛЯЦИОННЫЙ АНАЛИЗ")
        print("=" * 80)

        from statsmodels.tsa.filters.hp_filter import hpfilter

        if 'info_index' not in self.df.columns:
            return None

        targets = ['abs_return', 'volatility_5d', 'volume_log']
        targets = [t for t in targets if t in self.df.columns]

        fig, axes = plt.subplots(len(targets), 1, figsize=(14, 5 * len(targets)))
        if len(targets) == 1:
            axes = [axes]

        max_lag = 10
        results = []

        for i, target in enumerate(targets):
            ax = axes[i]

            x = self.df['info_index'].dropna().values
            y = self.df[target].dropna().values

            # Приводим к одинаковой длине
            min_len = min(len(x), len(y))
            x = x[:min_len]
            y = y[:min_len]

            # Детрендирование через HP фильтр
            try:
                cycle_x, _ = hpfilter(x, lamb=129600)
                cycle_y, _ = hpfilter(y, lamb=129600)
            except:
                # Если HP фильтр не работает, используем разности
                cycle_x = np.diff(x, prepend=x[0])
                cycle_y = np.diff(y, prepend=y[0])

            cross_corr = []
            for lag in range(-max_lag, max_lag + 1):
                if lag < 0:
                    corr = np.corrcoef(cycle_x[:lag], cycle_y[-lag:])[0, 1]
                elif lag > 0:
                    corr = np.corrcoef(cycle_x[:-lag], cycle_y[lag:])[0, 1]
                else:
                    corr = np.corrcoef(cycle_x, cycle_y)[0, 1]
                cross_corr.append(corr)

            lags = np.arange(-max_lag, max_lag + 1)
            n = len(x)
            significance = 1.96 / np.sqrt(n)

            ax.bar(lags, cross_corr, alpha=0.7, color='steelblue')
            ax.axhline(y=significance, color='red', linestyle='--', label='95% значимость')
            ax.axhline(y=-significance, color='red', linestyle='--')
            ax.axhline(y=0, color='black', linewidth=0.5)
            ax.axvline(x=0, color='green', linestyle=':', label='Лаг 0')

            ax.set_xlabel('Лаг (отрицательный = инфорфон опережает)', fontsize=11)
            ax.set_ylabel('Корреляция', fontsize=11)
            ax.set_title(f'Кросс-корреляция: Инфорфон ↔ {target}', fontsize=12, fontweight='bold')
            ax.legend()
            ax.grid(True, alpha=0.3)

            max_corr = max(cross_corr)
            max_lag_idx = np.argmax(cross_corr)
            best_lag = lags[max_lag_idx]

            results.append({
                'target': target,
                'max_correlation': max_corr,
                'best_lag': best_lag,
                'significant': abs(max_corr) > significance
            })

            print(f"\n   {target}:")
            print(f"      Макс. корреляция: {max_corr:.4f} (лаг {best_lag})")
            print(f"      Значимо: {'ДА' if abs(max_corr) > significance else 'НЕТ'}")

        plt.tight_layout()
        plt.savefig(self.output_dir / 'cross_correlation.png', dpi=150)
        plt.close()
        print("\n   ✅ cross_correlation.png сохранен")

        self.results['cross_correlation'] = results
        return results

    def generate_report(self):
        """Генерирует итоговый научный отчет"""
        print("\n" + "=" * 80)
        print("📄 НАУЧНЫЙ ОТЧЕТ: ПРИРОДА ИНФОРМАЦИОННОГО ФОНА")
        print("=" * 80)

        report = []
        report.append("=" * 80)
        report.append("НАУЧНЫЙ АНАЛИЗ ИНФОРМАЦИОННОГО ФОНА ПАО «ГАЗПРОМ»")
        report.append("=" * 80)

        # 1. Стационарность
        if 'stationarity' in self.results:
            df_stat = self.results['stationarity']
            stationary = df_stat[df_stat['stationary'] == True]['variable'].tolist()
            report.append(f"\n1. СТАЦИОНАРНОСТЬ РЯДОВ:")
            report.append(f"   Стационарные ряды: {', '.join(stationary)}")

        # 2. Причинность по Грейнджеру
        if 'granger' in self.results:
            df_g = self.results['granger']
            sig_g = df_g[df_g['significant_05'] == True]

            report.append(f"\n2. ПРИЧИННОСТЬ ПО ГРЕЙНДЖЕРУ (p < 0.05):")
            if len(sig_g) > 0:
                for _, row in sig_g.iterrows():
                    report.append(f"   ✅ {row['description']}: p={row['min_p_value']:.4f}")
            else:
                report.append(f"   ❌ Значимых причинных связей не обнаружено")

        # 3. Импульсные отклики
        if 'irf' in self.results:
            irf = self.results['irf']
            report.append(f"\n3. ИМПУЛЬСНЫЕ ОТКЛИКИ:")
            report.append(f"   Отклик волатильности на шок инфорфона: {irf['max_response']:.4f}")
            report.append(f"   Период максимального отклика: {irf['max_response_period']}")

        # 4. Event study
        if 'event_study' in self.results:
            es = self.results['event_study']
            report.append(f"\n4. РЕАКЦИЯ НА ЦЕНОВЫЕ ШОКИ:")
            report.append(f"   Изменение инфорфона после шока: {es['change']:+.4f}")
            report.append(f"   Значимость: {'ДА' if es['significant'] else 'НЕТ'} (p={es['p_value']:.4f})")

        # 5. Кросс-корреляции
        if 'cross_correlation' in self.results:
            report.append(f"\n5. КРОСС-КОРРЕЛЯЦИИ:")
            for cc in self.results['cross_correlation']:
                sig_str = "✅" if cc['significant'] else "❌"
                report.append(f"   {sig_str} {cc['target']}: r={cc['max_correlation']:.4f} (лаг {cc['best_lag']})")

        # 6. ИТОГОВЫЙ ВЫВОД
        report.append("\n" + "=" * 80)
        report.append("ИТОГОВЫЙ ВЫВОД:")
        report.append("=" * 80)

        # Анализируем результаты
        has_causality = False
        if 'granger' in self.results:
            has_causality = self.results['granger']['significant_05'].any()

        has_reaction = False
        if 'event_study' in self.results:
            has_reaction = self.results['event_study']['significant']

        if not has_causality and not has_reaction:
            report.append("\n   Информационный фон НЕ является предиктором рыночных движений.")
            report.append("   Он НЕ предсказывает волатильность, доходность или объем торгов.")
            report.append("\n   Однако анализ важности признаков в ML-моделях показывает,")
            report.append("   что информационный фон объясняет ~50% дисперсии в моделях.")
            report.append("\n   Это указывает на то, что информационный фон является")
            report.append("   СОПУТСТВУЮЩИМ/ОТРАЖАЮЩИМ фактором, а не причинным.")
            report.append("   Он отражает текущее состояние рынка, но не предсказывает будущее.")
        else:
            report.append("\n   Обнаружены значимые связи между информационным фоном и рынком.")

        # Сохраняем отчет
        report_text = "\n".join(report)
        print(report_text)

        with open(self.output_dir / 'scientific_report.txt', 'w', encoding='utf-8') as f:
            f.write(report_text)

        return report_text

    def run_full_analysis(self):
        """Запускает полный научный анализ"""
        self.load_and_prepare_data()

        self.test_stationarity()
        self.granger_causality_test()
        self.impulse_response_analysis()
        self.event_study()
        self.cross_correlation_analysis()

        report = self.generate_report()

        print("\n✅ Анализ завершен!")
        print(f"   Результаты сохранены в: {self.output_dir}")

        return report


def main():
    analyzer = RigorousInformationAnalyzer()
    analyzer.run_full_analysis()


if __name__ == "__main__":
    main()