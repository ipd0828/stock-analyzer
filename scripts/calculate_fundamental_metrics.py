#!/usr/bin/env python3
# scripts/calculate_fundamental_metrics.py
"""
Расчет фундаментальных показателей. Загружает все curated-файлы,
для каждого (год, период) выбирает наиболее полные данные, вычисляет метрики.
"""

import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict
import pandas as pd
import numpy as np

sys.path.append(str(Path(__file__).parent.parent))
from config.paths import PROCESSED_DATA_DIR

MILLION = 1_000_000
SHARES = 23645  # млн акций

TARGET_INDICATORS = [
    'Выручка от продаж', 'Чистая прибыль (прибыль за год)', 'Итого капитал',
    'Итого активы', 'Итого обязательства', 'Оборотные активы',
    'Краткосрочные обязательства', 'Денежные средства и их эквиваленты',
    'Дебиторская задолженность и предоплата', 'Запасы',
    'Финансовые доходы', 'Финансовые расходы', 'Амортизация',
    'Прибыль до налогообложения', 'Неконтролирующая доля участия',
    'Прибыль, приходящаяся на неконтролирующую долю'
]

def completeness_score(df: pd.DataFrame) -> int:
    inds = set(df['Показатель'].str.lower())
    return sum(1 for m in TARGET_INDICATORS if m.lower() in inds)

def extract_metrics(df: pd.DataFrame) -> dict:
    synonyms = {
        'revenue': ['Выручка от продаж', 'Выручка'],
        'net_profit': ['Чистая прибыль (прибыль за год)', 'Прибыль за год', 'Чистая прибыль', 'Прибыль за период'],
        'total_equity': ['Итого капитал'],
        'total_assets': ['Итого активы'],
        'total_liabilities': ['Итого обязательства'],
        'current_assets': ['Оборотные активы', 'Итого оборотные активы', 'Прочие оборотные активы'],
        'current_liabilities': ['Краткосрочные обязательства', 'Итого краткосрочные обязательства'],
        'cash': ['Денежные средства и их эквиваленты'],
        'receivables': ['Дебиторская задолженность и предоплата', 'Дебиторская задолженность'],
        'inventories': ['Товарно-материальные запасы', 'Запасы'],
        'finance_income': ['Финансовые доходы'],
        'finance_costs': ['Финансовые расходы'],
        'amortization': ['Амортизация'],
        'profit_before_tax': ['Прибыль до налогообложения'],
        'eps': ['Базовая прибыль на акцию', 'Прибыль на акцию', 'EPS'],
        'non_control': ['Неконтролирующая доля участия'],
        'non_control_profit': ['Прибыль, приходящаяся на неконтролирующую долю'],
    }
    year_cols = [c for c in df.columns if 'млн руб' in c]
    if not year_cols:
        return {}
    main_year_col = year_cols[0]
    year = main_year_col.split()[0]
    data = {'year': year}
    for metric, patterns in synonyms.items():
        for pat in patterns:
            mask = df['Показатель'].str.contains(pat, case=False, na=False, regex=False)
            if mask.any():
                val = df.loc[mask, main_year_col].values[0]
                if pd.notna(val):
                    data[metric] = float(val)
                    break
    return data

def merge_records(records):
    merged = records[0].copy()
    for rec in records[1:]:
        for k, v in rec.items():
            if k not in merged or pd.isna(merged[k]):
                merged[k] = v
    return merged

def load_all_data(input_dir: Path, use_raw: bool = False) -> pd.DataFrame:
    pattern = "*_raw.xlsx" if use_raw else "*_curated.xlsx"
    files = list(input_dir.glob(pattern))
    if not files:
        print(f"❌ Не найдено файлов {pattern}")
        return pd.DataFrame()

    group_map = defaultdict(list)
    for file in files:
        parts = file.stem.split('_')
        year = parts[0] if parts else None
        period = parts[1] if len(parts) > 1 else '12m'
        if year and re.match(r'20\d{2}', year):
            group_map[(year, period)].append(file)

    all_metrics = []
    for (year, period), f_list in group_map.items():
        scored = [(completeness_score(pd.read_excel(f)), f, pd.read_excel(f)) for f in f_list]
        scored.sort(key=lambda x: x[0], reverse=True)
        best_completeness = scored[0][0]
        best_files = [item for item in scored if item[0] == best_completeness]
        records = []
        for _, f, df in best_files:
            rec = extract_metrics(df)
            if rec:
                records.append(rec)
        if records:
            merged = merge_records(records)
            merged['period'] = period
            all_metrics.append(merged)

    if not all_metrics:
        return pd.DataFrame()
    df = pd.DataFrame(all_metrics)
    for col in df.columns:
        if col not in ['year', 'period']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.drop_duplicates(subset=['year', 'period'])
    return df

