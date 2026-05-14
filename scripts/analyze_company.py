#!/usr/bin/env python3
# scripts/analyze_company.py
"""
Универсальный полный анализ компании (2020-2026).
Аналог full_analysis.py — для любой из 5 компаний.
ВСЕ данные выводятся в отчёт.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import sys
import argparse
from datetime import datetime
import warnings
from scipy import stats

warnings.filterwarnings('ignore')

sys.path.append(str(Path(__file__).parent.parent))
from config.paths import PROCESSED_DATA_DIR

plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")
plt.rcParams['figure.figsize'] = (16, 8)
plt.rcParams['font.size'] = 10
plt.rcParams['axes.titlesize'] = 12
plt.rcParams['axes.labelsize'] = 11
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False

COMPANIES = {
    'GAZP': 'Газпром',
    'SBER': 'Сбер',
    'LKOH': 'Лукойл',
    'NVTK': 'Новатэк',
    'VTBR': 'ВТБ'
}

KEY_EVENTS = {
    'COVID-19': '2020-03-11',
    'Начало СВО': '2022-02-24',
    'Мобилизация': '2022-09-21',
    'Потолок цен на нефть': '2022-12-05',
    'Отказ от дивидендов Газпрома': '2023-05-23',
}


class CompanyFullAnalyzer:
    """Полный анализ компании с детальным отчётом"""

    def __init__(self, ticker: str):
        self.ticker = ticker
        self.company_name = COMPANIES.get(ticker, ticker)
        self.df = None
        self.dataset_path = PROCESSED_DATA_DIR / f"{ticker}_dataset" / f"{ticker}_complete_dataset.csv"
        self.output_dir = Path(f"data/plots/{ticker}_analysis")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.report_sections = []
        self.all_correlations = {}

    def load_data(self):
        if not self.dataset_path.exists():
            print(f"❌ Файл не найден: {self.dataset_path}")
            return False
        self.df = pd.read_csv(self.dataset_path)
        self.df['date'] = pd.to_datetime(self.df['date'])
        self.df = self.df.sort_values('date')
        self.df['year'] = self.df['date'].dt.year
        self.df['month'] = self.df['date'].dt.month
        if all(c in self.df.columns for c in ['high', 'low']):
            self.df['price_range'] = self.df['high'] - self.df['low']
            self.df['price_range_pct'] = (self.df['high'] - self.df['low']) / self.df['low'] * 100
        if 'volume' in self.df.columns:
            self.df['volume_ma7'] = self.df['volume'].rolling(7).mean()
        self.df['price_ma30'] = self.df['price'].rolling(30).mean()
        self.df['volatility_30'] = self.df['price'].rolling(30).std()
        if 'comments_positive' in self.df.columns and 'comments_negative' in self.df.columns:
            self.df['sentiment_ratio'] = (self.df['comments_positive'] + 1) / (self.df['comments_negative'] + 1)
        print(f"✅ Загружено: {len(self.df)} записей, {len(self.df.columns)} признаков")
        print(f"   Период: {self.df['date'].min().date()} - {self.df['date'].max().date()}")
        return True

    # ==================== 1. БОКСПЛОТ ====================
    def plot_01_price_boxplot_by_year(self):
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
        ax.set_title(f'{self.company_name}: Распределение цен по годам')
        ax.grid(True, alpha=0.3, axis='y')
        max_price = self.df['price'].max()
        for event_name, event_date in KEY_EVENTS.items():
            dt = pd.to_datetime(event_date)
            if self.df['date'].min() <= dt <= self.df['date'].max():
                year_val = dt.year + (dt.month - 1) / 12
                ax.annotate(event_name, xy=(year_val, max_price * 0.85),
                           fontsize=8, ha='center', color='red', alpha=0.8)
        plt.tight_layout()
        plt.savefig(self.output_dir / '01_price_boxplot_by_year.png', dpi=150)
        plt.close()

        # ДАННЫЕ ДЛЯ ОТЧЁТА
        stats_by_year = self.df.groupby('year')['price'].agg(['mean', 'median', 'std', 'min', 'max'])
        section = "1. РАСПРЕДЕЛЕНИЕ ЦЕН ПО ГОДАМ\n" + "-" * 60 + "\n"
        section += f"{'Год':<8} {'Средняя':>10} {'Медиана':>10} {'Стд.откл':>10} {'Мин':>10} {'Макс':>10}\n"
        for year in years:
            if year in stats_by_year.index:
                s = stats_by_year.loc[year]
                section += f"{year:<8} {s['mean']:>10.1f} {s['median']:>10.1f} {s['std']:>10.1f} {s['min']:>10.1f} {s['max']:>10.1f}\n"
        self.report_sections.append(section)
        print("   ✅ 01_price_boxplot_by_year.png")

    # ==================== 2a. PEARSON ====================
    def plot_02a_pearson_correlation(self):
        numeric_cols = ['price', 'volume', 'oil_brent', 'gas_henry_hub', 'cbr_key_rate', 'usd_rate',
                        'IMOEX', 'RTSI', 'MOEXOG', 'MOEXFN', 'MOEXMM', 'MOEXCN',
                        'comments_total', 'comments_positive', 'comments_negative', 'comments_neutral',
                        'comments_price', 'comments_dividends', 'comments_reports', 'comments_macro', 'comments_news',
                        'lenta_total', 'lenta_positive', 'lenta_negative', 'lenta_neutral',
                        'price_range', 'price_range_pct', 'volatility_30', 'sentiment_ratio']
        existing = [c for c in numeric_cols if c in self.df.columns]
        if len(existing) < 3:
            return
        corr_matrix = self.df[existing].corr(method='pearson')
        plt.figure(figsize=(20, 18))
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
        sns.heatmap(corr_matrix, mask=mask, annot=True, fmt='.2f', cmap='RdBu_r',
                    center=0, square=True, linewidths=0.5, annot_kws={'size': 7})
        plt.title(f'{self.company_name}: Pearson корреляция')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.savefig(self.output_dir / '02a_pearson_correlation.png', dpi=150)
        plt.close()

        # ДАННЫЕ ДЛЯ ОТЧЁТА
        price_corr = corr_matrix['price'].drop('price').sort_values(ascending=False)
        self.all_correlations['Pearson'] = price_corr.to_dict()
        section = "2. КОРРЕЛЯЦИИ С ЦЕНОЙ (Pearson)\n" + "-" * 60 + "\n"
        section += f"{'Признак':<35} {'Корреляция':>10} {'Направление':>12} {'Сила':>10}\n"
        for col, corr in price_corr.items():
            direction = "прямая" if corr > 0 else "обратная"
            strength = "сильная" if abs(corr) > 0.7 else "умеренная" if abs(corr) > 0.3 else "слабая"
            section += f"{col:<35} {corr:>+10.4f} {direction:>12} {strength:>10}\n"
        self.report_sections.append(section)
        print("   ✅ 02a_pearson_correlation.png")

    # ==================== 2b. SPEARMAN ====================
    def plot_02b_spearman_correlation(self):
        numeric_cols = ['price', 'volume', 'oil_brent', 'gas_henry_hub', 'cbr_key_rate', 'usd_rate',
                        'IMOEX', 'RTSI', 'MOEXOG', 'MOEXFN', 'MOEXMM', 'MOEXCN',
                        'comments_total', 'comments_positive', 'comments_negative', 'comments_neutral',
                        'comments_price', 'comments_dividends', 'comments_reports', 'comments_macro', 'comments_news',
                        'lenta_total', 'lenta_positive', 'lenta_negative', 'lenta_neutral',
                        'lenta_war', 'lenta_sanctions', 'lenta_oil_gas', 'lenta_market', 'lenta_political',
                        'bvps_rub', 'ncav_rub', 'eps', 'roe', 'roa', 'net_margin', 'debt_to_equity']
        existing = [c for c in numeric_cols if c in self.df.columns]
        if len(existing) < 3:
            return
        corr_matrix = self.df[existing].corr(method='spearman')
        plt.figure(figsize=(20, 18))
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
        sns.heatmap(corr_matrix, mask=mask, annot=True, fmt='.2f', cmap='RdBu_r',
                    center=0, square=True, linewidths=0.5, annot_kws={'size': 7})
        plt.title(f'{self.company_name}: Spearman корреляция')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.savefig(self.output_dir / '02b_spearman_correlation.png', dpi=150)
        plt.close()

        price_corr = corr_matrix['price'].drop('price').sort_values(ascending=False)
        self.all_correlations['Spearman'] = price_corr.to_dict()
        section = "\n3. КОРРЕЛЯЦИИ С ЦЕНОЙ (Spearman)\n" + "-" * 60 + "\n"
        section += f"{'Признак':<35} {'Корреляция':>10} {'Направление':>12} {'Сила':>10}\n"
        for col, corr in price_corr.items():
            direction = "прямая" if corr > 0 else "обратная"
            strength = "сильная" if abs(corr) > 0.7 else "умеренная" if abs(corr) > 0.3 else "слабая"
            section += f"{col:<35} {corr:>+10.4f} {direction:>12} {strength:>10}\n"
        self.report_sections.append(section)
        print("   ✅ 02b_spearman_correlation.png")

    # ==================== 2e. ТОП КОРРЕЛЯЦИЙ ====================
    def plot_02e_top_correlations(self):
        numeric_cols = ['volume', 'oil_brent', 'gas_henry_hub', 'cbr_key_rate', 'usd_rate',
                        'IMOEX', 'RTSI', 'MOEXOG', 'comments_total', 'comments_positive', 'comments_negative',
                        'lenta_total', 'lenta_war', 'lenta_sanctions', 'bvps_rub', 'eps', 'roe']
        existing = [c for c in numeric_cols if c in self.df.columns]
        if not existing:
            return
        price_corr = {col: self.df[col].corr(self.df['price'], method='spearman') for col in existing}
        price_corr = pd.Series(price_corr).sort_values()
        fig, ax = plt.subplots(figsize=(12, 8))
        colors_bar = ['green' if x > 0 else 'red' for x in price_corr.values]
        ax.barh(price_corr.index, price_corr.values, color=colors_bar, alpha=0.7)
        ax.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
        ax.set_xlabel('Spearman корреляция с ценой')
        ax.set_title(f'{self.company_name}: Топ факторов')
        for i, (idx, val) in enumerate(price_corr.items()):
            ax.text(val + 0.01 if val > 0 else val - 0.08, i, f'{val:.2f}', va='center', fontsize=9)
        plt.tight_layout()
        plt.savefig(self.output_dir / '02e_top_correlations.png', dpi=150)
        plt.close()
        print("   ✅ 02e_top_correlations.png")

    # ==================== 3. РАСПРЕДЕЛЕНИЯ ====================
    def plot_03_distributions(self):
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        axes[0, 0].hist(self.df['price'], bins=50, color='steelblue', edgecolor='black', alpha=0.7)
        axes[0, 0].axvline(self.df['price'].mean(), color='red', linestyle='--', label=f'Средняя: {self.df["price"].mean():.1f}')
        axes[0, 0].axvline(self.df['price'].median(), color='green', linestyle='--', label=f'Медиана: {self.df["price"].median():.1f}')
        axes[0, 0].set_title('Распределение цены')
        axes[0, 0].legend()
        if 'volume' in self.df.columns:
            axes[0, 1].hist(np.log1p(self.df['volume']), bins=50, color='coral', edgecolor='black', alpha=0.7)
            axes[0, 1].set_title('Объём торгов (лог)')
        if 'comments_total' in self.df.columns:
            axes[1, 0].hist(self.df['comments_total'], bins=50, color='green', edgecolor='black', alpha=0.7)
            axes[1, 0].set_title('Комментарии')
        if 'lenta_total' in self.df.columns:
            axes[1, 1].hist(self.df['lenta_total'], bins=50, color='purple', edgecolor='black', alpha=0.7)
            axes[1, 1].set_title('Заголовки Lenta')
        plt.suptitle(f'{self.company_name}: Распределения')
        plt.tight_layout()
        plt.savefig(self.output_dir / '03_distributions.png', dpi=150)
        plt.close()

        # ДАННЫЕ ДЛЯ ОТЧЁТА
        section = "\n4. ОПИСАТЕЛЬНАЯ СТАТИСТИКА\n" + "-" * 60 + "\n"
        for col_name, col_label in [('price', 'Цена'), ('volume', 'Объём'), ('comments_total', 'Комментарии'), ('lenta_total', 'Lenta')]:
            if col_name in self.df.columns:
                data = self.df[col_name].dropna()
                section += f"\n{col_label}:\n"
                section += f"  Среднее: {data.mean():.2f}\n"
                section += f"  Медиана: {data.median():.2f}\n"
                section += f"  Стд.откл: {data.std():.2f}\n"
                section += f"  Мин/Макс: {data.min():.2f} / {data.max():.2f}\n"
                section += f"  Асимметрия: {stats.skew(data):.2f}, Эксцесс: {stats.kurtosis(data):.2f}\n"
        self.report_sections.append(section)
        print("   ✅ 03_distributions.png")

    # ==================== 4a. СЕНТИМЕНТ ====================
    def plot_04a_price_sentiment_volume(self):
        if 'comments_positive' not in self.df.columns:
            return
        fig, ax = plt.subplots(figsize=(16, 8))
        ax.fill_between(self.df['date'], 0, self.df['comments_positive'], alpha=0.5, color='green', label='Позитивные')
        ax.fill_between(self.df['date'], self.df['comments_positive'],
                        self.df['comments_positive'] + self.df['comments_negative'],
                        alpha=0.5, color='red', label='Негативные')
        ax2 = ax.twinx()
        ax2.plot(self.df['date'], self.df['price'], 'k-', linewidth=1.5, alpha=0.7, label='Цена')
        ax2.set_ylabel('Цена, руб')
        ax.set_xlabel('Дата')
        ax.set_ylabel('Комментарии')
        ax.set_title(f'{self.company_name}: Цена и сентимент')
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(self.output_dir / '04a_price_sentiment_volume.png', dpi=150)
        plt.close()

        # ДАННЫЕ ДЛЯ ОТЧЁТА
        section = "\n5. СЕНТИМЕНТ КОММЕНТАРИЕВ\n" + "-" * 60 + "\n"
        for col, label in [('comments_positive', 'Позитивные'), ('comments_negative', 'Негативные'), ('comments_total', 'Всего')]:
            if col in self.df.columns:
                section += f"  {label}: всего {self.df[col].sum():.0f}, среднее в день {self.df[col].mean():.1f}\n"
        self.report_sections.append(section)
        print("   ✅ 04a_price_sentiment_volume.png")

    # ==================== 5. LENTA STACK ====================
    def plot_05_lenta_categories_stack(self):
        lenta_cats = ['lenta_war', 'lenta_sanctions', 'lenta_oil_gas', 'lenta_market', 'lenta_political']
        lenta_names = ['Война', 'Санкции', 'Нефть/Газ', 'Рынок', 'Политика']
        lenta_colors = ['darkred', 'orange', 'gold', 'steelblue', 'purple']
        existing = [(c, n, cl) for c, n, cl in zip(lenta_cats, lenta_names, lenta_colors) if c in self.df.columns]
        if not existing:
            return
        fig, ax = plt.subplots(figsize=(16, 8))
        bottom = np.zeros(len(self.df))
        for cat, name, color in existing:
            ax.fill_between(self.df['date'], bottom, bottom + self.df[cat], alpha=0.6, label=name, color=color)
            bottom += self.df[cat]
        ax2 = ax.twinx()
        ax2.plot(self.df['date'], self.df['price'], 'k-', linewidth=1.5, alpha=0.7)
        ax2.set_ylabel('Цена, руб')
        ax.set_xlabel('Дата')
        ax.set_title(f'{self.company_name}: Категории Lenta')
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(self.output_dir / '05_lenta_categories_stack.png', dpi=150)
        plt.close()

        # ДАННЫЕ ДЛЯ ОТЧЁТА
        section = "\n6. КАТЕГОРИИ LENTA\n" + "-" * 60 + "\n"
        for cat, name in zip(lenta_cats, lenta_names):
            if cat in self.df.columns:
                section += f"  {name}: всего {self.df[cat].sum():.0f}, среднее в день {self.df[cat].mean():.1f}\n"
        self.report_sections.append(section)
        print("   ✅ 05_lenta_categories_stack.png")

    # ==================== 6-9. МАКРО АНАЛИЗ ====================
    def _plot_macro_analysis(self, col, label, color, filename, file_num):
        if col not in self.df.columns:
            return None
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        valid = self.df[[col, 'price']].dropna()
        axes[0, 0].scatter(valid[col], valid['price'], alpha=0.3, s=15, c='blue')
        if len(valid) > 1:
            z = np.polyfit(valid[col], valid['price'], 1)
            axes[0, 0].plot(np.sort(valid[col]), np.poly1d(z)(np.sort(valid[col])), 'r-', linewidth=2)
        axes[0, 0].set_xlabel(label)
        axes[0, 0].set_ylabel('Цена, руб')
        axes[0, 0].set_title(f'Scatter: цена vs {label}')
        axes[0, 0].grid(True, alpha=0.3)

        ax1 = axes[0, 1]
        ax1.plot(self.df['date'], self.df['price'], 'b-', linewidth=1.5, label='Цена')
        ax1.set_ylabel('Цена, руб', color='b')
        ax2 = ax1.twinx()
        ax2.plot(self.df['date'], self.df[col], color=color, linewidth=1.5, alpha=0.7, label=label)
        ax2.set_ylabel(label, color=color)
        ax1.set_title(f'Динамика: цена и {label}')
        ax1.grid(True, alpha=0.3)

        lags = range(0, 31)
        correlations = [self.df[col].shift(lag).corr(self.df['price'], method='spearman') for lag in lags]
        axes[1, 0].plot(lags, correlations, 'o-', color='purple', linewidth=2, markersize=6)
        axes[1, 0].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        axes[1, 0].set_xlabel('Лаг, дни')
        axes[1, 0].set_ylabel('Spearman')
        axes[1, 0].set_title(f'Лаговая корреляция')
        axes[1, 0].grid(True, alpha=0.3)

        years = sorted(self.df['year'].unique())
        yearly_corr = []
        for year in years:
            year_df = self.df[self.df['year'] == year]
            corr = year_df[col].corr(year_df['price'], method='spearman') if len(year_df) > 30 else 0
            yearly_corr.append(corr)
        colors_c = ['green' if c > 0 else 'red' for c in yearly_corr]
        axes[1, 1].bar(years, yearly_corr, color=colors_c, alpha=0.7)
        axes[1, 1].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        axes[1, 1].set_xlabel('Год')
        axes[1, 1].set_ylabel('Spearman')
        axes[1, 1].set_title(f'Корреляция по годам')
        axes[1, 1].grid(True, alpha=0.3)

        plt.suptitle(f'{self.company_name}: Анализ {label}')
        plt.tight_layout()
        plt.savefig(self.output_dir / filename, dpi=150)
        plt.close()
        print(f"   ✅ {filename}")

        # ДАННЫЕ ДЛЯ ОТЧЁТА
        section = f"\n{file_num}. АНАЛИЗ: {label.upper()}\n" + "-" * 60 + "\n"
        section += f"  Текущая корреляция (Spearman): {correlations[0]:.4f}\n"
        section += f"  Максимальная корреляция: {max(correlations):.4f} (лаг {np.argmax(correlations)})\n"
        section += f"  Корреляция по годам:\n"
        for y, c in zip(years, yearly_corr):
            section += f"    {y}: {c:+.4f}\n"
        return section

    def plot_06_gas_analysis(self):
        s = self._plot_macro_analysis('gas_henry_hub', 'Газ Henry Hub, $/MMBtu', 'red', '06_gas_analysis.png', 7)
        if s:
            self.report_sections.append(s)

    def plot_07_oil_analysis(self):
        s = self._plot_macro_analysis('oil_brent', 'Нефть Brent, $/барр', 'green', '07_oil_analysis.png', 8)
        if s:
            self.report_sections.append(s)

    def plot_08_usd_analysis(self):
        s = self._plot_macro_analysis('usd_rate', 'Курс USD, руб', 'orange', '08_usd_analysis.png', 9)
        if s:
            self.report_sections.append(s)

    def plot_09_cbr_analysis(self):
        s = self._plot_macro_analysis('cbr_key_rate', 'Ключевая ставка ЦБ, %', 'red', '09_cbr_analysis.png', 10)
        if s:
            self.report_sections.append(s)

    # ==================== 10. ФУНДАМЕНТАЛЬНЫЙ АНАЛИЗ ====================
    def plot_10_fundamental_analysis(self):
        """10. Фундаментальный анализ: 4 подграфика (2×2)"""
        if 'bvps_rub' not in self.df.columns or self.df['bvps_rub'].isna().all():
            print("   ⚠️ Нет фундаментальных данных")
            return

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        year_data = self.df.groupby('year').agg({
            'price': 'mean',
            'bvps_rub': 'first',
            'graham_number_rub': 'first',
            'eps': 'first'
        }).reset_index()
        year_data = year_data.dropna(subset=['bvps_rub'])

        # График 1: Цена vs BVPS
        axes[0, 0].plot(year_data['year'], year_data['price'], 'o-',
                        label='Рыночная цена', linewidth=2, markersize=8, color='steelblue')
        axes[0, 0].plot(year_data['year'], year_data['bvps_rub'], 's--',
                        label='BVPS', linewidth=2, markersize=8, color='coral')
        for _, row in year_data.iterrows():
            axes[0, 0].annotate(f'{row["price"]:.0f}', (row['year'], row['price']),
                              textcoords="offset points", xytext=(0, 10), ha='center', fontsize=8, color='steelblue')
            axes[0, 0].annotate(f'{row["bvps_rub"]:.0f}', (row['year'], row['bvps_rub']),
                              textcoords="offset points", xytext=(0, -15), ha='center', fontsize=8, color='coral')
        axes[0, 0].set_xlabel('Год')
        axes[0, 0].set_ylabel('Рубли')
        axes[0, 0].set_title('Цена vs Балансовая стоимость')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)

        # График 2: Дисконт к BVPS
        discount = (1 - year_data['price'] / year_data['bvps_rub']) * 100
        colors_d = ['red' if d > 0 else 'green' for d in discount]
        axes[0, 1].bar(year_data['year'], discount, color=colors_d, alpha=0.7)
        axes[0, 1].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        axes[0, 1].set_xlabel('Год')
        axes[0, 1].set_ylabel('Дисконт к BVPS, %')
        axes[0, 1].set_title('Дисконт рыночной цены к балансовой стоимости')
        axes[0, 1].grid(True, alpha=0.3)
        for i, (year, d) in enumerate(zip(year_data['year'], discount)):
            axes[0, 1].text(year, d + 1.5 if d > 0 else d - 3, f'{d:.1f}%',
                          ha='center', fontsize=9, fontweight='bold')

        # График 3: Цена vs Graham Number
        if 'graham_number_rub' in self.df.columns:
            graham_yearly = self.df.groupby('year')['graham_number_rub'].first().dropna()
            if len(graham_yearly) > 0:
                axes[1, 0].plot(graham_yearly.index, graham_yearly.values, 'o-',
                              label='Graham Number', linewidth=2, markersize=8, color='green')
                axes[1, 0].plot(year_data['year'], year_data['price'], 's--',
                              label='Рыночная цена', linewidth=2, markersize=8, color='steelblue')
                axes[1, 0].set_xlabel('Год')
                axes[1, 0].set_ylabel('Рубли')
                axes[1, 0].set_title('Цена vs Graham Number')
                axes[1, 0].legend()
                axes[1, 0].grid(True, alpha=0.3)
            else:
                axes[1, 0].text(0.5, 0.5, 'Нет данных (EPS ≤ 0)', transform=axes[1, 0].transAxes,
                              ha='center', fontsize=12)
                axes[1, 0].set_title('Цена vs Graham Number (нет данных)')
        else:
            axes[1, 0].text(0.5, 0.5, 'Нет данных', transform=axes[1, 0].transAxes, ha='center', fontsize=12)
            axes[1, 0].set_title('Цена vs Graham Number (нет данных)')

        # График 4: P/E
        yearly_years = set()
        if 'period' in self.df.columns:
            yearly_years = set(self.df[self.df['period'].str.upper().isin(['Y', 'FY', '12M', 'ANNUAL'])]['year'].unique())
        if not yearly_years:
            yearly_years = set(y for y in year_data['year'].unique() if y < 2026)

        pe_data = []
        for year in sorted(yearly_years):
            yr_df = self.df[self.df['year'] == year]
            avg_price = yr_df['price'].mean()
            eps_val = yr_df['eps'].iloc[0] if 'eps' in yr_df.columns and len(yr_df) > 0 else None
            if eps_val is not None and eps_val != 0:
                pe_data.append({'year': int(year), 'price': avg_price, 'eps': eps_val,
                              'pe': avg_price / eps_val, 'is_negative': eps_val < 0, 'is_annualized': False})

        current_year = self.df['year'].max()
        if current_year not in yearly_years:
            yr_df = self.df[self.df['year'] == current_year]
            if len(yr_df) > 0:
                avg_price = yr_df['price'].mean()
                eps_val = yr_df['eps'].iloc[0] if 'eps' in yr_df.columns else None
                if eps_val and eps_val > 0:
                    annual_eps = eps_val * 4
                    pe_data.append({'year': int(current_year), 'price': avg_price, 'eps': annual_eps,
                                  'pe': avg_price / annual_eps, 'is_negative': False, 'is_annualized': True})

        pe_df = pd.DataFrame(pe_data) if pe_data else pd.DataFrame()

        if len(pe_df) > 0:
            regular = pe_df[~pe_df['is_annualized']]
            annualized = pe_df[pe_df['is_annualized']]

            axes[1, 1].plot(pe_df['year'], pe_df['pe'], 'o-', linewidth=2, markersize=8, color='blue', label='P/E')
            for _, row in regular.iterrows():
                axes[1, 1].annotate(f'{row["pe"]:.1f}', (row['year'], row['pe']),
                                  textcoords="offset points", xytext=(0, 10), ha='center', fontsize=9)
            for _, row in annualized.iterrows():
                axes[1, 1].annotate(f'{row["pe"]:.1f}*', (row['year'], row['pe']),
                                  textcoords="offset points", xytext=(0, -15), ha='center', fontsize=9, color='darkblue')
                if len(regular) > 0:
                    last_yr = regular['year'].max()
                    last_pe = regular[regular['year'] == last_yr]['pe'].values[0]
                    axes[1, 1].plot([last_yr, row['year']], [last_pe, row['pe']], '--', color='gray', alpha=0.5)

            axes[1, 1].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
            axes[1, 1].set_xlabel('Год')
            axes[1, 1].set_ylabel('P/E')
            axes[1, 1].set_title('Динамика P/E (* аннуализировано)')
            axes[1, 1].legend()
            axes[1, 1].grid(True, alpha=0.3)
        else:
            axes[1, 1].text(0.5, 0.5, 'Нет данных EPS', transform=axes[1, 1].transAxes, ha='center', fontsize=12)
            axes[1, 1].set_title('Динамика P/E (нет данных)')

        plt.suptitle(f'{self.company_name}: Фундаментальный анализ', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(self.output_dir / '10_fundamental_analysis.png', dpi=150)
        plt.close()

        # ДАННЫЕ ДЛЯ ОТЧЁТА
        section = "\n11. ФУНДАМЕНТАЛЬНЫЙ АНАЛИЗ\n" + "-" * 60 + "\n"
        section += "Примечание: используются только годовые периоды (Y).\n\n"
        section += "ТАБЛИЦА 1: Балансовая стоимость и мультипликаторы\n"
        section += f"{'Год':<8} {'Цена':>10} {'BVPS':>10} {'P/BV':>10} {'Дисконт':>10}\n"
        for _, row in year_data.iterrows():
            pb = row['price'] / row['bvps_rub'] if row['bvps_rub'] > 0 else 0
            section += f"{int(row['year']):<8} {row['price']:>10.1f} {row['bvps_rub']:>10.1f} {pb:>10.3f} {(1-pb)*100:>9.1f}%\n"

        graham_yearly = self.df.groupby('year')['graham_number_rub'].first().dropna()
        if len(graham_yearly) > 0:
            section += f"\nТАБЛИЦА 2: Graham Number = √(22.5 × EPS × BVPS)\n"
            section += f"{'Год':<8} {'Graham Number':>15}\n"
            for year, val in graham_yearly.items():
                section += f"{int(year):<8} {val:>15.2f} руб\n"

        if len(pe_df) > 0:
            section += f"\nТАБЛИЦА 3: P/E (Price to Earnings)\n"
            section += f"{'Год':<8} {'Цена':>10} {'EPS':>10} {'P/E':>10} {'Примечание':>15}\n"
            for _, row in pe_df.iterrows():
                note = "аннуализ.*" if row['is_annualized'] else ("убыток" if row['is_negative'] else "")
                section += f"{row['year']:<8} {row['price']:>10.1f} {row['eps']:>+10.2f} {row['pe']:>+10.1f} {note:>15}\n"
            if len(annualized) > 0:
                section += f"\n* EPS за {current_year} год аннуализирован (квартальный × 4)\n"

        self.report_sections.append(section)
        print("   ✅ 10_fundamental_analysis.png")


    # ==================== 11. КОРРЕЛЯЦИИ ПО ГОДАМ ====================
    def _plot_corr_by_year(self, factors, labels, title, filename):
        years = sorted(self.df['year'].unique())
        fig, ax = plt.subplots(figsize=(12, 6))
        data_for_report = {}
        for factor, label in zip(factors, labels):
            if factor in self.df.columns:
                corrs = []
                for year in years:
                    year_df = self.df[self.df['year'] == year]
                    corr = year_df[factor].corr(year_df['price'], method='spearman') if len(year_df) > 30 else None
                    corrs.append(corr)
                ax.plot(years, corrs, 'o-', label=label, linewidth=2, markersize=8)
                data_for_report[label] = dict(zip(years, corrs))
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax.set_xlabel('Год')
        ax.set_ylabel('Spearman')
        ax.set_title(title)
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(self.output_dir / filename, dpi=150)
        plt.close()
        print(f"   ✅ {filename}")
        return data_for_report

    def plot_11_all_yearly_correlations(self):
        data_lenta = self._plot_corr_by_year(
            ['lenta_war', 'lenta_sanctions', 'lenta_political', 'lenta_oil_gas'],
            ['Война', 'Санкции', 'Политика', 'Нефть/Газ'],
            f'{self.company_name}: Lenta по годам', '11a_correlation_by_year_lenta.png')
        data_comments = self._plot_corr_by_year(
            ['comments_price', 'comments_dividends', 'comments_macro', 'comments_news'],
            ['Цена', 'Дивиденды', 'Макро', 'Новости'],
            f'{self.company_name}: Комментарии по годам', '11b_correlation_by_year_comments.png')
        data_macro = self._plot_corr_by_year(
            ['oil_brent', 'gas_henry_hub', 'cbr_key_rate', 'usd_rate'],
            ['Нефть', 'Газ', 'Ставка ЦБ', 'Курс USD'],
            f'{self.company_name}: Макро по годам', '11c_correlation_by_year_macro.png')

        # ДАННЫЕ ДЛЯ ОТЧЁТА
        for title, data in [("Lenta", data_lenta), ("Комментарии", data_comments), ("Макро", data_macro)]:
            if not data:
                continue
            section = f"\n12. КОРРЕЛЯЦИИ ПО ГОДАМ: {title}\n" + "-" * 60 + "\n"
            years = sorted(self.df['year'].unique())
            section += f"{'Категория':<15}"
            for y in years:
                section += f"{y:>8}"
            section += "\n"
            for label, corrs in data.items():
                section += f"{label:<15}"
                for y in years:
                    val = corrs.get(y)
                    section += f"{val:>+8.3f}" if val is not None else f"{'—':>8}"
                section += "\n"
            self.report_sections.append(section)

    # ==================== ОТЧЁТ ====================
    def generate_report(self):
        report_path = self.output_dir / "analysis_report.txt"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"АНАЛИТИЧЕСКИЙ ОТЧЁТ: {self.company_name} ({self.ticker})\n")
            f.write(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"Период: {self.df['date'].min().date()} - {self.df['date'].max().date()}\n")
            f.write(f"Торговых дней: {len(self.df)}\n")
            f.write(f"Признаков: {len(self.df.columns)}\n")
            f.write("=" * 80 + "\n\n")
            for section in self.report_sections:
                f.write(section)
                f.write("\n")
            f.write("\n" + "=" * 80 + "\n")
            f.write("СПИСОК ГРАФИКОВ:\n")
            for png in sorted(self.output_dir.glob("*.png")):
                f.write(f"  {png.name}\n")
        print(f"\n📄 Отчёт сохранён: {report_path}")

    # ==================== ЗАПУСК ====================
    def run(self):
        if not self.load_data():
            return
        print(f"\n📊 Строим графики и собираем данные...\n")
        self.plot_01_price_boxplot_by_year()
        self.plot_02a_pearson_correlation()
        self.plot_02b_spearman_correlation()
        self.plot_02e_top_correlations()
        self.plot_03_distributions()
        self.plot_04a_price_sentiment_volume()
        self.plot_05_lenta_categories_stack()
        self.plot_06_gas_analysis()
        self.plot_07_oil_analysis()
        self.plot_08_usd_analysis()
        self.plot_09_cbr_analysis()
        self.plot_10_fundamental_analysis()
        self.plot_11_all_yearly_correlations()
        self.generate_report()
        print(f"\n✅ АНАЛИЗ {self.ticker} ЗАВЕРШЁН!")
        print(f"   Графики и отчёт: {self.output_dir}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ticker', default='GAZP', choices=['GAZP', 'SBER', 'LKOH', 'NVTK', 'VTBR'])
    parser.add_argument('--all', action='store_true')
    args = parser.parse_args()
    if args.all:
        for t in COMPANIES:
            print(f"\n{'='*70}\n🔍 {COMPANIES[t]} ({t})\n{'='*70}")
            try:
                CompanyFullAnalyzer(t).run()
            except Exception as e:
                print(f"❌ Ошибка: {e}")
    else:
        CompanyFullAnalyzer(args.ticker).run()


if __name__ == "__main__":
    main()