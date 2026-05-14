# scripts/prepare_calendar_for_ml.py

"""
Подготовка календаря событий для ML-датасета
- Фильтрация по нашим компаниям
- Разделение по типам событий
- Расчёт временных признаков
"""

import pandas as pd
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))
from config.paths import RAW_DATA_DIR, FEATURES_DIR
from config.companies import TICKERS


def prepare_calendar():
    """Подготавливает календарь событий для ML"""

    calendar_file = RAW_DATA_DIR / "calendar_events/calendar_events_all.csv"

    if not calendar_file.exists():
        print(f"❌ Файл не найден: {calendar_file}")
        return None

    df = pd.read_csv(calendar_file)
    print(f"📚 Всего событий: {len(df)}")

    # 1. Фильтруем по нашим компаниям
    df_filtered = df[df['ticker'].isin(TICKERS)].copy()
    print(f"   После фильтрации по {TICKERS}: {len(df_filtered)}")

    # 2. Парсим даты
    df_filtered['event_date'] = pd.to_datetime(df_filtered['date'], format='%d.%m.%Y', errors='coerce')
    df_filtered = df_filtered.dropna(subset=['event_date'])

    # 3. Добавляем год для группировки
    df_filtered['event_year'] = df_filtered['event_date'].dt.year

    # 4. Разделяем по типам событий
    dividend_events = df_filtered[df_filtered['category'] == 'dividends'].copy()
    report_events = df_filtered[df_filtered['category'] == 'reports'].copy()
    other_events = df_filtered[~df_filtered['category'].isin(['dividends', 'reports'])].copy()

    print(f"\n📊 ПО ТИПАМ СОБЫТИЙ:")
    print(f"   Дивиденды: {len(dividend_events)}")
    print(f"   Отчёты: {len(report_events)}")
    print(f"   Прочие: {len(other_events)}")

    # 5. Для дивидендов: определяем тип события
    if not dividend_events.empty:
        dividend_events['event_type_detail'] = dividend_events['description'].apply(
            lambda x: 'ex_date' if any(word in str(x) for word in ['отсечка', 'закрытие реестра'])
            else ('last_day' if any(word in str(x) for word in ['посл. день', 'последний день'])
                  else 'other')
        )

        print(f"\n📊 ДИВИДЕНДНЫЕ СОБЫТИЯ ПО ТИПАМ:")
        print(dividend_events['event_type_detail'].value_counts())

    # 6. Для отчётов: определяем тип отчёта
    if not report_events.empty:
        report_events['report_type_detail'] = report_events['description'].apply(
            lambda x: 'MSFO' if 'мсфо' in str(x).lower() or 'ifrs' in str(x).lower()
            else ('RSBU' if 'рсбу' in str(x).lower() or 'ras' in str(x).lower()
                  else 'other')
        )

        print(f"\n📊 ОТЧЁТНЫЕ СОБЫТИЯ ПО ТИПАМ:")
        print(report_events['report_type_detail'].value_counts())

    # 7. Сохраняем подготовленные данные
    output_dir = FEATURES_DIR / "calendar_processed"
    output_dir.mkdir(parents=True, exist_ok=True)

    dividend_events.to_csv(output_dir / "dividend_events_filtered.csv", index=False)
    report_events.to_csv(output_dir / "report_events_filtered.csv", index=False)

    print(f"\n✅ Сохранено:")
    print(f"   Дивиденды: {output_dir / 'dividend_events_filtered.csv'}")
    print(f"   Отчёты: {output_dir / 'report_events_filtered.csv'}")

    return dividend_events, report_events


def analyze_dividend_cycles(dividend_events):
    """Анализирует цикличность дивидендов"""
    if dividend_events.empty:
        return

    print("\n" + "=" * 80)
    print("📊 АНАЛИЗ ДИВИДЕНДНЫХ ЦИКЛОВ")
    print("=" * 80)

    for ticker in TICKERS:
        ticker_div = dividend_events[dividend_events['ticker'] == ticker]
        if ticker_div.empty:
            print(f"\n{ticker}: нет дивидендных событий")
            continue

        # Берём только события с суммой
        with_amount = ticker_div[ticker_div['dividend_amount'] > 0].copy()

        if with_amount.empty:
            print(f"\n{ticker}: {len(ticker_div)} событий, но нет сумм")
            continue

        # Группируем по годам
        with_amount['event_year'] = with_amount['event_date'].dt.year
        yearly = with_amount.groupby('event_year').agg({
            'dividend_amount': 'first',
            'event_date': 'first'
        }).reset_index()

        print(f"\n{ticker}:")
        for _, row in yearly.iterrows():
            print(
                f"   {int(row['event_year'])}: {row['dividend_amount']:.2f} руб (дата: {row['event_date'].strftime('%d.%m.%Y')})")

        # Средний интервал между дивидендами
        if len(yearly) > 1:
            intervals = []
            for i in range(1, len(yearly)):
                days = (yearly.iloc[i]['event_date'] - yearly.iloc[i - 1]['event_date']).days
                intervals.append(days)
            avg_interval = sum(intervals) / len(intervals)
            print(f"   Средний интервал: {avg_interval:.0f} дней")


def main():
    dividend_events, report_events = prepare_calendar()
    analyze_dividend_cycles(dividend_events)

    # Выводим примеры для проверки
    print("\n" + "=" * 80)
    print("📋 ПРИМЕРЫ ДИВИДЕНДНЫХ СОБЫТИЙ ПО КОМПАНИЯМ:")
    print("=" * 80)

    for ticker in TICKERS:
        ticker_div = dividend_events[dividend_events['ticker'] == ticker]
        if not ticker_div.empty:
            print(f"\n{ticker}:")
            for _, row in ticker_div.head(5).iterrows():
                div_type = row.get('event_type_detail', 'unknown')
                amount = row.get('dividend_amount', 0)
                print(
                    f"   {row['event_date'].strftime('%d.%m.%Y')} | {div_type:10} | {amount:.2f} руб | {row['description'][:40]}")


if __name__ == "__main__":
    main()