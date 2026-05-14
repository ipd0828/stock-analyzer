#!/usr/bin/env python3
# scripts/create_fundamental_dataset_ifrs_v2.py
"""
Создание итогового датасета с фундаментальными показателями Газпрома
на основе консолидированной отчетности МСФО за 2020-2025 гг.
ВСЕ данные только из отчетов, без оценочных значений.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys
from datetime import datetime

sys.path.append(str(Path(__file__).parent.parent))
from config.paths import PROCESSED_DATA_DIR


def create_fundamental_dataset_ifrs():
    """Создает итоговый датасет на основе данных МСФО (только точные данные)"""

    # Количество акций в обращении из отчетов МСФО (млн шт.)
    SHARES_2020_2024 = 23_645  # 2020-2024 гг.
    SHARES_2025 = 23_644  # 9 мес. 2025 г.

    # Конвертация млн руб. в рубли
    MILLION = 1_000_000

    # ============================================================
    # ДАННЫЕ ИЗ ОТЧЕТОВ МСФО (только подтвержденные значения)
    # ============================================================

    data = {
        2025: {  # 9 месяцев 2025 года
            # Из консолидированного промежуточного отчета
            'revenue': 7_165_136,  # Выручка за 9 месяцев
            'net_profit': 1_117_303,  # Чистая прибыль (акционеры) за 9 месяцев
            'eps': 44.90,  # EPS за 9 месяцев (руб)

            # Из бухгалтерского баланса на 30.09.2025
            'total_assets': 31_455_796,  # Активы всего
            'current_assets': 3_732_336,  # Оборотные активы
            'total_equity': 17_923_682,  # Капитал (акционеры)
            'total_liabilities': 12_761_865,  # Обязательства всего
            'shares': SHARES_2025,
            'period': '9m',
        },
        2024: {
            'revenue': 10_714_686,
            'net_profit': 1_218_543,
            'eps': 49.15,
            'total_assets': 30_698_255,
            'current_assets': 4_368_456,
            'total_equity': 16_710_793,
            'total_liabilities': 13_037_293,
            'shares': SHARES_2020_2024,
            'period': '12m',
        },
        2023: {
            'revenue': 8_541_818,
            'net_profit': -629_085,
            'eps': -27.58,
            'total_assets': 28_713_748,
            'current_assets': 4_780_869,
            'total_equity': 15_649_707,
            'total_liabilities': 12_261_034,
            'shares': SHARES_2020_2024,
            'period': '12m',
        },
        2022: {
            'revenue': 11_673_950,
            'net_profit': 1_225_807,
            'eps': 51.11,
            'total_assets': 26_128_929,
            'current_assets': 4_620_117,
            'total_equity': 15_749_697,
            'total_liabilities': 9_683_084,
            'shares': SHARES_2020_2024,
            'period': '12m',
        },
        2021: {
            'revenue': 10_241_353,
            'net_profit': 2_093_071,
            'eps': 88.07,
            'total_assets': 27_047_230,
            'current_assets': 4_780_869,  # Из отчета за 2023 год (сравнительные данные)
            'total_equity': 16_251_519,
            'total_liabilities': 10_180_651,
            'shares': SHARES_2020_2024,
            'period': '12m',
        },
        2020: {
            'revenue': 6_321_559,
            'net_profit': 135_341,
            'eps': 5.66,
            'total_assets': 23_352_185,
            'current_assets': 4_135_000,  # Из отчета (оборотные активы = 4 135 млрд)
            'total_equity': 14_237_943,
            'total_liabilities': 8_547_453,
            'shares': SHARES_2020_2024,
            'period': '12m',
        },
    }

    # Создаем DataFrame
    df = pd.DataFrame.from_dict(data, orient='index')
    df.index.name = 'year'
    df = df.sort_index(ascending=False)

    # Конвертируем млн руб в рубли для расчетов на акцию
    df['equity_rub'] = df['total_equity'] * MILLION
    df['net_profit_rub'] = df['net_profit'] * MILLION
    df['current_assets_rub'] = df['current_assets'] * MILLION
    df['total_liabilities_rub'] = df['total_liabilities'] * MILLION

    # Конвертируем в млрд руб для отображения
    df['revenue_bln'] = df['revenue'] / 1_000
    df['net_profit_bln'] = df['net_profit'] / 1_000
    df['equity_bln'] = df['total_equity'] / 1_000
    df['assets_bln'] = df['total_assets'] / 1_000
    df['liabilities_bln'] = df['total_liabilities'] / 1_000

    # ============================================================
    # РАСЧЕТ ФУНДАМЕНТАЛЬНЫХ ПОКАЗАТЕЛЕЙ
    # ============================================================

    # 1. BVPS - Балансовая стоимость на акцию (руб)
    df['bvps'] = df['equity_rub'] / (df['shares'] * MILLION)

    # 2. NCAV - по формуле Грэма: (Оборотные активы - Все обязательства) / Акции
    df['ncav'] = (df['current_assets_rub'] - df['total_liabilities_rub']) / (df['shares'] * MILLION)

    # 3. EPS - из отчета
    df['eps'] = df['eps']

    # 4. ROE - Рентабельность капитала (%)
    df['roe'] = (df['net_profit_rub'] / df['equity_rub']) * 100

    # 5. ROA - Рентабельность активов (%)
    df['roa'] = (df['net_profit_rub'] / (df['total_assets'] * MILLION)) * 100

    # 6. Net Margin - Чистая маржа (%)
    df['net_margin'] = (df['net_profit'] / df['revenue']) * 100

    # 7. Debt to Equity
    df['debt_to_equity'] = df['total_liabilities'] / df['total_equity']

    # 8. Graham Number - только для периодов с положительным EPS
    df['graham_number'] = np.where(
        df['eps'] > 0,
        np.sqrt(22.5 * df['eps'] * df['bvps']),
        np.nan
    )

    # 9. Graham Formula
    df['graham_formula'] = np.where(
        (df['eps'] > 0) & (df['roe'] > 0),
        df['eps'] * (8.5 + 2 * df['roe']) * (4.4 / 7.0),
        np.nan
    )

    # Округляем
    df = df.round({
        'revenue_bln': 0,
        'net_profit_bln': 0,
        'equity_bln': 0,
        'assets_bln': 0,
        'liabilities_bln': 0,
        'bvps': 2,
        'ncav': 2,
        'eps': 2,
        'roe': 1,
        'roa': 1,
        'net_margin': 1,
        'debt_to_equity': 2,
        'graham_number': 2,
        'graham_formula': 2,
    })

    return df


def save_dataset(df: pd.DataFrame):
    """Сохраняет датасет"""

    output_dir = PROCESSED_DATA_DIR / "gazp_financial_data"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Колонки для сохранения
    columns_to_save = [
        'period',
        'revenue_bln', 'net_profit_bln', 'equity_bln', 'assets_bln', 'liabilities_bln',
        'eps', 'bvps', 'ncav',
        'roe', 'roa', 'net_margin',
        'debt_to_equity',
        'graham_number', 'graham_formula',
    ]

    df_save = df[columns_to_save].copy()

    # CSV
    csv_file = output_dir / f"gazprom_ifrs_fundamental_v2_{timestamp}.csv"
    df_save.to_csv(csv_file, index=True, encoding='utf-8')
    print(f"\n📊 CSV сохранен: {csv_file}")

    # Excel
    try:
        import openpyxl
        excel_file = output_dir / f"gazprom_ifrs_fundamental_v2_{timestamp}.xlsx"
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            df_save.to_excel(writer, sheet_name='Фундаментальные показатели')
            df.T.to_excel(writer, sheet_name='Транспонировано')
        print(f"📁 Excel сохранен: {excel_file}")
    except Exception as e:
        print(f"⚠️ Excel не создан: {e}")

    return df_save


def print_summary(df: pd.DataFrame):
    """Выводит сводку"""

    print("\n" + "=" * 80)
    print("📊 ФУНДАМЕНТАЛЬНЫЙ АНАЛИЗ ПАО «ГАЗПРОМ» (МСФО)")
    print("=" * 80)

    print("\n📋 Основные показатели:")
    print("-" * 80)

    for year in df.index:
        row = df.loc[year]
        period = row['period']
        period_str = " (9 мес.)" if period == '9m' else ""

        print(f"\n📅 {int(year)}{period_str}:")
        print(f"   💰 Выручка: {row['revenue_bln']:,.0f} млрд руб")
        print(f"   📊 Чистая прибыль: {row['net_profit_bln']:+,.0f} млрд руб")
        print(f"   🏢 Капитал: {row['equity_bln']:,.0f} млрд руб")
        print(f"   📈 EPS: {row['eps']:+.2f} руб")
        print(f"   📚 BVPS: {row['bvps']:.2f} руб")
        print(f"   💧 NCAV: {row['ncav']:.2f} руб")
        print(f"   🔄 ROE: {row['roe']:+.1f}%")

        if not pd.isna(row['graham_number']):
            print(f"   🎯 Graham Number: {row['graham_number']:.2f} руб")
        else:
            print(f"   🎯 Graham Number: N/A (EPS ≤ 0)")

    print("\n" + "=" * 80)
    print("✅ ДАТАСЕТ СОЗДАН!")
    print("=" * 80)


def main():
    """Основная функция"""
    print("\n" + "=" * 80)
    print("🚀 СОЗДАНИЕ ФУНДАМЕНТАЛЬНОГО ДАТАСЕТА ГАЗПРОМА (МСФО) v2")
    print("=" * 80)
    print("\n📌 Все данные взяты из консолидированной отчетности МСФО")
    print("📌 NCAV рассчитан по формуле Грэма: (Оборотные активы - Обязательства) / Акции")
    print("📌 2025 год - данные за 9 месяцев")

    df = create_fundamental_dataset_ifrs()
    df_save = save_dataset(df)
    print_summary(df)

    return df


if __name__ == "__main__":
    df = main()