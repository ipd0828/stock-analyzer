# scripts/influence_analysis_gazp_full.py

"""
Анализ влияния информационного фона на цену и объём торгов ГАЗПРОМА
ЗА ВЕСЬ ПЕРИОД (2020-2026)
- Корреляция комментариев (категории, сентимент) с ценой
- Корреляция заголовков Lenta (категории, сентимент) с ценой
- Лаговые корреляции (влияние новостей на следующий день)
- Динамика по годам
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.stats import pearsonr, spearmanr
import warnings

warnings.filterwarnings('ignore')

# Настройка для кириллицы в графиках
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False

# Загрузка данных
df = pd.read_csv("data/daily_dataset/daily_dataset_2020-01-01_to_2026-03-31.csv")
df['date'] = pd.to_datetime(df['date'])

# Фильтр только по Газпрому
df = df[df['ticker'] == 'GAZP'].copy()

print("=" * 80)
print("АНАЛИЗ ВЛИЯНИЯ ИНФОРМАЦИОННОГО ФОНА НА АКЦИИ ГАЗПРОМА")
print("=" * 80)
print(f"Период: {df['date'].min().date()} - {df['date'].max().date()}")
print(f"Всего торговых дней: {len(df)}")
print()

# Создаём папку для результатов
output_dir = Path("data/analysis/influence_gazp")
output_dir.mkdir(parents=True, exist_ok=True)

# Целевые переменные
targets = [
    {'name': 'price', 'label': 'Цена (руб)', 'file_suffix': 'price'},
    {'name': 'volume', 'label': 'Объём торгов', 'file_suffix': 'volume'}
]

# Признаки комментариев
comment_features = [
    {'col': 'comments_positive', 'label': 'Позитивные комментарии', 'type': 'sentiment'},
    {'col': 'comments_negative', 'label': 'Негативные комментарии', 'type': 'sentiment'},
    {'col': 'comments_neutral', 'label': 'Нейтральные комментарии', 'type': 'sentiment'},
    {'col': 'comments_total', 'label': 'Всего комментариев', 'type': 'volume'},
    {'col': 'comments_price', 'label': 'Категория: Цена', 'type': 'category'},
    {'col': 'comments_dividends', 'label': 'Категория: Дивиденды', 'type': 'category'},
    {'col': 'comments_reports', 'label': 'Категория: Отчёты', 'type': 'category'},
    {'col': 'comments_macro', 'label': 'Категория: Макро', 'type': 'category'},
    {'col': 'comments_news', 'label': 'Категория: Новости', 'type': 'category'},
]

# Признаки заголовков Lenta
lenta_features = [
    {'col': 'lenta_positive', 'label': 'Позитивные заголовки', 'type': 'sentiment'},
    {'col': 'lenta_negative', 'label': 'Негативные заголовки', 'type': 'sentiment'},
    {'col': 'lenta_neutral', 'label': 'Нейтральные заголовки', 'type': 'sentiment'},
    {'col': 'lenta_total', 'label': 'Всего заголовков', 'type': 'volume'},
    {'col': 'lenta_war', 'label': 'Категория: Война', 'type': 'category'},
    {'col': 'lenta_sanctions', 'label': 'Категория: Санкции', 'type': 'category'},
    {'col': 'lenta_oil_gas', 'label': 'Категория: Нефть/Газ', 'type': 'category'},
    {'col': 'lenta_market', 'label': 'Категория: Рынок', 'type': 'category'},
    {'col': 'lenta_political', 'label': 'Категория: Политика', 'type': 'category'},
]

# Результаты корреляций
all_results = []

print("📊 РАСЧЁТ КОРРЕЛЯЦИЙ (весь период)")
print("-" * 60)

for target in targets:
    target_name = target['name']
    target_label = target['label']

    print(f"\n🎯 Целевая переменная: {target_label}")

    for feature in comment_features + lenta_features:
        col = feature['col']
        if col not in df.columns:
            continue

        # Корреляция за текущий день
        mask = ~(df[col].isna() | df[target_name].isna())
        if mask.sum() < 10:
            continue

        pearson_corr, pearson_p = pearsonr(df.loc[mask, col], df.loc[mask, target_name])
        spearman_corr, spearman_p = spearmanr(df.loc[mask, col], df.loc[mask, target_name])

        # Лаговая корреляция (влияние на следующий день)
        df_shifted = df[target_name].shift(-1)
        mask_shift = ~(df[col].isna() | df_shifted.isna())
        if mask_shift.sum() > 10:
            pearson_lag, pearson_lag_p = pearsonr(df.loc[mask_shift, col], df_shifted[mask_shift])
            spearman_lag, spearman_lag_p = spearmanr(df.loc[mask_shift, col], df_shifted[mask_shift])
        else:
            spearman_lag, spearman_lag_p = None, None

        # Корреляция по годам
        yearly_corr = {}
        for year in range(2020, 2027):
            df_year = df[df['date'].dt.year == year]
            mask_year = ~(df_year[col].isna() | df_year[target_name].isna())
            if mask_year.sum() > 5:
                _, corr_year = spearmanr(df_year.loc[mask_year, col], df_year.loc[mask_year, target_name])
                yearly_corr[year] = corr_year if not np.isnan(corr_year) else None
            else:
                yearly_corr[year] = None

        all_results.append({
            'target': target_label,
            'feature': feature['label'],
            'type': feature['type'],
            'source': 'comments' if col.startswith('comments') else 'lenta',
            'correlation': spearman_corr,
            'p_value': spearman_p,
            'correlation_lag': spearman_lag,
            'p_value_lag': spearman_lag_p if spearman_lag is not None else None,
            'abs_corr': abs(spearman_corr),
            'abs_corr_lag': abs(spearman_lag) if spearman_lag is not None else 0,
            'significant': spearman_p < 0.05,
            'yearly_2020': yearly_corr.get(2020),
            'yearly_2021': yearly_corr.get(2021),
            'yearly_2022': yearly_corr.get(2022),
            'yearly_2023': yearly_corr.get(2023),
            'yearly_2024': yearly_corr.get(2024),
            'yearly_2025': yearly_corr.get(2025),
            'yearly_2026': yearly_corr.get(2026),
        })

# Создаём DataFrame с результатами
df_results = pd.DataFrame(all_results)

# ========== ТАБЛИЦА 1: КОРРЕЛЯЦИЯ С ЦЕНОЙ (весь период) ==========
print("\n" + "=" * 80)
print("ТАБЛИЦА 1. КОРРЕЛЯЦИЯ ИНФОРМАЦИОННОГО ФОНА С ЦЕНОЙ ГАЗПРОМА")
print("Весь период: 2020-2026")
print("=" * 80)

price_results = df_results[df_results['target'] == 'Цена (руб)'].sort_values('abs_corr', ascending=False)
price_results['значимость'] = price_results['p_value'].apply(
    lambda x: '***' if x < 0.01 else ('**' if x < 0.05 else ('*' if x < 0.1 else ''))
)
price_results['направление'] = price_results['correlation'].apply(
    lambda x: 'Прямая' if x > 0 else ('Обратная' if x < 0 else 'Нейтральная')
)

print("\n{:<35} {:<20} {:<12} {:<10} {:<8} {:<10}".format(
    'Показатель', 'Источник', 'Корреляция', 'p-value', 'Знач.', 'Направление'
))
print("-" * 95)

for _, row in price_results.iterrows():
    p_val_str = f"{row['p_value']:.4f}" if row['p_value'] > 0.0001 else "0.0000"
    print("{:<35} {:<20} {:>10.3f}   {:>8}   {:<6} {:<10}".format(
        row['feature'][:34],
        row['source'].capitalize(),
        row['correlation'],
        p_val_str,
        row['значимость'],
        row['направление']
    ))

# ========== ТАБЛИЦА 2: КОРРЕЛЯЦИЯ ПО ГОДАМ ==========
print("\n" + "=" * 80)
print("ТАБЛИЦА 2. ДИНАМИКА КОРРЕЛЯЦИИ С ЦЕНОЙ ПО ГОДАМ")
print("=" * 80)

# Выбираем топ-5 факторов
top_factors = price_results.head(5)['feature'].tolist()
yearly_data = price_results[price_results['feature'].isin(top_factors)]

print("\n{:<35}".format('Показатель'), end='')
for year in [2020, 2021, 2022, 2023, 2024, 2025]:
    print(f" {year:>8}", end='')
print()
print("-" * 75)

for _, row in yearly_data.iterrows():
    print("{:<35}".format(row['feature'][:34]), end='')
    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        val = row.get(f'yearly_{year}')
        if val is not None and not np.isnan(val):
            print(f" {val:>8.3f}", end='')
        else:
            print(f" {'—':>8}", end='')
    print()

# ========== ТАБЛИЦА 3: КОРРЕЛЯЦИЯ С ОБЪЁМОМ ==========
print("\n" + "=" * 80)
print("ТАБЛИЦА 3. КОРРЕЛЯЦИЯ ИНФОРМАЦИОННОГО ФОНА С ОБЪЁМОМ ТОРГОВ")
print("=" * 80)

volume_results = df_results[df_results['target'] == 'Объём торгов'].sort_values('abs_corr', ascending=False)
volume_results['значимость'] = volume_results['p_value'].apply(
    lambda x: '***' if x < 0.01 else ('**' if x < 0.05 else ('*' if x < 0.1 else ''))
)
volume_results['направление'] = volume_results['correlation'].apply(
    lambda x: 'Прямая' if x > 0 else ('Обратная' if x < 0 else 'Нейтральная')
)

print("\n{:<35} {:<20} {:<12} {:<10} {:<8} {:<10}".format(
    'Показатель', 'Источник', 'Корреляция', 'p-value', 'Знач.', 'Направление'
))
print("-" * 95)

for _, row in volume_results.head(20).iterrows():
    p_val_str = f"{row['p_value']:.4f}" if row['p_value'] > 0.0001 else "0.0000"
    print("{:<35} {:<20} {:>10.3f}   {:>8}   {:<6} {:<10}".format(
        row['feature'][:34],
        row['source'].capitalize(),
        row['correlation'],
        p_val_str,
        row['значимость'],
        row['направление']
    ))

# ========== ТАБЛИЦА 4: ЛАГОВЫЕ КОРРЕЛЯЦИИ ==========
print("\n" + "=" * 80)
print("ТАБЛИЦА 4. ВЛИЯНИЕ НОВОСТЕЙ НА ЦЕНУ ГАЗПРОМА НА СЛЕДУЮЩИЙ ДЕНЬ")
print("=" * 80)

lag_results = df_results[df_results['target'] == 'Цена (руб)'].dropna(subset=['correlation_lag'])
if len(lag_results) > 0:
    lag_results = lag_results.sort_values('abs_corr_lag', ascending=False)

    print("\n{:<35} {:<20} {:<15} {:<10} {:<10}".format(
        'Показатель', 'Источник', 'Лаг-корреляция', 'p-value', 'Направление'
    ))
    print("-" * 90)

    for _, row in lag_results.head(10).iterrows():
        direction = 'Прямая' if row['correlation_lag'] > 0 else (
            'Обратная' if row['correlation_lag'] < 0 else 'Нейтральная')
        p_val_str = f"{row['p_value_lag']:.4f}" if row['p_value_lag'] > 0.0001 else "0.0000"
        print("{:<35} {:<20} {:>12.3f}   {:>8}   {:<10}".format(
            row['feature'][:34],
            row['source'].capitalize(),
            row['correlation_lag'],
            p_val_str,
            direction
        ))
else:
    print("   Нет значимых лаговых корреляций")

# ========== СОХРАНЕНИЕ РЕЗУЛЬТАТОВ ==========
df_results.to_csv(output_dir / 'gazprom_influence_analysis.csv', index=False)
print(f"\n💾 Полные результаты сохранены: {output_dir}/gazprom_influence_analysis.csv")

# ========== ВИЗУАЛИЗАЦИЯ ==========
print("\n" + "=" * 80)
print("📊 ПОСТРОЕНИЕ ГРАФИКОВ")
print("=" * 80)

# 1. Топ корреляций с ценой
fig, ax = plt.subplots(figsize=(12, 10))
top_price = price_results.head(15).sort_values('correlation')
colors = ['green' if x > 0 else 'red' for x in top_price['correlation']]
ax.barh(top_price['feature'], top_price['correlation'], color=colors, alpha=0.7)
ax.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
ax.set_xlabel('Spearman корреляция с ценой', fontsize=12)
ax.set_title('Газпром: Топ факторов, влияющих на цену (2020-2026)', fontsize=14)
ax.grid(True, alpha=0.3, axis='x')
plt.tight_layout()
plt.savefig(output_dir / 'gazprom_top_correlations_price.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"   ✅ {output_dir}/gazprom_top_correlations_price.png")

# 2. Топ корреляций с объёмом
fig, ax = plt.subplots(figsize=(12, 10))
top_volume = volume_results.head(15).sort_values('correlation')
colors = ['green' if x > 0 else 'red' for x in top_volume['correlation']]
ax.barh(top_volume['feature'], top_volume['correlation'], color=colors, alpha=0.7)
ax.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
ax.set_xlabel('Spearman корреляция с объёмом торгов', fontsize=12)
ax.set_title('Газпром: Топ факторов, влияющих на объём торгов (2020-2026)', fontsize=14)
ax.grid(True, alpha=0.3, axis='x')
plt.tight_layout()
plt.savefig(output_dir / 'gazprom_top_correlations_volume.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"   ✅ {output_dir}/gazprom_top_correlations_volume.png")

# 3. Динамика корреляции по годам
fig, ax = plt.subplots(figsize=(14, 8))

for factor in top_factors[:5]:
    factor_data = price_results[price_results['feature'] == factor].iloc[0]
    years = []
    corrs = []
    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        val = factor_data.get(f'yearly_{year}')
        if val is not None and not np.isnan(val):
            years.append(year)
            corrs.append(val)
    if years:
        ax.plot(years, corrs, 'o-', linewidth=2, markersize=6, label=factor[:25])

ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
ax.set_xlabel('Год', fontsize=12)
ax.set_ylabel('Spearman корреляция с ценой', fontsize=12)
ax.set_title('Газпром: Динамика корреляции ключевых факторов с ценой по годам', fontsize=14)
ax.legend(loc='best', fontsize=9)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(output_dir / 'gazprom_correlation_by_year.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"   ✅ {output_dir}/gazprom_correlation_by_year.png")

print("\n" + "=" * 80)
print("✅ АНАЛИЗ ЗАВЕРШЁН")
print("=" * 80)
print(f"\n📁 Результаты сохранены в: {output_dir}")