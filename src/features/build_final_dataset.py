# src/features/build_final_dataset.py
import pandas as pd
import numpy as np
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))
from config import RAW_DATA_DIR, FEATURES_DIR, ML_DATASET_DIR


class FinalDatasetBuilder:
    """Собирает финальный датасет для ML"""

    def __init__(self):
        self.moex_file = RAW_DATA_DIR / "moex" / "stocks_detailed.csv"
        self.smartlab_file = FEATURES_DIR / "smartlab_multiples_all.csv"
        self.output_file = ML_DATASET_DIR / "final_dataset.csv"

    def load_moex_data(self):
        """Загружает данные с MOEX"""
        print("📈 Загрузка данных с MOEX...")
        df = pd.read_csv(self.moex_file)
        df['date'] = pd.to_datetime(df['date'])

        # Берём только нужные колонки
        df = df[['date', 'ticker', 'close', 'volume']].copy()
        df = df.rename(columns={'close': 'price', 'volume': 'volume'})

        # Добавляем год и квартал для связывания
        df['year'] = df['date'].dt.year
        df['quarter'] = df['date'].dt.quarter
        df['year_quarter'] = df['date'].dt.year.astype(str) + 'Q' + df['date'].dt.quarter.astype(str)

        print(f"   Загружено {len(df)} записей")
        return df

    def load_smartlab_data(self):
        """Загружает мультипликаторы со Smart-Lab"""
        print("📊 Загрузка мультипликаторов...")
        df = pd.read_csv(self.smartlab_file)

        # Разделяем годовые и квартальные
        df_yearly = df[df['data_type'] == 'yearly'].copy()
        df_quarterly = df[df['data_type'] == 'quarterly'].copy()

        print(f"   Годовых: {len(df_yearly)}")
        print(f"   Квартальных: {len(df_quarterly)}")

        return df_yearly, df_quarterly

    def merge_data(self, prices_df, yearly_df, quarterly_df):
        """Объединяет цены с мультипликаторами"""

        print("\n🔄 Объединение данных...")

        # Сначала присоединяем годовые мультипликаторы
        result = prices_df.copy()

        # Для годовых - связываем по году
        yearly_for_merge = yearly_df.copy()
        yearly_for_merge['year'] = yearly_for_merge['period'].astype(int)

        result = result.merge(
            yearly_for_merge[['ticker', 'year', 'p_e', 'p_bv', 'ev_ebitda',
                              'eps', 'bv_share', 'dividend_yield']],
            on=['ticker', 'year'],
            how='left',
            suffixes=('', '_yearly')
        )

        # Переименовываем годовые колонки
        result = result.rename(columns={
            'p_e': 'pe_yearly',
            'p_bv': 'pb_yearly',
            'ev_ebitda': 'ev_ebitda_yearly',
            'eps': 'eps_yearly',
            'bv_share': 'bv_share_yearly',
            'dividend_yield': 'div_yield_yearly'
        })

        # Для квартальных - связываем по year_quarter
        quarterly_for_merge = quarterly_df.copy()
        quarterly_for_merge = quarterly_for_merge.rename(columns={
            'p_e': 'pe_quarterly',
            'p_bv': 'pb_quarterly',
            'ev_ebitda': 'ev_ebitda_quarterly',
            'eps': 'eps_quarterly',
            'bv_share': 'bv_share_quarterly',
            'dividend_yield': 'div_yield_quarterly'
        })

        result = result.merge(
            quarterly_for_merge[['ticker', 'period', 'pe_quarterly', 'pb_quarterly',
                                 'ev_ebitda_quarterly', 'eps_quarterly', 'bv_share_quarterly',
                                 'div_yield_quarterly']],
            left_on=['ticker', 'year_quarter'],
            right_on=['ticker', 'period'],
            how='left'
        )

        print(f"   Получилось {len(result)} записей")
        return result

    def add_features(self, df):
        """Добавляет дополнительные признаки"""
        print("\n🔧 Добавление признаков...")

        # Сортируем по дате и тикеру
        df = df.sort_values(['ticker', 'date'])

        # Лаговые признаки (предыдущие значения)
        for col in ['price', 'volume']:
            df[f'{col}_lag1'] = df.groupby('ticker')[col].shift(1)
            df[f'{col}_lag7'] = df.groupby('ticker')[col].shift(7)
            df[f'{col}_lag30'] = df.groupby('ticker')[col].shift(30)

        # Скользящие средние
        for col in ['price', 'volume']:
            df[f'{col}_ma5'] = df.groupby('ticker')[col].transform(
                lambda x: x.rolling(5, min_periods=1).mean()
            )
            df[f'{col}_ma20'] = df.groupby('ticker')[col].transform(
                lambda x: x.rolling(20, min_periods=1).mean()
            )

        # Доходность
        df['daily_return'] = df.groupby('ticker')['price'].pct_change()
        df['log_return'] = np.log1p(df['daily_return'])

        # Волатильность (20 дней)
        df['volatility'] = df.groupby('ticker')['daily_return'].transform(
            lambda x: x.rolling(20, min_periods=1).std()
        )

        # Признаки даты
        df['day_of_week'] = df['date'].dt.dayofweek
        df['month'] = df['date'].dt.month
        df['quarter'] = df['date'].dt.quarter
        df['is_month_end'] = df['date'].dt.is_month_end.astype(int)

        print(f"   Добавлено {len([c for c in df.columns if 'lag' in c or 'ma' in c])} новых признаков")
        return df

    def build_dataset(self):
        """Строит финальный датасет"""

        print("\n" + "=" * 70)
        print("🚀 СБОРКА ФИНАЛЬНОГО ДАТАСЕТА")
        print("=" * 70)

        # Загружаем данные
        prices = self.load_moex_data()
        yearly, quarterly = self.load_smartlab_data()

        # Объединяем
        df = self.merge_data(prices, yearly, quarterly)

        # Добавляем признаки
        df = self.add_features(df)

        # Сохраняем
        df.to_csv(self.output_file, index=False, encoding='utf-8')

        print(f"\n✅ Датacет сохранён: {self.output_file}")
        print(f"   Размер: {df.shape[0]} строк × {df.shape[1]} колонок")
        print(f"   Период: {df['date'].min()} - {df['date'].max()}")

        # Статистика по заполненности
        print(f"\n📊 ЗАПОЛНЕННОСТЬ ДАННЫХ:")
        for col in ['pe_yearly', 'pb_yearly', 'ev_ebitda_yearly',
                    'pe_quarterly', 'pb_quarterly', 'ev_ebitda_quarterly']:
            if col in df.columns:
                pct = df[col].notna().mean() * 100
                print(f"   {col}: {pct:.1f}%")

        return df


def main():
    """Основная функция"""
    builder = FinalDatasetBuilder()
    df = builder.build_dataset()

    print("\n" + "=" * 70)
    print("✅ РАБОТА ЗАВЕРШЕНА")
    print("=" * 70)

    # Покажем пример данных
    print("\n📋 Пример данных для Газпрома:")
    gazp_sample = df[df['ticker'] == 'GAZP'].tail(10)[
        ['date', 'price', 'pe_yearly', 'pe_quarterly', 'ev_ebitda_yearly', 'ev_ebitda_quarterly']
    ]
    print(gazp_sample.to_string())


if __name__ == "__main__":
    main()