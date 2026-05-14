# scripts/full_analysis.py
"""
Анализ датасета акций Газпрома (2020-2026).

Строит:
1. Боксплот цен по годам с аннотациями ключевых событий.
2. Корреляционные матрицы: Pearson (числовые признаки), Spearman (все признаки),
   Kendall (категориальные признаки Lenta и комментариев).
3. Гистограммы распределений: цена, объём, комментарии, заголовки Lenta.
4. Временные ряды: цена + сентимент комментариев (стек) + объём;
   цена + категории комментариев (стек) + цена газа.
5. Стек категорий заголовков Lenta с наложением цены.
6. Анализ зависимости цены от газа Henry Hub: scatter plot, совмещённая динамика,
   лаговая корреляция (0-30 дней), корреляция по годам.
7. Анализ зависимости цены от нефти Brent: scatter plot, совмещённая динамика,
   лаговая корреляция (0-30 дней), корреляция по годам.
8. Анализ зависимости цены от курса USD: scatter plot, совмещённая динамика,
   лаговая корреляция (0-30 дней), корреляция по годам.
9. Анализ зависимости цены от ключевой ставки ЦБ: scatter plot, совмещённая динамика,
   корреляция по годам.
10. Фундаментальный анализ: цена vs BVPS, дисконт к BVPS, цена vs Graham Number, динамика P/E.
11. Динамика корреляции по годам для категорий Lenta, категорий комментариев и макропоказателей.

Генерирует текстовый отчёт, содержащий:
- Общую статистику (торговые дни, средняя/медианная/мин/макс цена).
- Статистику по комментариям и заголовкам Lenta.
- Корреляции всех признаков с ценой (Spearman).
- Описание наблюдаемых закономерностей для каждого блока графиков.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import sys
from datetime import datetime
import warnings
from scipy import stats

warnings.filterwarnings('ignore')

sys.path.append(str(Path(__file__).parent.parent))
from config.paths import PROCESSED_DATA_DIR

# Настройки графиков
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")
plt.rcParams['figure.figsize'] = (16, 8)
plt.rcParams['font.size'] = 10
plt.rcParams['axes.titlesize'] = 12
plt.rcParams['axes.labelsize'] = 11
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False

OUTPUT_DIR = Path("data/plots/full_analysis")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class FullAnalyzer:
    """Полный анализ датасета Газпрома"""

    def __init__(self):
        self.df = None
        self.key_dates = {
            '2020-03-11': 'COVID-19',
            '2022-02-24': 'Начало СВО',
            '2022-09-26': 'Взрыв Северных потоков',
            '2023-07-01': 'Отказ от дивидендов',
        }
        self.observations = {}

    def load_data(self):
        """Загрузка данных"""
        dataset_path = PROCESSED_DATA_DIR / "gazp_financial_data/GAZP_complete_dataset.csv"
        if not dataset_path.exists():
            print(f"Файл не найден: {dataset_path}")
            return False

        self.df = pd.read_csv(dataset_path)
        self.df['date'] = pd.to_datetime(self.df['date'])
        self.df = self.df.sort_values('date')
        self.df['year'] = self.df['date'].dt.year
        self.df['month'] = self.df['date'].dt.month

        # Производные признаки
        self.df['price_range'] = self.df['high'] - self.df['low']
        self.df['price_range_pct'] = (self.df['high'] - self.df['low']) / self.df['low'] * 100
        self.df['volume_ma7'] = self.df['volume'].rolling(7).mean()
        self.df['price_ma30'] = self.df['price'].rolling(30).mean()
        self.df['volatility_30'] = self.df['price'].rolling(30).std()
        self.df['sentiment_ratio'] = (self.df['comments_positive'] + 1) / (self.df['comments_negative'] + 1)

        print(f"Загружено записей: {len(self.df)}")
        print(f"Период: {self.df['date'].min().date()} - {self.df['date'].max().date()}")
        print(f"Признаков: {len(self.df.columns)}")
        return True

    def plot_01_price_boxplot_by_year(self):
        """1. Боксплот цен по годам с аннотациями событий"""
        fig, ax = plt.subplots(figsize=(14, 6))

        years = sorted(self.df['year'].unique())
        data_by_year = [self.df[self.df['year'] == y]['price'].values for y in years]

        bp = ax.boxplot(data_by_year, labels=years, patch_artist=True,
                        medianprops={'linewidth': 2, 'color': 'red'},
                        boxprops={'facecolor': 'lightblue', 'alpha': 0.7})

        colors = ['lightblue', 'lightgreen', 'lightcoral', 'lightyellow', 'lightcyan', 'lightpink']
        for i, box in enumerate(bp['boxes']):
            box.set_facecolor(colors[i % len(colors)])

        ax.set_xlabel('Год')
        ax.set_ylabel('Цена, руб')
        ax.set_title('Распределение цен акций Газпрома по годам')
        ax.grid(True, alpha=0.3, axis='y')

        max_price = self.df['price'].max()
        events_pos = {
            'COVID-19': (2020, self.df[self.df['year'] == 2020]['price'].max()),
            'Начало СВО': (2022, self.df[self.df['year'] == 2022]['price'].max()),
            'Взрыв СП': (2022.75, 180),
            'Отказ от дивидендов': (2023.5, self.df[self.df['year'] == 2023]['price'].max()),
        }

        for event, (x, y) in events_pos.items():
            ax.annotate(event, xy=(x, y), xytext=(x, max_price * 0.85),
                        arrowprops=dict(arrowstyle='->', color='red'),
                        fontsize=9, ha='center')

        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '01_price_boxplot_by_year.png', dpi=150)
        plt.close()

        stats_by_year = self.df.groupby('year')['price'].agg(['mean', 'median', 'std', 'min', 'max'])
        self.observations['01_price_boxplot'] = f"""
        Распределение цен по годам:
        - 2020: средняя {stats_by_year.loc[2020, 'mean']:.1f} руб, разброс {stats_by_year.loc[2020, 'std']:.1f} руб
        - 2021: средняя {stats_by_year.loc[2021, 'mean']:.1f} руб, разброс {stats_by_year.loc[2021, 'std']:.1f} руб
        - 2022: средняя {stats_by_year.loc[2022, 'mean']:.1f} руб, разброс {stats_by_year.loc[2022, 'std']:.1f} руб
        - 2023: средняя {stats_by_year.loc[2023, 'mean']:.1f} руб, разброс {stats_by_year.loc[2023, 'std']:.1f} руб
        - 2024: средняя {stats_by_year.loc[2024, 'mean']:.1f} руб, разброс {stats_by_year.loc[2024, 'std']:.1f} руб
        """
        print("  01_price_boxplot_by_year.png")

    def plot_02a_pearson_correlation(self):
        """2a. Pearson корреляция числовых признаков"""
        numeric_cols = ['price', 'volume', 'oil_brent', 'gas_henry_hub', 'cbr_key_rate', 'usd_rate',
                        'IMOEX', 'RTSI', 'MOEXOG', 'MOEXFN', 'MOEXMM', 'MOEXCN',
                        'comments_total', 'comments_positive', 'comments_negative', 'comments_neutral',
                        'comments_price', 'comments_dividends', 'comments_reports', 'comments_macro', 'comments_news',
                        'lenta_total', 'lenta_positive', 'lenta_negative', 'lenta_neutral',
                        'price_range', 'price_range_pct', 'volatility_30', 'sentiment_ratio']

        existing = [c for c in numeric_cols if c in self.df.columns]
        corr_matrix = self.df[existing].corr(method='pearson')

        plt.figure(figsize=(20, 18))
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
        sns.heatmap(corr_matrix, mask=mask, annot=True, fmt='.2f', cmap='RdBu_r',
                    center=0, square=True, linewidths=0.5, annot_kws={'size': 7})
        plt.title('Pearson корреляция числовых признаков')
        plt.xticks(rotation=45, ha='right')
        plt.yticks(rotation=0)
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '02a_pearson_correlation.png', dpi=150)
        plt.close()

        price_corr = corr_matrix['price'].drop('price').sort_values(ascending=False)
        self.observations['02a_pearson'] = f"""
        Топ-5 положительных корреляций с ценой (Pearson):
        {price_corr.head(5).to_string()}
        Топ-5 отрицательных корреляций с ценой (Pearson):
        {price_corr.tail(5).to_string()}
        """
        print("  02a_pearson_correlation.png")

    def plot_02b_spearman_correlation(self):
        """2b. Spearman корреляция всех признаков"""
        numeric_cols = ['price', 'volume', 'oil_brent', 'gas_henry_hub', 'cbr_key_rate', 'usd_rate',
                        'IMOEX', 'RTSI', 'MOEXOG', 'MOEXFN', 'MOEXMM', 'MOEXCN',
                        'comments_total', 'comments_positive', 'comments_negative', 'comments_neutral',
                        'comments_price', 'comments_dividends', 'comments_reports', 'comments_macro', 'comments_news',
                        'lenta_total', 'lenta_positive', 'lenta_negative', 'lenta_neutral',
                        'lenta_war', 'lenta_sanctions', 'lenta_oil_gas', 'lenta_market', 'lenta_political',
                        'bvps_rub', 'eps_rub', 'pb_ratio', 'pe_ratio', 'graham_number_rub']

        existing = [c for c in numeric_cols if c in self.df.columns]
        corr_matrix = self.df[existing].corr(method='spearman')

        plt.figure(figsize=(20, 18))
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
        sns.heatmap(corr_matrix, mask=mask, annot=True, fmt='.2f', cmap='RdBu_r',
                    center=0, square=True, linewidths=0.5, annot_kws={'size': 7})
        plt.title('Spearman корреляция всех признаков')
        plt.xticks(rotation=45, ha='right')
        plt.yticks(rotation=0)
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '02b_spearman_correlation.png', dpi=150)
        plt.close()

        price_corr = corr_matrix['price'].drop('price').sort_values(ascending=False)
        self.observations['02b_spearman'] = f"""
        Топ-5 положительных корреляций с ценой (Spearman):
        {price_corr.head(5).to_string()}
        Топ-5 отрицательных корреляций с ценой (Spearman):
        {price_corr.tail(5).to_string()}
        """
        print("  02b_spearman_correlation.png")

    def plot_02c_kendall_lenta(self):
        """2c. Kendall корреляция категорий Lenta"""
        lenta_cats = ['lenta_war', 'lenta_sanctions', 'lenta_oil_gas', 'lenta_market', 'lenta_political']
        existing = [c for c in lenta_cats if c in self.df.columns]

        if not existing:
            return

        lenta_df = self.df[existing + ['price']].copy()
        for col in existing:
            if self.df[col].max() > 0:
                lenta_df[f'{col}_cat'] = pd.qcut(self.df[col], q=4, labels=False, duplicates='drop')
                lenta_df[f'{col}_cat'] = lenta_df[f'{col}_cat'].fillna(0).astype(int)
            else:
                lenta_df[f'{col}_cat'] = 0

        cat_cols = [f'{c}_cat' for c in existing]
        corr_matrix = lenta_df[cat_cols + ['price']].corr(method='kendall')
        rename_map = {f'{c}_cat': c for c in existing}
        corr_matrix = corr_matrix.rename(index=rename_map, columns=rename_map)

        plt.figure(figsize=(10, 8))
        sns.heatmap(corr_matrix, annot=True, fmt='.2f', cmap='RdBu_r',
                    center=0, square=True, linewidths=0.5)
        plt.title('Kendall корреляция категорий Lenta')
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '02c_kendall_lenta.png', dpi=150)
        plt.close()
        print("  02c_kendall_lenta.png")

    def plot_02d_kendall_comments(self):
        """2d. Kendall корреляция категорий комментариев"""
        comment_cats = ['comments_price', 'comments_dividends', 'comments_reports', 'comments_macro', 'comments_news']
        existing = [c for c in comment_cats if c in self.df.columns]

        if not existing:
            return

        comm_df = self.df[existing + ['price']].copy()
        for col in existing:
            if self.df[col].max() > 0:
                comm_df[f'{col}_cat'] = pd.qcut(self.df[col], q=4, labels=False, duplicates='drop')
                comm_df[f'{col}_cat'] = comm_df[f'{col}_cat'].fillna(0).astype(int)
            else:
                comm_df[f'{col}_cat'] = 0

        cat_cols = [f'{c}_cat' for c in existing]
        corr_matrix = comm_df[cat_cols + ['price']].corr(method='kendall')
        rename_map = {f'{c}_cat': c for c in existing}
        corr_matrix = corr_matrix.rename(index=rename_map, columns=rename_map)

        plt.figure(figsize=(10, 8))
        sns.heatmap(corr_matrix, annot=True, fmt='.2f', cmap='RdBu_r',
                    center=0, square=True, linewidths=0.5)
        plt.title('Kendall корреляция категорий комментариев')
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '02d_kendall_comments.png', dpi=150)
        plt.close()
        print("  02d_kendall_comments.png")

    def plot_02e_top_correlations(self):
        """2e. Топ корреляций с ценой (барчарт)"""
        numeric_cols = ['volume', 'oil_brent', 'gas_henry_hub', 'cbr_key_rate', 'usd_rate',
                        'IMOEX', 'RTSI', 'MOEXOG',
                        'comments_total', 'comments_positive', 'comments_negative',
                        'lenta_total', 'lenta_war', 'lenta_sanctions',
                        'price_range', 'volatility_30', 'sentiment_ratio']

        existing = [c for c in numeric_cols if c in self.df.columns]
        price_corr = {}
        for col in existing:
            price_corr[col] = self.df[col].corr(self.df['price'], method='spearman')

        price_corr = pd.Series(price_corr).sort_values()

        fig, ax = plt.subplots(figsize=(12, 8))
        colors = ['green' if x > 0 else 'red' for x in price_corr.values]
        ax.barh(price_corr.index, price_corr.values, color=colors, alpha=0.7)
        ax.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
        ax.set_xlabel('Spearman корреляция с ценой')
        ax.set_title('Корреляция признаков с ценой акций')

        for i, (idx, val) in enumerate(price_corr.items()):
            ax.text(val + 0.01 if val > 0 else val - 0.08, i, f'{val:.2f}', va='center', fontsize=9)

        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '02e_top_correlations.png', dpi=150)
        plt.close()
        print("  02e_top_correlations.png")

    def plot_03_distributions(self):
        """3. Гистограммы распределений"""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        axes[0, 0].hist(self.df['price'], bins=50, color='steelblue', edgecolor='black', alpha=0.7)
        axes[0, 0].axvline(self.df['price'].mean(), color='red', linestyle='--', label=f'Средняя: {self.df["price"].mean():.1f}')
        axes[0, 0].axvline(self.df['price'].median(), color='green', linestyle='--', label=f'Медиана: {self.df["price"].median():.1f}')
        axes[0, 0].set_xlabel('Цена, руб')
        axes[0, 0].set_ylabel('Частота')
        axes[0, 0].set_title('Распределение цены')
        axes[0, 0].legend()

        axes[0, 1].hist(np.log1p(self.df['volume']), bins=50, color='coral', edgecolor='black', alpha=0.7)
        axes[0, 1].set_xlabel('log(Объём + 1)')
        axes[0, 1].set_ylabel('Частота')
        axes[0, 1].set_title('Распределение объёма торгов (лог шкала)')

        axes[1, 0].hist(self.df['comments_total'], bins=50, color='green', edgecolor='black', alpha=0.7)
        axes[1, 0].axvline(self.df['comments_total'].mean(), color='red', linestyle='--', label=f'Среднее: {self.df["comments_total"].mean():.1f}')
        axes[1, 0].set_xlabel('Количество комментариев')
        axes[1, 0].set_ylabel('Частота')
        axes[1, 0].set_title('Распределение комментариев')
        axes[1, 0].legend()

        axes[1, 1].hist(self.df['lenta_total'], bins=50, color='purple', edgecolor='black', alpha=0.7)
        axes[1, 1].set_xlabel('Количество заголовков')
        axes[1, 1].set_ylabel('Частота')
        axes[1, 1].set_title('Распределение заголовков Lenta')

        plt.suptitle('Распределения основных показателей')
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '03_distributions.png', dpi=150)
        plt.close()

        skew_price = stats.skew(self.df['price'].dropna())
        kurt_price = stats.kurtosis(self.df['price'].dropna())
        self.observations['03_distributions'] = f"""
        Распределение цены: асимметрия {skew_price:.2f}, эксцесс {kurt_price:.2f}
        Среднее комментариев в день: {self.df['comments_total'].mean():.1f}
        Среднее заголовков Lenta в день: {self.df['lenta_total'].mean():.1f}
        """
        print("  03_distributions.png")

    def plot_04a_price_sentiment_volume(self):
        """4a. Динамика: цена + сентимент комментариев (стек) + объём"""
        fig, ax = plt.subplots(figsize=(16, 8))

        ax.fill_between(self.df['date'], 0, self.df['comments_positive'],
                        alpha=0.5, color='green', label='Позитивные')
        ax.fill_between(self.df['date'], self.df['comments_positive'],
                        self.df['comments_positive'] + self.df['comments_negative'],
                        alpha=0.5, color='red', label='Негативные')
        ax.fill_between(self.df['date'],
                        self.df['comments_positive'] + self.df['comments_negative'],
                        self.df['comments_positive'] + self.df['comments_negative'] + self.df['comments_neutral'],
                        alpha=0.5, color='gray', label='Нейтральные')

        ax2 = ax.twinx()
        ax2.plot(self.df['date'], self.df['price'], 'k-', linewidth=1.5, alpha=0.7, label='Цена')
        ax2.set_ylabel('Цена, руб', color='black')

        vol_norm = (self.df['volume'] - self.df['volume'].min()) / (self.df['volume'].max() - self.df['volume'].min()) * 100
        ax3 = ax.twinx()
        ax3.spines['right'].set_position(('outward', 70))
        ax3.plot(self.df['date'], vol_norm, 'purple', linewidth=1, alpha=0.4, label='Объём (норм.)')
        ax3.set_ylabel('Объём (нормированный)', color='purple')

        ax.set_xlabel('Дата')
        ax.set_ylabel('Количество комментариев')
        ax.set_title('Динамика цены, сентимента комментариев и объёма торгов')

        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        lines3, labels3 = ax3.get_legend_handles_labels()
        ax.legend(lines1 + lines2 + lines3, labels1 + labels2 + labels3, loc='upper left')

        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '04a_price_sentiment_volume.png', dpi=150)
        plt.close()

        self.observations['04a_events'] = []
        for date_str, event in self.key_dates.items():
            date_dt = pd.to_datetime(date_str)
            if date_dt >= self.df['date'].min() and date_dt <= self.df['date'].max():
                idx = (self.df['date'] - date_dt).abs().idxmin()
                self.observations['04a_events'].append(f"{event}: {date_str}, цена {self.df.loc[idx, 'price']:.1f} руб")

        print("  04a_price_sentiment_volume.png")

    def plot_04b_price_comments_categories_gas(self):
        """4b. Динамика: цена + категории комментариев (стек) + газ"""
        fig, ax = plt.subplots(figsize=(16, 8))

        comment_cats = ['comments_price', 'comments_dividends', 'comments_reports', 'comments_macro', 'comments_news']
        comment_names = ['Цена', 'Дивиденды', 'Отчёты', 'Макро', 'Новости']
        comment_colors = ['#2E86AB', '#A23B72', '#F18F01', '#1B998B', '#C73E1D']

        bottom = np.zeros(len(self.df))
        for cat, name, color in zip(comment_cats, comment_names, comment_colors):
            if cat in self.df.columns:
                ax.fill_between(self.df['date'], bottom, bottom + self.df[cat],
                                alpha=0.6, label=name, color=color)
                bottom += self.df[cat]

        ax2 = ax.twinx()
        ax2.plot(self.df['date'], self.df['price'], 'k-', linewidth=1.5, alpha=0.7, label='Цена')
        ax2.set_ylabel('Цена, руб', color='black')

        ax3 = ax.twinx()
        ax3.spines['right'].set_position(('outward', 70))
        ax3.plot(self.df['date'], self.df['gas_henry_hub'], 'r-', linewidth=1.5, alpha=0.5, label='Газ Henry Hub')
        ax3.set_ylabel('Газ Henry Hub, $/MMBtu', color='red')

        ax.set_xlabel('Дата')
        ax.set_ylabel('Количество комментариев')
        ax.set_title('Динамика цены, категорий комментариев и цены газа')

        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        lines3, labels3 = ax3.get_legend_handles_labels()
        ax.legend(lines1 + lines2 + lines3, labels1 + labels2 + labels3, loc='upper left')

        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '04b_price_comments_categories_gas.png', dpi=150)
        plt.close()
        print("  04b_price_comments_categories_gas.png")

    def plot_05_lenta_categories_stack(self):
        """5. Стек категорий Lenta + цена"""
        fig, ax = plt.subplots(figsize=(16, 8))

        lenta_cats = ['lenta_war', 'lenta_sanctions', 'lenta_oil_gas', 'lenta_market', 'lenta_political']
        lenta_names = ['Война', 'Санкции', 'Нефть/Газ', 'Рынок', 'Политика']
        lenta_colors = ['darkred', 'orange', 'gold', 'steelblue', 'purple']

        bottom = np.zeros(len(self.df))
        for cat, name, color in zip(lenta_cats, lenta_names, lenta_colors):
            if cat in self.df.columns:
                ax.fill_between(self.df['date'], bottom, bottom + self.df[cat],
                                alpha=0.6, label=name, color=color)
                bottom += self.df[cat]

        ax2 = ax.twinx()
        ax2.plot(self.df['date'], self.df['price'], 'k-', linewidth=1.5, alpha=0.7, label='Цена')
        ax2.set_ylabel('Цена, руб', color='black')

        ax.set_xlabel('Дата')
        ax.set_ylabel('Количество заголовков')
        ax.set_title('Категории заголовков Lenta и цена акций')

        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '05_lenta_categories_stack.png', dpi=150)
        plt.close()

        stats = {}
        for cat in lenta_cats:
            if cat in self.df.columns:
                stats[cat] = self.df[cat].sum()
        self.observations['05_lenta'] = f"""
        Всего заголовков Lenta: {self.df['lenta_total'].sum():,.0f}
        По категориям:
        - Война: {stats.get('lenta_war', 0):,.0f}
        - Санкции: {stats.get('lenta_sanctions', 0):,.0f}
        - Нефть/Газ: {stats.get('lenta_oil_gas', 0):,.0f}
        - Рынок: {stats.get('lenta_market', 0):,.0f}
        - Политика: {stats.get('lenta_political', 0):,.0f}
        """
        print("  05_lenta_categories_stack.png")

    def plot_06_gas_analysis(self):
        """6. Анализ зависимости от газа Henry Hub"""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))

        axes[0, 0].scatter(self.df['gas_henry_hub'], self.df['price'], alpha=0.3, s=15, c='blue')
        z = np.polyfit(self.df['gas_henry_hub'].dropna(), self.df.loc[self.df['gas_henry_hub'].notna(), 'price'], 1)
        p = np.poly1d(z)
        x_sorted = np.sort(self.df['gas_henry_hub'].dropna())
        axes[0, 0].plot(x_sorted, p(x_sorted), 'r-', linewidth=2,
                        label=f"Spearman r = {self.df['gas_henry_hub'].corr(self.df['price'], method='spearman'):.3f}")
        axes[0, 0].set_xlabel('Газ Henry Hub, $/MMBtu')
        axes[0, 0].set_ylabel('Цена акции, руб')
        axes[0, 0].set_title('Зависимость цены акций от цены газа')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)

        ax1 = axes[0, 1]
        ax1.plot(self.df['date'], self.df['price'], 'b-', linewidth=1.5, label='Цена акции')
        ax1.set_xlabel('Дата')
        ax1.set_ylabel('Цена акции, руб', color='b')
        ax1.tick_params(axis='y', labelcolor='b')

        ax2 = ax1.twinx()
        ax2.plot(self.df['date'], self.df['gas_henry_hub'], 'r-', linewidth=1.5, alpha=0.7, label='Газ')
        ax2.set_ylabel('Газ Henry Hub, $/MMBtu', color='r')
        ax2.tick_params(axis='y', labelcolor='r')

        ax1.set_title('Динамика цены акций и цены газа')
        ax1.grid(True, alpha=0.3)
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

        lags = range(0, 31)
        correlations = []
        for lag in lags:
            if lag == 0:
                corr = self.df['gas_henry_hub'].corr(self.df['price'], method='spearman')
            else:
                gas_shifted = self.df['gas_henry_hub'].shift(lag)
                corr = gas_shifted.corr(self.df['price'], method='spearman')
            correlations.append(corr)

        axes[1, 0].plot(lags, correlations, 'o-', color='purple', linewidth=2, markersize=6)
        axes[1, 0].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        axes[1, 0].set_xlabel('Лаг, дни')
        axes[1, 0].set_ylabel('Spearman корреляция')
        axes[1, 0].set_title('Лаговая корреляция: влияние газа на цену акции')
        axes[1, 0].grid(True, alpha=0.3)

        max_corr_idx = np.argmax(np.abs(correlations))
        max_corr = correlations[max_corr_idx]
        axes[1, 0].annotate(f'Максимум: лаг {max_corr_idx}, r = {max_corr:.3f}',
                            xy=(max_corr_idx, max_corr), xytext=(max_corr_idx + 5, max_corr - 0.1),
                            arrowprops=dict(arrowstyle='->'), fontsize=9)

        years = sorted(self.df['year'].unique())
        yearly_corr = []
        for year in years:
            year_df = self.df[self.df['year'] == year]
            if len(year_df) > 50:
                corr = year_df['gas_henry_hub'].corr(year_df['price'], method='spearman')
                yearly_corr.append(corr)
            else:
                yearly_corr.append(0)

        colors_corr = ['green' if c > 0 else 'red' for c in yearly_corr]
        axes[1, 1].bar(years, yearly_corr, color=colors_corr, alpha=0.7)
        axes[1, 1].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        axes[1, 1].set_xlabel('Год')
        axes[1, 1].set_ylabel('Spearman корреляция')
        axes[1, 1].set_title('Корреляция цена акции vs цена газа по годам')
        axes[1, 1].grid(True, alpha=0.3, axis='y')

        for i, (year, corr) in enumerate(zip(years, yearly_corr)):
            axes[1, 1].text(year, corr + 0.02 if corr > 0 else corr - 0.08, f'{corr:.3f}', ha='center', fontsize=9)

        plt.suptitle('Анализ зависимости цены акций Газпрома от цены газа')
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '06_gas_analysis.png', dpi=150)
        plt.close()

        self.observations['06_gas'] = f"""
        Корреляция с газом (Spearman): текущая {correlations[0]:.3f}
        Максимальная корреляция: {max_corr:.3f} при лаге {max_corr_idx} дней
        Корреляция по годам: {dict(zip(years, yearly_corr))}
        """
        print("  06_gas_analysis.png")

    def plot_07_oil_analysis(self):
        """7. Анализ зависимости от нефти Brent"""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))

        axes[0, 0].scatter(self.df['oil_brent'], self.df['price'], alpha=0.3, s=15, c='blue')
        z = np.polyfit(self.df['oil_brent'].dropna(), self.df.loc[self.df['oil_brent'].notna(), 'price'], 1)
        p = np.poly1d(z)
        x_sorted = np.sort(self.df['oil_brent'].dropna())
        axes[0, 0].plot(x_sorted, p(x_sorted), 'r-', linewidth=2,
                        label=f"Spearman r = {self.df['oil_brent'].corr(self.df['price'], method='spearman'):.3f}")
        axes[0, 0].set_xlabel('Нефть Brent, $/барр')
        axes[0, 0].set_ylabel('Цена акции, руб')
        axes[0, 0].set_title('Зависимость цены акций от нефти Brent')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)

        ax1 = axes[0, 1]
        ax1.plot(self.df['date'], self.df['price'], 'b-', linewidth=1.5, label='Цена акции')
        ax1.set_xlabel('Дата')
        ax1.set_ylabel('Цена акции, руб', color='b')
        ax1.tick_params(axis='y', labelcolor='b')

        ax2 = ax1.twinx()
        ax2.plot(self.df['date'], self.df['oil_brent'], 'g-', linewidth=1.5, alpha=0.7, label='Нефть Brent')
        ax2.set_ylabel('Нефть Brent, $/барр', color='g')
        ax2.tick_params(axis='y', labelcolor='g')

        ax1.set_title('Динамика цены акций и нефти Brent')
        ax1.grid(True, alpha=0.3)
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

        lags = range(0, 31)
        correlations = []
        for lag in lags:
            if lag == 0:
                corr = self.df['oil_brent'].corr(self.df['price'], method='spearman')
            else:
                oil_shifted = self.df['oil_brent'].shift(lag)
                corr = oil_shifted.corr(self.df['price'], method='spearman')
            correlations.append(corr)

        axes[1, 0].plot(lags, correlations, 'o-', color='purple', linewidth=2, markersize=6)
        axes[1, 0].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        axes[1, 0].set_xlabel('Лаг, дни')
        axes[1, 0].set_ylabel('Spearman корреляция')
        axes[1, 0].set_title('Лаговая корреляция: влияние нефти на цену акции')
        axes[1, 0].grid(True, alpha=0.3)

        max_corr_idx = np.argmax(np.abs(correlations))
        max_corr = correlations[max_corr_idx]
        axes[1, 0].annotate(f'Максимум: лаг {max_corr_idx}, r = {max_corr:.3f}',
                            xy=(max_corr_idx, max_corr), xytext=(max_corr_idx + 5, max_corr - 0.1),
                            arrowprops=dict(arrowstyle='->'), fontsize=9)

        years = sorted(self.df['year'].unique())
        yearly_corr = []
        for year in years:
            year_df = self.df[self.df['year'] == year]
            if len(year_df) > 50:
                corr = year_df['oil_brent'].corr(year_df['price'], method='spearman')
                yearly_corr.append(corr)
            else:
                yearly_corr.append(0)

        colors_corr = ['green' if c > 0 else 'red' for c in yearly_corr]
        axes[1, 1].bar(years, yearly_corr, color=colors_corr, alpha=0.7)
        axes[1, 1].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        axes[1, 1].set_xlabel('Год')
        axes[1, 1].set_ylabel('Spearman корреляция')
        axes[1, 1].set_title('Корреляция цена акции vs нефть Brent по годам')
        axes[1, 1].grid(True, alpha=0.3, axis='y')

        for i, (year, corr) in enumerate(zip(years, yearly_corr)):
            axes[1, 1].text(year, corr + 0.02 if corr > 0 else corr - 0.08, f'{corr:.3f}', ha='center', fontsize=9)

        plt.suptitle('Анализ зависимости цены акций Газпрома от нефти Brent')
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '07_oil_analysis.png', dpi=150)
        plt.close()

        self.observations['07_oil'] = f"""
        Корреляция с нефтью (Spearman): текущая {correlations[0]:.3f}
        Максимальная корреляция: {max_corr:.3f} при лаге {max_corr_idx} дней
        Корреляция по годам: {dict(zip(years, yearly_corr))}
        """
        print("  07_oil_analysis.png")

    def plot_08_usd_analysis(self):
        """8. Анализ зависимости от курса USD"""
        if 'usd_rate' not in self.df.columns:
            print("  Нет данных о курсе USD")
            return

        fig, axes = plt.subplots(2, 2, figsize=(16, 12))

        axes[0, 0].scatter(self.df['usd_rate'], self.df['price'], alpha=0.3, s=15, c='blue')
        z = np.polyfit(self.df['usd_rate'].dropna(), self.df.loc[self.df['usd_rate'].notna(), 'price'], 1)
        p = np.poly1d(z)
        x_sorted = np.sort(self.df['usd_rate'].dropna())
        axes[0, 0].plot(x_sorted, p(x_sorted), 'r-', linewidth=2,
                        label=f"Spearman r = {self.df['usd_rate'].corr(self.df['price'], method='spearman'):.3f}")
        axes[0, 0].set_xlabel('Курс USD, руб')
        axes[0, 0].set_ylabel('Цена акции, руб')
        axes[0, 0].set_title('Зависимость цены акций от курса доллара')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)

        ax1 = axes[0, 1]
        ax1.plot(self.df['date'], self.df['price'], 'b-', linewidth=1.5, label='Цена акции')
        ax1.set_xlabel('Дата')
        ax1.set_ylabel('Цена акции, руб', color='b')
        ax1.tick_params(axis='y', labelcolor='b')

        ax2 = ax1.twinx()
        ax2.plot(self.df['date'], self.df['usd_rate'], 'orange', linewidth=1.5, alpha=0.7, label='Курс USD')
        ax2.set_ylabel('Курс USD, руб', color='orange')
        ax2.tick_params(axis='y', labelcolor='orange')

        ax1.set_title('Динамика цены акций и курса доллара')
        ax1.grid(True, alpha=0.3)
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

        lags = range(0, 31)
        correlations = []
        for lag in lags:
            if lag == 0:
                corr = self.df['usd_rate'].corr(self.df['price'], method='spearman')
            else:
                usd_shifted = self.df['usd_rate'].shift(lag)
                corr = usd_shifted.corr(self.df['price'], method='spearman')
            correlations.append(corr)

        axes[1, 0].plot(lags, correlations, 'o-', color='purple', linewidth=2, markersize=6)
        axes[1, 0].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        axes[1, 0].set_xlabel('Лаг, дни')
        axes[1, 0].set_ylabel('Spearman корреляция')
        axes[1, 0].set_title('Лаговая корреляция: влияние курса USD на цену акции')
        axes[1, 0].grid(True, alpha=0.3)

        max_corr_idx = np.argmax(np.abs(correlations))
        max_corr = correlations[max_corr_idx]
        axes[1, 0].annotate(f'Максимум: лаг {max_corr_idx}, r = {max_corr:.3f}',
                            xy=(max_corr_idx, max_corr), xytext=(max_corr_idx + 5, max_corr - 0.1),
                            arrowprops=dict(arrowstyle='->'), fontsize=9)

        years = sorted(self.df['year'].unique())
        yearly_corr = []
        for year in years:
            year_df = self.df[self.df['year'] == year]
            if len(year_df) > 50:
                corr = year_df['usd_rate'].corr(year_df['price'], method='spearman')
                yearly_corr.append(corr)
            else:
                yearly_corr.append(0)

        colors_corr = ['green' if c > 0 else 'red' for c in yearly_corr]
        axes[1, 1].bar(years, yearly_corr, color=colors_corr, alpha=0.7)
        axes[1, 1].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        axes[1, 1].set_xlabel('Год')
        axes[1, 1].set_ylabel('Spearman корреляция')
        axes[1, 1].set_title('Корреляция цена акции vs курс USD по годам')
        axes[1, 1].grid(True, alpha=0.3, axis='y')

        for i, (year, corr) in enumerate(zip(years, yearly_corr)):
            axes[1, 1].text(year, corr + 0.02 if corr > 0 else corr - 0.08, f'{corr:.3f}', ha='center', fontsize=9)

        plt.suptitle('Анализ зависимости цены акций Газпрома от курса доллара США')
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '08_usd_analysis.png', dpi=150)
        plt.close()

        self.observations['08_usd'] = f"""
        Корреляция с курсом USD (Spearman): текущая {correlations[0]:.3f}
        Максимальная корреляция: {max_corr:.3f} при лаге {max_corr_idx} дней
        Корреляция по годам: {dict(zip(years, yearly_corr))}
        """
        print("  08_usd_analysis.png")

    def plot_09_cbr_analysis(self):
        """9. Анализ зависимости от ключевой ставки ЦБ"""
        if 'cbr_key_rate' not in self.df.columns:
            print("  Нет данных о ставке ЦБ")
            return

        fig, axes = plt.subplots(2, 2, figsize=(16, 12))

        axes[0, 0].scatter(self.df['cbr_key_rate'], self.df['price'], alpha=0.3, s=15, c='blue')
        z = np.polyfit(self.df['cbr_key_rate'].dropna(), self.df.loc[self.df['cbr_key_rate'].notna(), 'price'], 1)
        p = np.poly1d(z)
        x_sorted = np.sort(self.df['cbr_key_rate'].dropna())
        axes[0, 0].plot(x_sorted, p(x_sorted), 'r-', linewidth=2,
                        label=f"Spearman r = {self.df['cbr_key_rate'].corr(self.df['price'], method='spearman'):.3f}")
        axes[0, 0].set_xlabel('Ключевая ставка ЦБ, %')
        axes[0, 0].set_ylabel('Цена акции, руб')
        axes[0, 0].set_title('Зависимость цены акций от ключевой ставки')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)

        ax1 = axes[0, 1]
        ax1.plot(self.df['date'], self.df['price'], 'b-', linewidth=1.5, label='Цена акции')
        ax1.set_xlabel('Дата')
        ax1.set_ylabel('Цена акции, руб', color='b')
        ax1.tick_params(axis='y', labelcolor='b')

        ax2 = ax1.twinx()
        ax2.plot(self.df['date'], self.df['cbr_key_rate'], 'r-', linewidth=1.5, alpha=0.7, label='Ставка ЦБ')
        ax2.set_ylabel('Ключевая ставка ЦБ, %', color='r')
        ax2.tick_params(axis='y', labelcolor='r')

        ax1.set_title('Динамика цены акций и ключевой ставки ЦБ')
        ax1.grid(True, alpha=0.3)
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

        years = sorted(self.df['year'].unique())
        yearly_corr = []
        for year in years:
            year_df = self.df[self.df['year'] == year]
            if len(year_df) > 50:
                corr = year_df['cbr_key_rate'].corr(year_df['price'], method='spearman')
                yearly_corr.append(corr)
            else:
                yearly_corr.append(0)

        colors_corr = ['green' if c > 0 else 'red' for c in yearly_corr]
        axes[1, 0].bar(years, yearly_corr, color=colors_corr, alpha=0.7)
        axes[1, 0].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        axes[1, 0].set_xlabel('Год')
        axes[1, 0].set_ylabel('Spearman корреляция')
        axes[1, 0].set_title('Корреляция цена акции vs ставка ЦБ по годам')
        axes[1, 0].grid(True, alpha=0.3, axis='y')

        for i, (year, corr) in enumerate(zip(years, yearly_corr)):
            axes[1, 0].text(year, corr + 0.02 if corr > 0 else corr - 0.08, f'{corr:.3f}', ha='center', fontsize=9)

        # График изменений ставки
        rate_changes = self.df[self.df['cbr_key_rate'].diff() != 0][['date', 'cbr_key_rate']].dropna()
        axes[1, 1].step(rate_changes['date'], rate_changes['cbr_key_rate'], where='post',
                        color='red', linewidth=2, label='Изменения ставки')
        axes[1, 1].set_xlabel('Дата')
        axes[1, 1].set_ylabel('Ключевая ставка ЦБ, %')
        axes[1, 1].set_title('История изменений ключевой ставки ЦБ')
        axes[1, 1].grid(True, alpha=0.3)
        axes[1, 1].legend()

        plt.suptitle('Анализ зависимости цены акций Газпрома от ключевой ставки ЦБ')
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '09_cbr_analysis.png', dpi=150)
        plt.close()

        current_corr = self.df['cbr_key_rate'].corr(self.df['price'], method='spearman')
        self.observations['09_cbr'] = f"""
        Корреляция со ставкой ЦБ (Spearman): {current_corr:.3f}
        Корреляция по годам: {dict(zip(years, yearly_corr))}
        Количество изменений ставки: {len(rate_changes)}
        """
        print("  09_cbr_analysis.png")

    def plot_10_fundamental_analysis(self):
        """10. Фундаментальный анализ"""
        if 'bvps_rub' not in self.df.columns or self.df['bvps_rub'].isna().all():
            print("  Нет фундаментальных данных")
            return

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        year_data = self.df.groupby('year').agg({
            'price': 'mean',
            'bvps_rub': 'first',
            'graham_number_rub': 'first'
        }).reset_index()
        year_data = year_data.dropna(subset=['bvps_rub'])

        axes[0, 0].plot(year_data['year'], year_data['price'], 'o-', label='Рыночная цена', linewidth=2, markersize=8)
        axes[0, 0].plot(year_data['year'], year_data['bvps_rub'], 's--', label='BVPS', linewidth=2, markersize=8)
        axes[0, 0].set_xlabel('Год')
        axes[0, 0].set_ylabel('Рубли')
        axes[0, 0].set_title('Цена vs Балансовая стоимость')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)

        discount = (1 - year_data['price'] / year_data['bvps_rub']) * 100
        colors = ['red' if d > 0 else 'green' for d in discount]
        axes[0, 1].bar(year_data['year'], discount, color=colors, alpha=0.7)
        axes[0, 1].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        axes[0, 1].set_xlabel('Год')
        axes[0, 1].set_ylabel('Дисконт к BVPS, %')
        axes[0, 1].set_title('Дисконт рыночной цены к балансовой стоимости')
        axes[0, 1].grid(True, alpha=0.3)

        if 'graham_number_rub' in self.df.columns:
            graham_yearly = self.df.groupby('year')['graham_number_rub'].first().dropna()
            axes[1, 0].plot(graham_yearly.index, graham_yearly.values, 'o-', label='Graham Number', linewidth=2, markersize=8)
            axes[1, 0].plot(year_data['year'], year_data['price'], 's--', label='Рыночная цена', linewidth=2, markersize=8)
            axes[1, 0].set_xlabel('Год')
            axes[1, 0].set_ylabel('Рубли')
            axes[1, 0].set_title('Цена vs Graham Number')
            axes[1, 0].legend()
            axes[1, 0].grid(True, alpha=0.3)

        if 'pe_ratio' in self.df.columns:
            pe_yearly = self.df.groupby('year')['pe_ratio'].first().dropna()
            axes[1, 1].plot(pe_yearly.index, pe_yearly.values, 'o-', label='P/E', linewidth=2, markersize=8)
            axes[1, 1].set_xlabel('Год')
            axes[1, 1].set_ylabel('P/E')
            axes[1, 1].set_title('Динамика мультипликатора P/E')
            axes[1, 1].grid(True, alpha=0.3)

        plt.suptitle('Фундаментальный анализ')
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '10_fundamental_analysis.png', dpi=150)
        plt.close()

        self.observations['10_fundamental'] = f"""
        BVPS средний: {self.df['bvps_rub'].mean():.2f} руб
        P/BV средний: {self.df['pb_ratio'].mean():.2f}
        P/E средний: {self.df['pe_ratio'].mean():.2f}
        """
        print("  10_fundamental_analysis.png")

    def plot_11a_correlation_by_year_lenta(self):
        """11a. Корреляция по годам для категорий Lenta"""
        years = sorted(self.df['year'].unique())
        lenta_factors = ['lenta_war', 'lenta_sanctions', 'lenta_political', 'lenta_oil_gas']
        lenta_labels = ['Война', 'Санкции', 'Политика', 'Нефть/Газ']

        fig, ax = plt.subplots(figsize=(12, 6))

        for factor, label in zip(lenta_factors, lenta_labels):
            if factor in self.df.columns:
                corrs = []
                for year in years:
                    year_df = self.df[self.df['year'] == year]
                    if len(year_df) > 50:
                        corr = year_df[factor].corr(year_df['price'], method='spearman')
                        corrs.append(corr)
                    else:
                        corrs.append(None)
                ax.plot(years, corrs, 'o-', label=label, linewidth=2, markersize=8)
                for i, (year, corr) in enumerate(zip(years, corrs)):
                    if corr is not None:
                        ax.annotate(f'{corr:.2f}', (year, corr), textcoords="offset points",
                                    xytext=(0, 10), ha='center', fontsize=8)

        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax.set_xlabel('Год')
        ax.set_ylabel('Spearman корреляция с ценой')
        ax.set_title('Динамика корреляции категорий Lenta с ценой по годам')
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '11a_correlation_by_year_lenta.png', dpi=150)
        plt.close()
        print("  11a_correlation_by_year_lenta.png")

    def plot_11b_correlation_by_year_comments(self):
        """11b. Корреляция по годам для категорий комментариев"""
        years = sorted(self.df['year'].unique())
        comment_factors = ['comments_price', 'comments_dividends', 'comments_macro', 'comments_news']
        comment_labels = ['Цена', 'Дивиденды', 'Макро', 'Новости']

        fig, ax = plt.subplots(figsize=(12, 6))

        for factor, label in zip(comment_factors, comment_labels):
            if factor in self.df.columns:
                corrs = []
                for year in years:
                    year_df = self.df[self.df['year'] == year]
                    if len(year_df) > 50:
                        corr = year_df[factor].corr(year_df['price'], method='spearman')
                        corrs.append(corr)
                    else:
                        corrs.append(None)
                ax.plot(years, corrs, 'o-', label=label, linewidth=2, markersize=8)
                for i, (year, corr) in enumerate(zip(years, corrs)):
                    if corr is not None:
                        ax.annotate(f'{corr:.2f}', (year, corr), textcoords="offset points",
                                    xytext=(0, 10), ha='center', fontsize=8)

        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax.set_xlabel('Год')
        ax.set_ylabel('Spearman корреляция с ценой')
        ax.set_title('Динамика корреляции категорий комментариев с ценой по годам')
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '11b_correlation_by_year_comments.png', dpi=150)
        plt.close()
        print("  11b_correlation_by_year_comments.png")

    def plot_11c_correlation_by_year_macro(self):
        """11c. Корреляция по годам для макропоказателей"""
        years = sorted(self.df['year'].unique())
        macro_factors = ['oil_brent', 'gas_henry_hub', 'cbr_key_rate', 'usd_rate']
        macro_labels = ['Нефть Brent', 'Газ Henry Hub', 'Ключевая ставка', 'Курс USD']

        fig, ax = plt.subplots(figsize=(12, 6))

        for factor, label in zip(macro_factors, macro_labels):
            if factor in self.df.columns:
                corrs = []
                for year in years:
                    year_df = self.df[self.df['year'] == year]
                    if len(year_df) > 50:
                        corr = year_df[factor].corr(year_df['price'], method='spearman')
                        corrs.append(corr)
                    else:
                        corrs.append(None)
                ax.plot(years, corrs, 'o-', label=label, linewidth=2, markersize=8)
                for i, (year, corr) in enumerate(zip(years, corrs)):
                    if corr is not None:
                        ax.annotate(f'{corr:.2f}', (year, corr), textcoords="offset points",
                                    xytext=(0, 10), ha='center', fontsize=8)

        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax.set_xlabel('Год')
        ax.set_ylabel('Spearman корреляция с ценой')
        ax.set_title('Динамика корреляции макропоказателей с ценой по годам')
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / '11c_correlation_by_year_macro.png', dpi=150)
        plt.close()
        print("  11c_correlation_by_year_macro.png")

    def generate_report(self):
        """Генерация полного текстового отчёта со всеми корреляциями и матрицами"""
        report_path = OUTPUT_DIR / "analysis_report.txt"

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("=" * 120 + "\n")
            f.write("ПОЛНЫЙ АНАЛИТИЧЕСКИЙ ОТЧЁТ ПО АКЦИЯМ ГАЗПРОМА (2020-2026)\n")
            f.write(f"Дата создания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Период данных: {self.df['date'].min().date()} - {self.df['date'].max().date()}\n")
            f.write(f"Количество торговых дней: {len(self.df)}\n")
            f.write(f"Количество признаков: {len(self.df.columns)}\n")
            f.write("=" * 120 + "\n\n")

            # ========== 1. СТАТИСТИКА ПО ВСЕМ ЧИСЛОВЫМ ПРИЗНАКАМ ==========
            f.write("1. ПОЛНАЯ СТАТИСТИКА ПО ВСЕМ ЧИСЛОВЫМ ПРИЗНАКАМ\n")
            f.write("-" * 120 + "\n")

            numeric_cols = self.df.select_dtypes(include=[np.number]).columns
            for col in sorted(numeric_cols):
                if col in ['year', 'month', 'direction_next_day']:
                    continue
                data = self.df[col].dropna()
                if len(data) > 0:
                    f.write(f"\n{col}:\n")
                    f.write(f"  Среднее: {data.mean():15.4f}    Медиана: {data.median():15.4f}\n")
                    f.write(f"  Стд.откл: {data.std():15.4f}    Мин: {data.min():15.4f}    Макс: {data.max():15.4f}\n")
                    f.write(f"  Асимметрия: {stats.skew(data):11.4f}    Эксцесс: {stats.kurtosis(data):11.4f}\n")
            f.write("\n\n")

            # ========== 2. ВСЕ КОРРЕЛЯЦИИ С ЦЕНОЙ (PEARSON) ==========
            f.write("2. ВСЕ КОРРЕЛЯЦИИ С ЦЕНОЙ (Pearson) — отсортированы по убыванию абсолютного значения\n")
            f.write("-" * 120 + "\n")
            f.write(f"{'Признак':<35} {'Корреляция':>12} {'Направление':>12} {'Сила связи':>15}\n")
            f.write("-" * 120 + "\n")

            pearson_corrs = {}
            for col in self.df.select_dtypes(include=[np.number]).columns:
                if col != 'price' and col not in ['year', 'month', 'open', 'high', 'low', 'price_ma30']:
                    try:
                        corr = self.df['price'].corr(self.df[col], method='pearson')
                        if not np.isnan(corr):
                            pearson_corrs[col] = corr
                    except:
                        pass

            for col, corr in sorted(pearson_corrs.items(), key=lambda x: abs(x[1]), reverse=True):
                direction = "прямая" if corr > 0 else "обратная"
                strength = "сильная" if abs(corr) > 0.7 else "умеренная" if abs(corr) > 0.3 else "слабая"
                f.write(f"{col:<35} {corr:>+12.4f} {direction:>12} {strength:>15}\n")
            f.write("\n\n")

            # ========== 3. ВСЕ КОРРЕЛЯЦИИ С ЦЕНОЙ (SPEARMAN) ==========
            f.write("3. ВСЕ КОРРЕЛЯЦИИ С ЦЕНОЙ (Spearman) — отсортированы по убыванию абсолютного значения\n")
            f.write("-" * 120 + "\n")
            f.write(f"{'Признак':<35} {'Корреляция':>12} {'Направление':>12} {'Сила связи':>15}\n")
            f.write("-" * 120 + "\n")

            spearman_corrs = {}
            for col in self.df.select_dtypes(include=[np.number]).columns:
                if col != 'price' and col not in ['year', 'month', 'open', 'high', 'low', 'price_ma30']:
                    try:
                        corr = self.df['price'].corr(self.df[col], method='spearman')
                        if not np.isnan(corr):
                            spearman_corrs[col] = corr
                    except:
                        pass

            for col, corr in sorted(spearman_corrs.items(), key=lambda x: abs(x[1]), reverse=True):
                direction = "прямая" if corr > 0 else "обратная"
                strength = "сильная" if abs(corr) > 0.7 else "умеренная" if abs(corr) > 0.3 else "слабая"
                f.write(f"{col:<35} {corr:>+12.4f} {direction:>12} {strength:>15}\n")
            f.write("\n\n")

            # ========== 4. КОРРЕЛЯЦИОННАЯ МАТРИЦА: МАКРОПОКАЗАТЕЛИ ==========
            f.write("4. КОРРЕЛЯЦИОННАЯ МАТРИЦА МАКРОПОКАЗАТЕЛЕЙ (Spearman)\n")
            f.write("-" * 120 + "\n")

            macro_cols = ['price', 'oil_brent', 'gas_henry_hub', 'cbr_key_rate', 'usd_rate']
            existing_macro = [c for c in macro_cols if c in self.df.columns]

            if len(existing_macro) > 1:
                macro_corr = self.df[existing_macro].corr(method='spearman')

                # Форматированный вывод матрицы
                f.write(f"{'':<20}")
                for col in existing_macro:
                    f.write(f"{col:>12}")
                f.write("\n")

                for row in existing_macro:
                    f.write(f"{row:<20}")
                    for col in existing_macro:
                        val = macro_corr.loc[row, col]
                        f.write(f"{val:>12.4f}")
                    f.write("\n")
            f.write("\n\n")

            # ========== 5. КОРРЕЛЯЦИОННАЯ МАТРИЦА: ИНДЕКСЫ MOEX ==========
            f.write("5. КОРРЕЛЯЦИОННАЯ МАТРИЦА ИНДЕКСОВ MOEX С ЦЕНОЙ (Spearman)\n")
            f.write("-" * 120 + "\n")

            index_cols = ['price', 'IMOEX', 'RTSI', 'MOEXOG', 'MOEXFN', 'MOEXMM', 'MOEXCN']
            existing_index = [c for c in index_cols if c in self.df.columns]

            if len(existing_index) > 1:
                index_corr = self.df[existing_index].corr(method='spearman')

                f.write(f"{'':<15}")
                for col in existing_index:
                    f.write(f"{col:>10}")
                f.write("\n")

                for row in existing_index:
                    f.write(f"{row:<15}")
                    for col in existing_index:
                        val = index_corr.loc[row, col]
                        f.write(f"{val:>10.4f}")
                    f.write("\n")
            f.write("\n\n")

            # ========== 6. КОРРЕЛЯЦИОННАЯ МАТРИЦА: КОММЕНТАРИИ ==========
            f.write("6. КОРРЕЛЯЦИОННАЯ МАТРИЦА КОММЕНТАРИЕВ С ЦЕНОЙ (Spearman)\n")
            f.write("-" * 120 + "\n")

            comment_cols = ['price', 'comments_total', 'comments_positive', 'comments_negative', 'comments_neutral',
                            'comments_price', 'comments_dividends', 'comments_reports', 'comments_macro',
                            'comments_news']
            existing_comment = [c for c in comment_cols if c in self.df.columns]

            if len(existing_comment) > 1:
                comment_corr = self.df[existing_comment].corr(method='spearman')

                f.write(f"{'':<20}")
                for col in existing_comment:
                    f.write(f"{col:>10}")
                f.write("\n")

                for row in existing_comment:
                    f.write(f"{row:<20}")
                    for col in existing_comment:
                        val = comment_corr.loc[row, col]
                        f.write(f"{val:>10.4f}")
                    f.write("\n")
            f.write("\n\n")

            # ========== 7. КОРРЕЛЯЦИОННАЯ МАТРИЦА: LENTA ==========
            f.write("7. КОРРЕЛЯЦИОННАЯ МАТРИЦА ЗАГОЛОВКОВ LENTA С ЦЕНОЙ (Spearman)\n")
            f.write("-" * 120 + "\n")

            lenta_cols = ['price', 'lenta_total', 'lenta_positive', 'lenta_negative', 'lenta_neutral',
                          'lenta_war', 'lenta_sanctions', 'lenta_oil_gas', 'lenta_market', 'lenta_political']
            existing_lenta = [c for c in lenta_cols if c in self.df.columns]

            if len(existing_lenta) > 1:
                lenta_corr = self.df[existing_lenta].corr(method='spearman')

                f.write(f"{'':<20}")
                for col in existing_lenta:
                    f.write(f"{col:>10}")
                f.write("\n")

                for row in existing_lenta:
                    f.write(f"{row:<20}")
                    for col in existing_lenta:
                        val = lenta_corr.loc[row, col]
                        f.write(f"{val:>10.4f}")
                    f.write("\n")
            f.write("\n\n")

            # ========== 8. КОРРЕЛЯЦИОННАЯ МАТРИЦА: ФУНДАМЕНТАЛЬНЫЕ ПОКАЗАТЕЛИ ==========
            f.write("8. КОРРЕЛЯЦИОННАЯ МАТРИЦА ФУНДАМЕНТАЛЬНЫХ ПОКАЗАТЕЛЕЙ С ЦЕНОЙ (Spearman)\n")
            f.write("-" * 120 + "\n")

            fund_cols = ['price', 'bvps_rub', 'eps_rub', 'pb_ratio', 'pe_ratio', 'graham_number_rub']
            existing_fund = [c for c in fund_cols if c in self.df.columns]

            if len(existing_fund) > 1:
                fund_corr = self.df[existing_fund].corr(method='spearman')

                f.write(f"{'':<20}")
                for col in existing_fund:
                    f.write(f"{col:>12}")
                f.write("\n")

                for row in existing_fund:
                    f.write(f"{row:<20}")
                    for col in existing_fund:
                        val = fund_corr.loc[row, col]
                        f.write(f"{val:>12.4f}")
                    f.write("\n")
            f.write("\n\n")

            # ========== 9. ПАРНЫЕ КОРРЕЛЯЦИИ МЕЖДУ ВСЕМИ ПРИЗНАКАМИ (ТОП-50) ==========
            f.write("9. ТОП-50 САМЫХ СИЛЬНЫХ ПАРНЫХ КОРРЕЛЯЦИЙ МЕЖДУ ВСЕМИ ПРИЗНАКАМИ (Spearman)\n")
            f.write("-" * 120 + "\n")

            all_numeric = self.df.select_dtypes(include=[np.number]).columns
            exclude_cols = ['year', 'month', 'direction_next_day', 'open', 'high', 'low', 'price_ma30']
            analysis_cols = [c for c in all_numeric if c not in exclude_cols]

            pair_corrs = []
            for i, col1 in enumerate(analysis_cols):
                for col2 in analysis_cols[i + 1:]:
                    try:
                        corr = self.df[col1].corr(self.df[col2], method='spearman')
                        if not np.isnan(corr):
                            pair_corrs.append((col1, col2, corr))
                    except:
                        pass

            pair_corrs.sort(key=lambda x: abs(x[2]), reverse=True)

            f.write(f"{'Признак 1':<30} {'Признак 2':<30} {'Корреляция':>12}\n")
            f.write("-" * 120 + "\n")
            for col1, col2, corr in pair_corrs[:50]:
                f.write(f"{col1:<30} {col2:<30} {corr:>+12.4f}\n")
            f.write("\n\n")

            # ========== 10. СТАТИСТИКА ПО ГОДАМ ==========
            f.write("10. СТАТИСТИКА ПО ГОДАМ\n")
            f.write("-" * 120 + "\n")

            years = sorted(self.df['year'].unique())
            for year in years:
                year_df = self.df[self.df['year'] == year]
                if len(year_df) > 50:
                    f.write(f"\n{year} год (записей: {len(year_df)}):\n")
                    f.write(
                        f"  Цена: средняя {year_df['price'].mean():.2f} руб, стд {year_df['price'].std():.2f} руб\n")
                    f.write(f"  Объём: средний {year_df['volume'].mean():,.0f}\n")
                    if 'comments_total' in year_df.columns:
                        f.write(
                            f"  Комментарии: всего {year_df['comments_total'].sum():,.0f}, среднее в день {year_df['comments_total'].mean():.1f}\n")
                    if 'lenta_total' in year_df.columns:
                        f.write(
                            f"  Lenta: всего {year_df['lenta_total'].sum():,.0f}, среднее в день {year_df['lenta_total'].mean():.1f}\n")

                    # Корреляции по годам для ключевых признаков
                    f.write(f"  Корреляции с ценой (Spearman):\n")
                    for col in ['oil_brent', 'gas_henry_hub', 'cbr_key_rate', 'usd_rate', 'comments_total',
                                'lenta_war']:
                        if col in year_df.columns:
                            corr = year_df[col].corr(year_df['price'], method='spearman')
                            if not np.isnan(corr):
                                f.write(f"    {col:<20}: {corr:>+8.4f}\n")
            f.write("\n\n")

            # ========== 11. КЛЮЧЕВЫЕ СОБЫТИЯ ==========
            f.write("11. КЛЮЧЕВЫЕ СОБЫТИЯ И ЦЕНА\n")
            f.write("-" * 120 + "\n")
            for item in self.observations.get('04a_events', []):
                f.write(f"  {item}\n")
            f.write("\n")

            # ========== 12. СПИСОК ВСЕХ ПРИЗНАКОВ ==========
            f.write("12. СПИСОК ВСЕХ ПРИЗНАКОВ В ДАТАСЕТЕ\n")
            f.write("-" * 120 + "\n")
            for i, col in enumerate(sorted(self.df.columns), 1):
                dtype = self.df[col].dtype
                non_null = self.df[col].notna().sum()
                f.write(f"  {i:3}. {col:<35} {str(dtype):<15} заполнено: {non_null}/{len(self.df)}\n")
            f.write("\n")

            f.write("=" * 120 + "\n")
            f.write("СПИСОК СОЗДАННЫХ ГРАФИКОВ:\n")
            f.write("-" * 120 + "\n")
            for fname in sorted(OUTPUT_DIR.glob("*.png")):
                f.write(f"  {fname.name}\n")

        print(f"\nОтчёт сохранён: {report_path}")

    def run(self):
        """Запуск полного анализа"""
        if not self.load_data():
            return

        print("\n" + "=" * 80)
        print("ЗАПУСК ПОЛНОГО АНАЛИЗА")
        print("=" * 80 + "\n")

        self.observations['04a_events'] = []

        self.plot_01_price_boxplot_by_year()
        self.plot_02a_pearson_correlation()
        self.plot_02b_spearman_correlation()
        self.plot_02c_kendall_lenta()
        self.plot_02d_kendall_comments()
        self.plot_02e_top_correlations()
        self.plot_03_distributions()
        self.plot_04a_price_sentiment_volume()
        self.plot_04b_price_comments_categories_gas()
        self.plot_05_lenta_categories_stack()
        self.plot_06_gas_analysis()
        self.plot_07_oil_analysis()
        self.plot_08_usd_analysis()
        self.plot_09_cbr_analysis()
        self.plot_10_fundamental_analysis()
        self.plot_11a_correlation_by_year_lenta()
        self.plot_11b_correlation_by_year_comments()
        self.plot_11c_correlation_by_year_macro()

        self.generate_report()

        print("\n" + "=" * 80)
        print(f"АНАЛИЗ ЗАВЕРШЁН")
        print(f"Результаты сохранены в: {OUTPUT_DIR}")
        print("=" * 80)


if __name__ == "__main__":
    analyzer = FullAnalyzer()
    analyzer.run()