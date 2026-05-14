# src/features/fundamental_multiples.py
"""
Модуль для расчёта финансовых мультипликаторов
Задача 3 ВКР: сбор и расчет финансовых мультипликаторов
"""

import pandas as pd
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))
from config import FEATURES_DIR, MOEX_RAW_DIR
from config import TICKERS, TICKER_TO_COMPANY


class FundamentalMultiplesCalculator:
    """
    Калькулятор фундаментальных мультипликаторов

    Источники данных:
    - Цены: MOEX ISS API (уже собрали)
    - Отчётность: smart-lab.ru, dohod.ru, или прямые ссылки на отчёты
    """

    def __init__(self):
        self.output_dir = FEATURES_DIR
        self.moex_data_dir = MOEX_RAW_DIR

        # Заглушка с типичными мультипликаторами для российских компаний
        # В реальном проекте эти данные нужно парсить из отчётов
        self.typical_multiples = {
            'SBER': {'pe': 5.2, 'pb': 0.9, 'ev_ebitda': 3.8, 'dividend_yield': 0.12},
            'LKOH': {'pe': 4.8, 'pb': 1.1, 'ev_ebitda': 3.2, 'dividend_yield': 0.09},
            'GAZP': {'pe': 3.5, 'pb': 0.5, 'ev_ebitda': 2.8, 'dividend_yield': 0.15},
            'NVTK': {'pe': 7.2, 'pb': 1.8, 'ev_ebitda': 5.1, 'dividend_yield': 0.06},
            'VTBR': {'pe': 2.1, 'pb': 0.4, 'ev_ebitda': None, 'dividend_yield': 0.0},
        }

    def load_price_data(self, ticker: str) -> pd.DataFrame:
        """Загружает данные о ценах для тикера"""
        file_path = self.moex_data_dir / "stocks_detailed.csv"
        if not file_path.exists():
            print(f"❌ Файл не найден: {file_path}")
            return None

        df = pd.read_csv(file_path)
        df['date'] = pd.to_datetime(df['date'])

        # Фильтруем по тикеру
        ticker_data = df[df['ticker'] == ticker].copy()
        ticker_data = ticker_data.sort_values('date')

        print(f"   Загружено {len(ticker_data)} записей для {ticker}")
        return ticker_data

    def calculate_pe_ratio(self, price: float, eps: float) -> float:
        """P/E = Price / Earnings Per Share"""
        if eps and eps > 0:
            return round(price / eps, 2)
        return None

    def calculate_pb_ratio(self, price: float, book_value_per_share: float) -> float:
        """P/B = Price / Book Value Per Share"""
        if book_value_per_share and book_value_per_share > 0:
            return round(price / book_value_per_share, 2)
        return None

    def calculate_ev_ebitda(self, market_cap: float, debt: float, cash: float, ebitda: float) -> float:
        """EV/EBITDA = (Market Cap + Debt - Cash) / EBITDA"""
        ev = market_cap + debt - cash
        if ebitda and ebitda > 0:
            return round(ev / ebitda, 2)
        return None

    def estimate_market_cap(self, price: float, shares_outstanding: float) -> float:
        """Капитализация = Цена * Количество акций"""
        return price * shares_outstanding

    def calculate_all_multiples(self, ticker: str) -> pd.DataFrame:
        """Рассчитывает все мультипликаторы для тикера"""

        print(f"\n📊 Расчёт мультипликаторов для {ticker} ({TICKER_TO_COMPANY.get(ticker, 'Неизвестно')})")

        # Загружаем данные о ценах
        price_data = self.load_price_data(ticker)
        if price_data is None or len(price_data) == 0:
            print(f"❌ Нет данных о ценах для {ticker}")
            return None

        # Берём типичные значения (в реальности - из отчётности)
        typical = self.typical_multiples.get(ticker, {})

        # Рассчитываем мультипликаторы для каждой даты
        result_data = []

        for _, row in price_data.iterrows():
            date = row['date']
            price = row['close']

            # Здесь должны быть реальные данные из отчётности
            # Сейчас используем типичные значения как константы
            record = {
                'date': date,
                'ticker': ticker,
                'price': price,
                'pe_ratio': self.calculate_pe_ratio(price, price / typical.get('pe', 5)) if typical.get('pe') else None,
                'pb_ratio': self.calculate_pb_ratio(price, price / typical.get('pb', 1)) if typical.get('pb') else None,
                'ev_ebitda': typical.get('ev_ebitda'),
                'dividend_yield': typical.get('dividend_yield'),
                'market_cap': price * 1e9,  # Заглушка: 1 млрд акций
            }
            result_data.append(record)

        df = pd.DataFrame(result_data)

        # Добавляем скользящие средние
        df['pe_ma20'] = df['pe_ratio'].rolling(20, min_periods=1).mean()
        df['pb_ma20'] = df['pb_ratio'].rolling(20, min_periods=1).mean()

        return df

    def calculate_for_all_tickers(self):
        """Рассчитывает мультипликаторы для всех тикеров"""

        print("\n" + "=" * 70)
        print("🚀 РАСЧЁТ ФУНДАМЕНТАЛЬНЫХ МУЛЬТИПЛИКАТОРОВ")
        print("=" * 70)

        all_results = []

        for ticker in TICKERS:
            df = self.calculate_all_multiples(ticker)
            if df is not None:
                all_results.append(df)

        if all_results:
            # Объединяем все результаты
            final_df = pd.concat(all_results, ignore_index=True)

            # Сохраняем
            output_file = self.output_dir / "fundamental_multiples.csv"
            final_df.to_csv(output_file, index=False, encoding='utf-8')

            print(f"\n✅ Результаты сохранены: {output_file}")
            print(f"   Всего записей: {len(final_df)}")
            print(f"   Период: {final_df['date'].min()} - {final_df['date'].max()}")

            # Статистика по каждому тикеру
            print(f"\n📊 Статистика по тикерам:")
            for ticker in TICKERS:
                ticker_data = final_df[final_df['ticker'] == ticker]
                print(f"\n   {ticker}:")
                print(f"      Записей: {len(ticker_data)}")
                print(f"      Средний P/E: {ticker_data['pe_ratio'].mean():.2f}")
                print(f"      Средний P/B: {ticker_data['pb_ratio'].mean():.2f}")

            return final_df
        else:
            print("❌ Нет данных для расчёта")
            return None


def test_calculator():
    """Тестовая функция"""

    print("\n" + "=" * 70)
    print("🧪 ТЕСТ: Расчёт фундаментальных мультипликаторов")
    print("=" * 70)

    calculator = FundamentalMultiplesCalculator()

    # Тест для SBER
    print("\n🔍 Тест 1: Расчёт для SBER")
    sber_multiples = calculator.calculate_all_multiples('SBER')

    if sber_multiples is not None:
        print(f"\n   Первые 3 записи:")
        print(sber_multiples[['date', 'price', 'pe_ratio', 'pb_ratio']].head(3).to_string())

    # Тест для всех тикеров
    print("\n🔍 Тест 2: Расчёт для всех тикеров")
    all_data = calculator.calculate_for_all_tickers()

    print("\n" + "=" * 70)
    print("✅ Тест завершён!")
    print("=" * 70)

    return all_data is not None


if __name__ == "__main__":
    success = test_calculator()

    if success:
        print("\n🎉 Модуль расчёта мультипликаторов работает!")
        print("   В реальном проекте нужно заменить typical_multiples")
        print("   на данные из отчётности компаний")
    else:
        print("\n⚠️ Что-то пошло не так")