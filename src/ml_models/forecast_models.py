# src/ml_models/forecast_models.py
# Предсказание на 1 день вперед (t+1)

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import sys
import warnings
from typing import Dict, Tuple, Optional

from statsmodels.tsa.statespace.sarimax import SARIMAX

try:
    from prophet import Prophet

    PROPHET_AVAILABLE = True
    print("✅ Prophet установлен")
except ImportError:
    PROPHET_AVAILABLE = False
    print("⚠️ Prophet не установлен")

from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge, LinearRegression
from xgboost import XGBRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

warnings.filterwarnings('ignore')

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import PROCESSED_DATA_DIR

plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams['figure.figsize'] = (14, 8)

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"🖥️ Используется устройство: {DEVICE}")


class LSTMPredictor(nn.Module):
    def __init__(self, input_size: int, hidden_size: int = 128, num_layers: int = 3, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=dropout)
        self.fc1 = nn.Linear(hidden_size, 32)
        self.fc2 = nn.Linear(32, 1)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        out = lstm_out[:, -1, :]
        out = self.relu(self.fc1(out))
        out = self.dropout(out)
        out = self.fc2(out)
        return out


class ForecastModels:
    """Предсказание на 1 день вперед (t+1)"""

    def __init__(self, data_path: Optional[Path] = None):
        if data_path is None:
            data_path = PROCESSED_DATA_DIR / "gazp_financial_data/GAZP_complete_dataset.csv"

        self.data_path = data_path
        self.df = None
        self.target_col = 'price'
        self.date_col = 'date'

        # Информационные признаки
        self.info_features = {
            'comments': ['comments_negative', 'comments_positive', 'comments_news',
                         'comments_price', 'comments_dividends', 'comments_total'],
            'lenta': ['lenta_war', 'lenta_negative', 'lenta_sanctions', 'lenta_total',
                      'lenta_political', 'lenta_market'],
            'volume': ['volume']
        }

        # Макро-признаки для Prophet
        self.macro_features = ['oil_brent', 'gas_henry_hub', 'usd_rate', 'cbr_key_rate',
                               'IMOEX', 'RTSI', 'MOEXOG']

        # Лаги для ML моделей
        self.info_lags = [1, 2, 3]

        self.output_dir = Path("data/ml_models/forecasts")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.models = {}
        self.metrics = {}
        self.forecasts = {}

        self.info_feature_names = []
        self.lstm_feature_names = []
        self.feature_groups_map = {}

    def load_and_prepare_data(self) -> pd.DataFrame:
        print("=" * 80)
        print("📥 ЗАГРУЗКА ДАННЫХ")
        print("=" * 80)

        self.df = pd.read_csv(self.data_path)
        self.df[self.date_col] = pd.to_datetime(self.df[self.date_col])
        self.df = self.df.sort_values(self.date_col).reset_index(drop=True)

        # Оставляем только существующие признаки
        for group in self.info_features:
            self.info_features[group] = [f for f in self.info_features[group] if f in self.df.columns]
        self.macro_features = [f for f in self.macro_features if f in self.df.columns]

        print(f"\n✅ Загружено {len(self.df)} записей")

        # Заполняем пропуски
        all_features = []
        for group_features in self.info_features.values():
            all_features.extend(group_features)
        all_features.extend(self.macro_features)

        for col in all_features + [self.target_col]:
            if col in self.df.columns:
                self.df[col] = self.df[col].fillna(method='ffill').fillna(method='bfill')

        # ===== ВАЖНО: целевая переменная = цена ЗАВТРА =====
        self.df['target_next_day'] = self.df[self.target_col].shift(-1)

        # ===== ПРИЗНАКИ ДЛЯ LSTM (без лагов) =====
        self.lstm_feature_names = []
        for group, features in self.info_features.items():
            for f in features:
                if f in self.df.columns:
                    self.lstm_feature_names.append(f)
        for f in self.macro_features:
            if f in self.df.columns:
                self.lstm_feature_names.append(f)

        # ===== ПРИЗНАКИ ДЛЯ ML (с лагами) =====
        self.info_feature_names = []
        self.feature_groups_map = {}

        for group, features in self.info_features.items():
            for feature in features:
                if feature in self.df.columns:
                    self.info_feature_names.append(feature)
                    self.feature_groups_map[feature] = group

                    for lag in self.info_lags:
                        lag_name = f'{feature}_lag_{lag}'
                        self.df[lag_name] = self.df[feature].shift(lag)
                        self.info_feature_names.append(lag_name)
                        self.feature_groups_map[lag_name] = group

        # Временные признаки
        self.df['month'] = self.df[self.date_col].dt.month
        self.df['dayofweek'] = self.df[self.date_col].dt.dayofweek
        self.info_feature_names.extend(['month', 'dayofweek'])
        self.lstm_feature_names.extend(['month', 'dayofweek'])

        # Лаги цены для baseline
        for lag in range(1, 31):
            self.df[f'price_lag_{lag}'] = self.df[self.target_col].shift(lag)

        # Удаляем последнюю строку (нет целевой переменной)
        self.df = self.df.dropna().reset_index(drop=True)

        print(f"✅ После обработки: {len(self.df)} записей")
        print(f"   Целевая переменная: цена ЗАВТРАШНЕГО дня")

        return self.df

    def split_data(self, test_ratio: float = 0.05) -> Tuple[pd.DataFrame, pd.DataFrame]:
        split_idx = int(len(self.df) * (1 - test_ratio))
        train = self.df.iloc[:split_idx].copy()
        test = self.df.iloc[split_idx:].copy()

        print(f"\n📊 Разделение ({test_ratio * 100:.0f}% на тест):")
        print(f"   Обучение: {len(train)} дней")
        print(f"   Тест: {len(test)} дней")

        return train, test

    def _calculate_metrics(self, y_true: np.ndarray, y_pred: np.ndarray) -> Dict:
        mask = ~(np.isnan(y_true) | np.isnan(y_pred))
        y_true, y_pred = y_true[mask], y_pred[mask]

        if len(y_true) == 0:
            return {'mae': np.nan, 'rmse': np.nan, 'r2': np.nan, 'direction_accuracy': np.nan}

        # Direction: сравниваем с СЕГОДНЯШНЕЙ ценой (которая известна)
        # Нам нужно предсказать: будет ли цена завтра ВЫШЕ или НИЖЕ сегодняшней

        return {
            'mae': mean_absolute_error(y_true, y_pred),
            'rmse': np.sqrt(mean_squared_error(y_true, y_pred)),
            'r2': r2_score(y_true, y_pred),
        }

    # =========================================================================
    # BASELINE - предсказание ЗАВТРАШНЕЙ цены
    # =========================================================================

    def train_baseline(self, train: pd.DataFrame, test: pd.DataFrame) -> Dict:
        print("\n" + "=" * 80)
        print("📊 BASELINE (30 лагов цены → цена завтра)")
        print("=" * 80)

        lag_features = [f'price_lag_{i}' for i in range(1, 31)]

        X_train = train[lag_features].values
        y_train = train['target_next_day'].values
        X_test = test[lag_features].values
        y_test = test['target_next_day'].values

        model = LinearRegression()
        model.fit(X_train, y_train)
        self.models['baseline'] = model

        y_pred = model.predict(X_test)

        # Direction Accuracy: сравниваем предсказанную цену завтра с СЕГОДНЯШНЕЙ ценой
        today_price = test[self.target_col].values
        dir_true = (y_test > today_price).astype(int)
        dir_pred = (y_pred > today_price).astype(int)
        dir_acc = np.mean(dir_true == dir_pred) * 100

        self.forecasts['baseline'] = pd.DataFrame({
            'date': test[self.date_col],
            'today': today_price,
            'actual_tomorrow': y_test,
            'predicted_tomorrow': y_pred,
            'direction_correct': dir_true == dir_pred
        })

        metrics = self._calculate_metrics(y_test, y_pred)
        metrics['direction_accuracy'] = dir_acc
        self.metrics['baseline'] = metrics

        print(f"   MAE: {metrics['mae']:.4f} руб")
        print(f"   RMSE: {metrics['rmse']:.4f} руб")
        print(f"   R²: {metrics['r2']:.4f}")
        print(f"   Direction Accuracy: {dir_acc:.1f}%")

        return {'metrics': metrics}

    # =========================================================================
    # PROPHET - предсказание завтрашней цены
    # =========================================================================

    def train_prophet(self, train: pd.DataFrame, test: pd.DataFrame) -> Dict:
        if not PROPHET_AVAILABLE:
            print("\n⚠️ Prophet не установлен - пропускаем")
            return None

        print("\n" + "=" * 80)
        print("🔮 PROPHET (с макро-признаками → цена завтра)")
        print("=" * 80)

        df_train = pd.DataFrame({
            'ds': train[self.date_col],
            'y': train['target_next_day']  # ВАЖНО: предсказываем завтрашнюю цену!
        })

        for f in self.macro_features:
            if f in train.columns:
                df_train[f] = train[f].fillna(0).values

        model = Prophet(yearly_seasonality=True, weekly_seasonality=True)
        for f in self.macro_features:
            if f in df_train.columns:
                model.add_regressor(f)

        model.fit(df_train)
        self.models['prophet'] = model

        df_test = pd.DataFrame({'ds': test[self.date_col]})
        for f in self.macro_features:
            if f in test.columns:
                df_test[f] = test[f].fillna(0).values

        forecast_df = model.predict(df_test)
        y_pred = forecast_df['yhat'].values
        y_test = test['target_next_day'].values
        today_price = test[self.target_col].values

        dir_true = (y_test > today_price).astype(int)
        dir_pred = (y_pred > today_price).astype(int)
        dir_acc = np.mean(dir_true == dir_pred) * 100

        self.forecasts['prophet'] = pd.DataFrame({
            'date': test[self.date_col],
            'today': today_price,
            'actual_tomorrow': y_test,
            'predicted_tomorrow': y_pred,
            'direction_correct': dir_true == dir_pred
        })

        metrics = self._calculate_metrics(y_test, y_pred)
        metrics['direction_accuracy'] = dir_acc
        self.metrics['prophet'] = metrics

        print(f"   MAE: {metrics['mae']:.4f} руб")
        print(f"   Direction Accuracy: {dir_acc:.1f}%")

        return {'metrics': metrics}

    # =========================================================================
    # ML МОДЕЛИ
    # =========================================================================

    def train_ml_models(self, train: pd.DataFrame, test: pd.DataFrame) -> Dict:
        print("\n" + "=" * 80)
        print("🌲 ML МОДЕЛИ (информационные признаки → цена завтра)")
        print("=" * 80)

        X_train = train[self.info_feature_names].fillna(0).values
        y_train = train['target_next_day'].values
        X_test = test[self.info_feature_names].fillna(0).values
        y_test = test['target_next_day'].values
        today_price = test[self.target_col].values

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        models = {
            'random_forest': RandomForestRegressor(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1),
            'xgboost': XGBRegressor(n_estimators=300, max_depth=6, learning_rate=0.05, random_state=42, n_jobs=-1)
        }

        results = {}

        for name, model in models.items():
            print(f"\n🔧 {name.upper()}...")

            model.fit(X_train_scaled, y_train)
            self.models[name] = model

            y_pred = model.predict(X_test_scaled)

            dir_true = (y_test > today_price).astype(int)
            dir_pred = (y_pred > today_price).astype(int)
            dir_acc = np.mean(dir_true == dir_pred) * 100

            self.forecasts[name] = pd.DataFrame({
                'date': test[self.date_col],
                'today': today_price,
                'actual_tomorrow': y_test,
                'predicted_tomorrow': y_pred,
                'direction_correct': dir_true == dir_pred
            })

            metrics = self._calculate_metrics(y_test, y_pred)
            metrics['direction_accuracy'] = dir_acc
            self.metrics[name] = metrics

            print(f"   MAE: {metrics['mae']:.4f} руб, Direction: {dir_acc:.1f}%")

            if name == 'xgboost':
                importance = pd.DataFrame({
                    'feature': self.info_feature_names,
                    'importance': model.feature_importances_,
                    'group': [self.feature_groups_map.get(f, 'other') for f in self.info_feature_names]
                }).sort_values('importance', ascending=False)

                print(f"\n   📊 Топ-5 важных признаков:")
                for _, row in importance.head(5).iterrows():
                    print(f"      {row['feature']} ({row['group']}): {row['importance']:.4f}")

                group_imp = importance.groupby('group')['importance'].sum()
                print(f"\n   📊 Важность по группам:")
                for group, imp in group_imp.items():
                    print(f"      {group}: {imp:.4f} ({imp * 100:.1f}%)")

                self.output_dir.mkdir(parents=True, exist_ok=True)
                importance.to_csv(self.output_dir / 'xgboost_importance.csv', index=False)

            results[name] = {'metrics': metrics}

        return results

    # =========================================================================
    # СВОДКА
    # =========================================================================

    def print_summary(self):
        """Выводит сводку: кто лучше предсказывает следующий день"""
        print("\n" + "=" * 80)
        print("📊 ИТОГОВАЯ СВОДКА: КТО ЛУЧШЕ ПРЕДСКАЗЫВАЕТ СЛЕДУЮЩИЙ ДЕНЬ?")
        print("=" * 80)

        if not self.metrics:
            return

        # Собираем результаты
        results = []
        for name, m in self.metrics.items():
            results.append({
                'model': name,
                'mae': m['mae'],
                'direction_accuracy': m.get('direction_accuracy', 0)
            })

        df = pd.DataFrame(results).sort_values('mae')

        print("\n📊 По точности прогноза цены (MAE, руб):")
        for _, row in df.iterrows():
            print(f"   {row['model']:15s}: MAE = {row['mae']:.4f} руб")

        df_dir = df.sort_values('direction_accuracy', ascending=False)
        print("\n📈 По точности предсказания направления (рост/падение):")
        for _, row in df_dir.iterrows():
            print(f"   {row['model']:15s}: Direction = {row['direction_accuracy']:.1f}%")

        # Определяем победителя
        best_mae = df.iloc[0]['model']
        best_dir = df_dir.iloc[0]['model']

        print("\n" + "=" * 80)
        print(f"🏆 Лучший прогноз цены: {best_mae}")
        print(f"🏆 Лучшее предсказание направления: {best_dir}")
        print("=" * 80)

        # Сохраняем
        df.to_csv(self.output_dir / 'next_day_prediction_results.csv', index=False)

    # =========================================================================
    # ЗАПУСК
    # =========================================================================

    def run_all(self, test_ratio: float = 0.05):
        print("\n" + "=" * 80)
        print("🚀 ПРЕДСКАЗАНИЕ СЛЕДУЮЩЕГО ДНЯ (t+1)")
        print(f"   Тест: {test_ratio * 100:.0f}% последних данных")
        print("=" * 80)

        self.load_and_prepare_data()
        train, test = self.split_data(test_ratio=test_ratio)

        self.train_baseline(train, test)
        self.train_prophet(train, test)
        self.train_ml_models(train, test)

        self.print_summary()

        print("\n✅ ГОТОВО!")
        return self.metrics


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test-ratio', type=float, default=0.05)
    args = parser.parse_args()

    forecaster = ForecastModels()
    forecaster.run_all(test_ratio=args.test_ratio)


if __name__ == "__main__":
    main()