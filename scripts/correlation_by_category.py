# scripts/correlation_by_category.py

"""
Корреляционный анализ по категориям и сентименту:
- С ЦЕНОЙ: негативные/позитивные/нейтральные комментарии по категориям
- С ОБЪЁМОМ: негативные/позитивные/нейтральные комментарии по категориям
- Аналогично для заголовков Lenta
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from scipy.stats import spearmanr, pearsonr
import warnings

warnings.filterwarnings('ignore')

# Загрузка данных
df = pd.read_csv("data/daily_dataset/daily_dataset_2020-01-01_to_2026-03-31.csv")
df['date'] = pd.to_datetime(df['date'])

print("=" * 80)
print("КОРРЕЛЯЦИЯ КОММЕНТАРИЕВ И ЗАГОЛОВКОВ ПО КАТЕГОРИЯМ")
print("С ЦЕНОЙ И ОБЪЁМОМ ТОРГОВ")
print("=" * 80)
print(f"Всего записей: {len(df)}")
print(f"Компании: {df['ticker'].unique().tolist()}")
print()

# Создаём папку
plot_dir = Path("data/plots/correlation_by_category")
plot_dir.mkdir(parents=True, exist_ok=True)

# Категории
comment_categories = ['price', 'dividends', 'reports', 'macro', 'news']
comment_labels = ['Цена', 'Дивиденды', 'Отчёты', 'Макро', 'Новости']

lenta_categories = ['lenta_war', 'lenta_sanctions', 'lenta_oil_gas', 'lenta_market', 'lenta_political']
lenta_labels = ['Война', 'Санкции', 'Нефть/Газ', 'Рынок', 'Политика']

# Сентименты
sentiments = ['positive', 'negative', 'neutral']
sentiment_labels = ['Позитивные', 'Негативные', 'Нейтральные']
sentiment_colors = ['green', 'red', 'gray']

# Целевые переменные
targets = [
    {'name': 'price', 'label': 'Цена', 'suffix': 'price'},
    {'name': 'volume', 'label': 'Объём', 'suffix': 'volume'}
]

all_results = []

# ========== АНАЛИЗ ДЛЯ КАЖДОЙ ЦЕЛЕВОЙ ПЕРЕМЕННОЙ ==========
for target in targets:
    target_name = target['name']
    target_label = target['label']
    target_suffix = target['suffix']

    print(f"\n{'=' * 80}")
    print(f"📈 КОРРЕЛЯЦИЯ С {target_label.upper()}")
    print('=' * 80)

    # 1. КОММЕНТАРИИ
    print(f"\n📊 КОММЕНТАРИИ → {target_label}")
    print("-" * 60)

    for sent, sent_label in zip(sentiments, sentiment_labels):
        for cat, cat_label in zip(comment_categories, comment_labels):
            col_name = f'comments_{cat}'
            if col_name in df.columns:
                sent_col = f'comments_{sent}'
                total_col = 'comments_total'

                if sent_col in df.columns and total_col in df.columns:
                    sent_ratio = df[sent_col] / (df[total_col] + 1)
                    weighted_cat = df[col_name] * sent_ratio

                    pearson_corr, pearson_p = pearsonr(weighted_cat.fillna(0), df[target_name].fillna(0))
                    spearman_corr, spearman_p = spearmanr(weighted_cat.fillna(0), df[target_name].fillna(0))

                    all_results.append({
                        'target': target_label,
                        'source': 'comments',
                        'sentiment': sent_label,
                        'category': cat_label,
                        'pearson': pearson_corr,
                        'spearman': spearman_corr,
                        'abs_corr': max(abs(pearson_corr), abs(spearman_corr))
                    })

                    print(
                        f"   {sent_label:10} | {cat_label:12} | Pearson: {pearson_corr:6.3f} | Spearman: {spearman_corr:6.3f}")

    # 2. ЗАГОЛОВКИ LENTA
    print(f"\n📰 ЗАГОЛОВКИ LENTA → {target_label}")
    print("-" * 60)

    for sent, sent_label in zip(sentiments, sentiment_labels):
        for cat, cat_label in zip(lenta_categories, lenta_labels):
            if cat in df.columns:
                sent_col = f'lenta_{sent}'
                total_col = 'lenta_total'

                if sent_col in df.columns and total_col in df.columns:
                    sent_ratio = df[sent_col] / (df[total_col] + 1)
                    weighted_cat = df[cat] * sent_ratio

                    pearson_corr, pearson_p = pearsonr(weighted_cat.fillna(0), df[target_name].fillna(0))
                    spearman_corr, spearman_p = spearmanr(weighted_cat.fillna(0), df[target_name].fillna(0))

                    all_results.append({
                        'target': target_label,
                        'source': 'lenta',
                        'sentiment': sent_label,
                        'category': cat_label,
                        'pearson': pearson_corr,
                        'spearman': spearman_corr,
                        'abs_corr': max(abs(pearson_corr), abs(spearman_corr))
                    })

                    print(
                        f"   {sent_label:10} | {cat_label:12} | Pearson: {pearson_corr:6.3f} | Spearman: {spearman_corr:6.3f}")

# ========== ВИЗУАЛИЗАЦИЯ ==========
print("\n" + "=" * 80)
print("📊 ПОСТРОЕНИЕ ГРАФИКОВ")
print("=" * 80)

df_results = pd.DataFrame(all_results)

# Для каждого источника
for source in ['comments', 'lenta']:
    for target in targets:
        target_label = target['label']
        target_suffix = target['suffix']

        source_df = df_results[(df_results['source'] == source) & (df_results['target'] == target_label)]

        if source == 'comments':
            source_name = 'Комментарии'
            categories = comment_labels
        else:
            source_name = 'Заголовки Lenta'
            categories = lenta_labels

        if len(source_df) == 0:
            print(f"   ⚠️ Нет данных для {source_name} → {target_label}")
            continue

        # 1. Тепловая карта
        pivot_df = source_df.pivot(index='category', columns='sentiment', values='spearman')

        # Добавляем缺失的категории
        for cat in categories:
            if cat not in pivot_df.index:
                pivot_df.loc[cat] = [0, 0, 0]
        pivot_df = pivot_df.reindex(categories)

        plt.figure(figsize=(10, 6))
        sns.heatmap(pivot_df, annot=True, fmt='.3f', cmap='RdBu_r', center=0,
                    vmin=-0.3, vmax=0.3, square=True, linewidths=1,
                    cbar_kws={'label': 'Spearman correlation'})
        plt.title(f'{source_name}: корреляция с {target_label.lower()} (Spearman)',
                  fontsize=14, fontweight='bold')
        plt.xlabel('Сентимент', fontsize=12)
        plt.ylabel('Категория', fontsize=12)
        plt.tight_layout()
        plt.savefig(plot_dir / f'{source}_{target_suffix}_heatmap.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"   ✅ {source}_{target_suffix}_heatmap.png")

        # 2. Групповые столбцы (сравнение сентиментов по категориям)
        fig, ax = plt.subplots(figsize=(12, 6))
        x = np.arange(len(categories))
        width = 0.25

        for i, (sent, color) in enumerate(zip(sentiment_labels, sentiment_colors)):
            values = []
            for cat in categories:
                val = source_df[(source_df['category'] == cat) & (source_df['sentiment'] == sent)]
                if len(val) > 0:
                    values.append(val.iloc[0]['spearman'])
                else:
                    values.append(0)

            bars = ax.bar(x + i * width, values, width, label=sent, color=color, alpha=0.7)

            for bar, val in zip(bars, values):
                if abs(val) > 0.05:
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01 * np.sign(val),
                            f'{val:.2f}', ha='center', va='bottom' if val >= 0 else 'top', fontsize=8)

        ax.set_xlabel('Категория', fontsize=12)
        ax.set_ylabel(f'Spearman корреляция с {target_label.lower()}', fontsize=12)
        ax.set_title(f'{source_name}: корреляция с {target_label.lower()} по категориям', fontsize=14,
                     fontweight='bold')
        ax.set_xticks(x + width)
        ax.set_xticklabels(categories, rotation=45, ha='right')
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3, axis='y')
        plt.tight_layout()
        plt.savefig(plot_dir / f'{source}_{target_suffix}_category_bars.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"   ✅ {source}_{target_suffix}_category_bars.png")

        # 3. Групповые столбцы (сравнение категорий по сентиментам)
        fig, ax = plt.subplots(figsize=(12, 6))
        x = np.arange(len(sentiment_labels))
        width = 0.15

        colors_by_cat = {
            'Цена': '#2E86AB', 'Дивиденды': '#A23B72', 'Отчёты': '#F18F01',
            'Макро': '#1B998B', 'Новости': '#C73E1D',
            'Война': '#A23B72', 'Санкции': '#C73E1D', 'Нефть/Газ': '#F18F01',
            'Рынок': '#2E86AB', 'Политика': '#1B998B'
        }

        for i, cat in enumerate(categories):
            values = []
            for sent in sentiment_labels:
                val = source_df[(source_df['category'] == cat) & (source_df['sentiment'] == sent)]
                if len(val) > 0:
                    values.append(val.iloc[0]['spearman'])
                else:
                    values.append(0)

            bars = ax.bar(x + i * width, values, width, label=cat,
                          color=colors_by_cat.get(cat, '#888888'), alpha=0.7)

            for bar, val in zip(bars, values):
                if abs(val) > 0.05:
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01 * np.sign(val),
                            f'{val:.2f}', ha='center', va='bottom' if val >= 0 else 'top', fontsize=7)

        ax.set_xlabel('Сентимент', fontsize=12)
        ax.set_ylabel(f'Spearman корреляция с {target_label.lower()}', fontsize=12)
        ax.set_title(f'{source_name}: корреляция с {target_label.lower()} по сентиментам', fontsize=14,
                     fontweight='bold')
        ax.set_xticks(x + 2 * width)
        ax.set_xticklabels(sentiment_labels)
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax.legend(loc='best', ncol=2, fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')
        plt.tight_layout()
        plt.savefig(plot_dir / f'{source}_{target_suffix}_sentiment_bars.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"   ✅ {source}_{target_suffix}_sentiment_bars.png")

# Сводная таблица значимых корреляций
print("\n" + "=" * 80)
print("📊 ЗНАЧИМЫЕ КОРРЕЛЯЦИИ (|Spearman| > 0.1)")
print("=" * 80)

significant = df_results[abs(df_results['spearman']) > 0.1].sort_values('spearman', ascending=False)

if len(significant) > 0:
    print("\n{:<12} {:<12} {:<12} {:<12} {:>10}".format('Цель', 'Источник', 'Сентимент', 'Категория', 'Spearman'))
    print("-" * 65)
    for _, row in significant.iterrows():
        print("{:<12} {:<12} {:<12} {:<12} {:>10.3f}".format(
            row['target'], row['source'], row['sentiment'], row['category'][:12], row['spearman']))
else:
    print("   Значимых корреляций не обнаружено")

# Сохраняем результаты
df_results.to_csv(plot_dir / 'correlation_by_category_full.csv', index=False)

print("\n" + "=" * 80)
print("✅ АНАЛИЗ ЗАВЕРШЁН!")
print("=" * 80)
print(f"\n📁 Результаты сохранены в: {plot_dir}")