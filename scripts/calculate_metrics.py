#!/usr/bin/env python3
# scripts/calculate_metrics_fixed.py
"""
Расчёт финансовых коэффициентов на основе очищенных данных
"""

import pandas as pd
import numpy as np
from pathlib import Path

# Константы: количество обыкновенных акций Газпрома (млн шт.)
SHARES = 23645  # ≈ 23.645 млрд акций


def find_value(df, keywords, year_col):
    mask = df['Показатель'].str.contains('|'.join(keywords), case=False, na=False)
    if mask.any():
        return float(df[mask].iloc[0][year_col])
    return np.nan


def calculate_metrics(excel_path):
    df = pd.read_excel(excel_path, sheet_name='Raw')
    year_cols = [c for c in df.columns if 'млн руб' in c]
    years = [c.split()[0] for c in year_cols]

    results = []
    for i, year in enumerate(years):
        col = year_cols[i]
        revenue = find_value(df, ['выручка'], col)
        net_profit = find_value(df, ['прибыль за год', 'чистая прибыль'], col)
        equity_total = find_value(df, ['итого капитал'], col)
        noncontrol = find_value(df, ['неконтролирующая'], col)
        equity = equity_total - noncontrol if not np.isnan(noncontrol) else equity_total
        assets = find_value(df, ['итого активы'], col)
        liabilities = find_value(df, ['итого обязательства'], col)

        bvps = equity / SHARES  # equity в млн руб, SHARES в млн шт -> руб/акция
        eps = net_profit / SHARES
        roe = (net_profit / equity) * 100 if equity else np.nan
        roa = (net_profit / assets) * 100 if assets else np.nan
        net_margin = (net_profit / revenue) * 100 if revenue else np.nan
        debt_to_equity = liabilities / equity if equity else np.nan
        graham_number = np.sqrt(22.5 * eps * bvps) if eps and bvps else np.nan

        results.append({
            'year': year,
            'revenue_bln': revenue / 1000,
            'net_profit_bln': net_profit / 1000,
            'equity_bln': equity / 1000,
            'assets_bln': assets / 1000,
            'liabilities_bln': liabilities / 1000,
            'eps_rub': eps,
            'bvps_rub': bvps,
            'roe_pct': roe,
            'roa_pct': roa,
            'net_margin_pct': net_margin,
            'debt_to_equity': debt_to_equity,
            'graham_number_rub': graham_number
        })
    return pd.DataFrame(results)


def main():
    import sys
    input_file = sys.argv[1] if len(sys.argv) > 1 else 'data/processed/gazp_ifrs_final/2021_ifrs_clean.xlsx'
    df_metrics = calculate_metrics(Path(input_file))
    print(df_metrics.round(2).to_string(index=False))
    output_file = Path(input_file).with_name('metrics_calculated.xlsx')
    df_metrics.to_excel(output_file, index=False)
    print(f"\n✅ Сохранено в {output_file}")


if __name__ == "__main__":
    main()