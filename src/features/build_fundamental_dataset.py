# src/features/build_fundamental_dataset.py

"""
Формирование итогового датасета с фундаментальными показателями
Расчёт: NCAV, Graham Number, Graham Formula
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import FEATURES_DIR
from config.companies import TICKERS, TICKER_TO_COMPANY

# Загрузка сырых данных
input_file = FEATURES_DIR / "fundamental_raw/fundamental_all_raw.csv"
output_dir = FEATURES_DIR / "fundamental_processed"
output_dir.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(input_file)
print(f"📚 Загружено {len(df)} записей")
print(f"📋 Доступные колонки: {list(df.columns)[:20]}...")


# Функция для безопасного извлечения числа
def get_number(row, col):
    if col not in row.index:
        return None
    val = row[col]
    if pd.isna(val):
        return None
    try:
        return float(val)
    except:
        return None


# Собираем показатели
results = []

for idx, row in df.iterrows():
    ticker = row['ticker']
    period = row.get('period', 'unknown')
    report_type = row.get('report_type', 'unknown')

    # Извлекаем ключевые показатели
    capital = get_number(row, 'capital')  # Капитал, млрд руб
    net_income = get_number(row, 'net_income')  # Чистая прибыль, млрд руб
    eps = get_number(row, 'eps')  # Прибыль на акцию, руб
    shares = get_number(row, 'number_of_shares')  # Количество акций, млн
    roe = get_number(row, 'roe')  # ROE
    roa = get_number(row, 'roa')  # ROA
    p_e = get_number(row, 'p_e')  # P/E
    p_b = get_number(row, 'p_b')  # P/B
    bank_assets = get_number(row, 'bank_assets')  # Активы банка, млрд руб

    # BVPS (Balance Value per Share) = Капитал / Количество акций
    bvps = None
    if capital and shares and shares > 0:
        # capital в млрд, shares в млн → результат в рублях
        bvps = capital * 1e9 / (shares * 1e6)

    # NCAV (Net Current Asset Value) на акцию
    # Для банков используем капитал как аналог
    ncav = bvps

    # Graham Number = sqrt(22.5 * EPS * BVPS)
    graham_number = None
    if eps and bvps and eps > 0 and bvps > 0:
        graham_number = np.sqrt(22.5 * eps * bvps)

    # Graham Formula: V* = EPS × (8.5 + 2g) × (4.4 / Y)
    # Упрощённо: используем ROE как темп роста g
    graham_formula = None
    if eps and roe:
        g = roe  # темп роста
        risk_free_rate = 0.07  # 7% — текущая ставка
        graham_formula = eps * (8.5 + 2 * g) * (4.4 / (risk_free_rate * 100))

    record = {
        'ticker': ticker,
        'company': TICKER_TO_COMPANY.get(ticker, ''),
        'period': period,
        'report_type': report_type,
        'capital_bn': capital,
        'net_income_bn': net_income,
        'eps_rub': eps,
        'shares_mn': shares,
        'roe': roe,
        'roa': roa,
        'p_e': p_e,
        'p_b': p_b,
        'bank_assets_bn': bank_assets,
        'bvps_rub': bvps,
        'ncav_rub': ncav,
        'graham_number_rub': graham_number,
        'graham_formula_rub': graham_formula,
    }
    results.append(record)

# Создаём DataFrame
result_df = pd.DataFrame(results)

# Сортируем
result_df = result_df.sort_values(['ticker', 'period'])

# Сохраняем
output_file = output_dir / "fundamental_metrics.csv"
result_df.to_csv(output_file, index=False, encoding='utf-8')

print(f"\n✅ Сохранено: {output_file}")
print(f"   Всего записей: {len(result_df)}")

# Статистика по компаниям
print("\n📊 СТАТИСТИКА ПО КОМПАНИЯМ:")
for ticker in TICKERS:
    ticker_df = result_df[result_df['ticker'] == ticker]
    if len(ticker_df) == 0:
        continue

    print(f"\n{ticker}:")
    print(f"   Записей: {len(ticker_df)}")

    # Последние значения (по году)
    last_row = ticker_df.iloc[-1]
    print(f"   Капитал (посл.): {last_row.get('capital_bn', 'нет'):.0f} млрд руб" if last_row.get(
        'capital_bn') else "   Капитал: нет")
    print(f"   EPS (посл.): {last_row.get('eps_rub', 'нет'):.2f} руб" if last_row.get('eps_rub') else "   EPS: нет")
    print(f"   NCAV (посл.): {last_row.get('ncav_rub', 'нет'):.2f} руб" if last_row.get('ncav_rub') else "   NCAV: нет")
    print(f"   Graham Number: {last_row.get('graham_number_rub', 'нет'):.2f} руб" if last_row.get(
        'graham_number_rub') else "   Graham Number: нет")

# Покажем пример для Сбера
print("\n📋 ПРИМЕР ДАННЫХ ДЛЯ SBER (последние 3 года):")
sber_data = result_df[result_df['ticker'] == 'SBER'].tail(3)
if len(sber_data) > 0:
    cols = ['period', 'capital_bn', 'eps_rub', 'bvps_rub', 'ncav_rub', 'graham_number_rub', 'p_e', 'p_b']
    print(sber_data[cols].to_string())

print("\n✅ Готово!")