def annualize_if_needed(df: pd.DataFrame) -> pd.DataFrame:
    balance = ['total_assets','total_liabilities','total_equity','current_assets','current_liabilities','cash','receivables','inventories']
    factor_map = {'12m':1, '9m':4/3, '6m':2, '3m':4, 'quarterly':1}
    for idx, row in df.iterrows():
        factor = factor_map.get(row['period'], 1)
        for col in df.columns:
            if col not in balance and col not in ['year','period']:
                df.at[idx, col] = row[col] * factor
    return df

def calculate_metrics(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    required = ['profit_before_tax','finance_costs','finance_income','amortization',
                'cash','current_assets','receivables','inventories','current_liabilities',
                'non_control','non_control_profit']
    for col in required:
        if col not in df.columns:
            df[col] = 0
        df[col] = df[col].fillna(0)

    df['equity_share'] = df['total_equity'] - df['non_control']
    df['net_profit_share'] = df['net_profit'] - df['non_control_profit']

    df['ebitda'] = df['profit_before_tax'] + df['finance_costs'] - df['finance_income'] + df['amortization']

    for col, name in [('revenue','revenue_bln'), ('net_profit_share','net_profit_bln'),
                      ('equity_share','equity_bln'), ('total_assets','assets_bln'),
                      ('total_liabilities','liabilities_bln'), ('cash','cash_bln'),
                      ('current_assets','current_assets_bln'), ('receivables','receivables_bln'),
                      ('inventories','inventories_bln'), ('ebitda','ebitda_bln')]:
        df[name] = df[col] / 1_000

    df['bvps'] = (df['equity_share'] * MILLION) / (SHARES * MILLION)
    df['eps'] = df['net_profit_share'] / SHARES
    df['ncav'] = (df['current_assets'] - df['total_liabilities']) * MILLION / (SHARES * MILLION)
    df['roe'] = (df['net_profit_share'] / df['equity_share']) * 100
    df['roa'] = (df['net_profit_share'] / df['total_assets']) * 100
    df['net_margin'] = (df['net_profit_share'] / df['revenue']) * 100
    df['debt_to_equity'] = df['total_liabilities'] / df['equity_share']
    df['receivables_to_revenue'] = df['receivables'] / df['revenue']
    df['inventories_to_revenue'] = df['inventories'] / df['revenue']
    df['current_ratio'] = np.where(df['current_liabilities'] > 0, df['current_assets'] / df['current_liabilities'], np.nan)
    df['graham_number'] = np.where(df['eps'] > 0, np.sqrt(22.5 * df['eps'] * df['bvps']), np.nan)
    df['graham_formula'] = np.where((df['eps'] > 0) & (df['roe'] > 0), df['eps'] * (8.5 + 2 * df['roe']) * (4.4 / 7.0), np.nan)

    if 'period' not in df.columns:
        df['period'] = '12m'
    df = df.sort_values('year', ascending=False)

    cols = ['year','period','revenue_bln','net_profit_bln','equity_bln','assets_bln','liabilities_bln',
            'cash_bln','current_assets_bln','receivables_bln','inventories_bln','ebitda_bln',
            'eps','bvps','ncav','roe','roa','net_margin','debt_to_equity',
            'receivables_to_revenue','inventories_to_revenue','current_ratio',
            'graham_number','graham_formula']
    df = df[cols]

    df = df.round({
        'revenue_bln':0, 'net_profit_bln':0, 'equity_bln':0, 'assets_bln':0, 'liabilities_bln':0,
        'cash_bln':0, 'current_assets_bln':0, 'receivables_bln':0, 'inventories_bln':0, 'ebitda_bln':0,
        'eps':2, 'bvps':2, 'ncav':2,
        'roe':1, 'roa':1, 'net_margin':1,
        'debt_to_equity':2, 'receivables_to_revenue':2, 'inventories_to_revenue':2, 'current_ratio':2,
        'graham_number':2, 'graham_formula':2
    })
    return df

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--use-raw', action='store_true')
    parser.add_argument('--periods', type=str, default='12m,9m,quarterly')
    args = parser.parse_args()
    allowed = [p.strip() for p in args.periods.split(',')]

    input_dir = PROCESSED_DATA_DIR / "gazp_universal"
    df = load_all_data(input_dir, args.use_raw)
    if df.empty:
        print("❌ Нет данных")
        return

    df = df[df['period'].isin(allowed)]
    if df.empty:
        print("❌ После фильтрации периодов данных не осталось")
        return

    df = annualize_if_needed(df)
    result = calculate_metrics(df)

    suffix = "_raw" if args.use_raw else ""
    outfile = input_dir / f"gazp_manual_data{suffix}.csv"
    result.to_csv(outfile, index=False, encoding='utf-8')
    print(f"\n✅ Сохранено: {outfile}")
    print(result.to_string())

if __name__ == "__main__":
    main()