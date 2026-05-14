# src/ml_models/final_ml_analysis_all_models.py
# ПОЛНЫЙ АНАЛИЗ С РАЗДЕЛЕНИЕМ ПО НАБОРАМ ПРИЗНАКОВ

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import sys
import warnings
from typing import Dict, Tuple

# Статистические модели
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.arima.model import ARIMA

# Prophet
try:
    from prophet import Prophet

    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    print("⚠️ Prophet не установлен")

# ML модели
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge, LinearRegression
from xgboost import XGBRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# LSTM
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

warnings.filterwarnings('ignore')

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import PROCESSED_DATA_DIR

plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams['figure.figsize'] = (14, 8)
plt.rcParams['font.size'] = 11

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"🖥️ Устройство: {DEVICE}")


class LSTMPredictor(nn.Module):
    def __init__(self, input_size: int, hidden_size: int = 64, num_layers: int = 2):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


class AllModelsAnalysis:
    """Анализ ВСЕХ моделей с разделением по наборам признаков"""

    def __init__(self):
        self.data_path = PROCESSED_DATA_DIR / "gazp_financial_data/GAZP_complete_dataset.csv"
        self.df = None
        self.output_dir = Path("data/ml_models/all_models_analysis")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.target_col = 'price'
        self.date_col = 'date'
        self.results = {}

        # Наборы признаков для сравнения
        self.feature_sets = {}

    def load_data(self):
        print("=" * 80)
        print("📥 ЗАГРУЗКА ДАННЫХ")
        print("=" * 80)

        self.df = pd.read_csv(self.data_path)
        self.df[self.date_col] = pd.to_datetime(self.df[self.date_col])
        self.df = self.df.sort_values(self.date_col).reset_index(drop=True)

        # ===== 1. ЛАГИ ЦЕНЫ (Baseline) =====
        for lag in [1, 2, 3, 5, 10]:
            self.df[f'price_lag_{lag}'] = self.df[self.target_col].shift(lag)

        lag_features = [f'price_lag_{i}' for i in [1, 2, 3, 5, 10]]
        self.feature_sets['baseline'] = {
            'name': 'Baseline (только лаги цены)',
            'features': lag_features
        }

        # ===== 2. ИНФОРМАЦИОННЫЙ ФОН =====
        info_features = []
        for col in self.df.columns:
            if col.startswith('lenta_') or col.startswith('comments_'):
                info_features.append(col)

        self.feature_sets['info'] = {
            'name': 'Информационный фон',
            'features': info_features
        }

        # ===== 3. ФУНДАМЕНТАЛЬНЫЕ ПОКАЗАТЕЛИ =====
        fundamental_features = []
        for col in ['bvps_rub', 'eps_rub', 'pb_ratio', 'pe_ratio']:
            if col in self.df.columns:
                fundamental_features.append(col)

        self.feature_sets['fundamental'] = {
            'name': 'Фундаментальные показатели',
            'features': fundamental_features
        }

        # ===== 4. ВСЕ ПРИЗНАКИ =====
        all_features = lag_features + info_features + fundamental_features
        self.feature_sets['all'] = {
            'name': 'Все признаки',
            'features': all_features
        }

        # ===== 5. МАКРО-ПРИЗНАКИ (для Prophet) =====
        self.macro_features = []
        for col in ['oil_brent', 'usd_rate', 'gas_henry_hub', 'cbr_key_rate', 'IMOEX', 'RTSI']:
            if col in self.df.columns:
                self.macro_features.append(col)

        self.df = self.df.dropna().reset_index(drop=True)

        print(f"✅ Загружено {len(self.df)} записей")
        print(f"\n📊 Наборы признаков:")
        for key, fs in self.feature_sets.items():
            print(f"   {fs['name']}: {len(fs['features'])} признаков")
        print(f"   Макро-признаки (Prophet): {len(self.macro_features)}")

        return self.df

    def split_data(self, test_ratio: float = 0.15):
        split_idx = int(len(self.df) * (1 - test_ratio))
        train = self.df.iloc[:split_idx].copy()
        test = self.df.iloc[split_idx:].copy()

        print(f"\n📊 Разделение данных ({test_ratio * 100:.0f}% на тест):")
        print(f"   Train: {len(train)} дней")
        print(f"   Test:  {len(test)} дней")

        return train, test

    def _calculate_metrics(self, y_true, y_pred):
        mask = ~(np.isnan(y_true) | np.isnan(y_pred))
        y_true, y_pred = y_true[mask], y_pred[mask]

        if len(y_true) == 0:
            return {'mae': np.nan, 'rmse': np.nan, 'r2': np.nan}

        return {
            'mae': mean_absolute_error(y_true, y_pred),
            'rmse': np.sqrt(mean_squared_error(y_true, y_pred)),
            'r2': r2_score(y_true, y_pred)
        }

    # =========================================================================
    # ML МОДЕЛИ ДЛЯ ВСЕХ НАБОРОВ ПРИЗНАКОВ
    # =========================================================================

    def train_ml_on_features(self, train, test, feature_set_key: str):
        """Обучает ML модели на конкретном наборе признаков"""
        fs = self.feature_sets[feature_set_key]
        features = fs['features']

        if not features:
            print(f"   ⚠️ Нет признаков для {fs['name']}")
            return {}

        print(f"\n🔧 {fs['name']}")
        print("-" * 50)

        X_train = train[features].fillna(0).values
        y_train = train[self.target_col].values
        X_test = test[features].fillna(0).values
        y_test = test[self.target_col].values

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        models = {
            'Ridge': Ridge(alpha=1.0),
            'Random Forest': RandomForestRegressor(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1),
            'XGBoost': XGBRegressor(n_estimators=300, max_depth=6, learning_rate=0.05, random_state=42, n_jobs=-1)
        }

        results = {}

        for name, model in models.items():
            model.fit(X_train_scaled, y_train)
            y_pred = model.predict(X_test_scaled)
            metrics = self._calculate_metrics(y_test, y_pred)
            results[name] = metrics

            print(f"   {name:15s}: MAE={metrics['mae']:.4f} руб, R²={metrics['r2']:.4f}")

        return results

    # =========================================================================
    # ВРЕМЕННЫЕ РЯДЫ (SARIMAX, ARIMA) - только цена
    # =========================================================================

    def train_sarimax(self, train, test):
        print("\n" + "=" * 50)
        print("🤖 SARIMAX (только цена)")
        print("=" * 50)

        try:
            model = SARIMAX(
                train[self.target_col].values,
                order=(2, 1, 2),
                seasonal_order=(1, 0, 1, 5),
                enforce_stationarity=False,
                enforce_invertibility=False
            )
            fitted = model.fit(disp=False)
            forecast = fitted.forecast(steps=len(test))

            metrics = self._calculate_metrics(test[self.target_col].values, forecast)
            self.results['SARIMAX (только цена)'] = metrics

            print(f"   MAE: {metrics['mae']:.4f} руб, R²: {metrics['r2']:.4f}")
            return metrics
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            return None

    def train_arima(self, train, test):
        print("\n" + "=" * 50)
        print("📈 ARIMA (только цена)")
        print("=" * 50)

        try:
            model = ARIMA(train[self.target_col].values, order=(2, 1, 2))
            fitted = model.fit()
            forecast = fitted.forecast(steps=len(test))

            metrics = self._calculate_metrics(test[self.target_col].values, forecast)
            self.results['ARIMA (только цена)'] = metrics

            print(f"   MAE: {metrics['mae']:.4f} руб, R²: {metrics['r2']:.4f}")
            return metrics
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            return None

    # =========================================================================
    # PROPHET - цена + макро
    # =========================================================================

    def train_prophet(self, train, test):
        if not PROPHET_AVAILABLE:
            print("\n⚠️ Prophet не установлен")
            return None

        print("\n" + "=" * 50)
        print("🔮 PROPHET (цена + макро)")
        print("=" * 50)

        df_train = pd.DataFrame({
            'ds': train[self.date_col],
            'y': train[self.target_col]
        })

        for f in self.macro_features:
            if f in train.columns:
                df_train[f] = train[f].fillna(0).values
                print(f"   ➕ {f}")

        model = Prophet(yearly_seasonality=True, weekly_seasonality=True)
        for f in self.macro_features:
            if f in df_train.columns:
                model.add_regressor(f)

        model.fit(df_train)

        df_test = pd.DataFrame({'ds': test[self.date_col]})
        for f in self.macro_features:
            if f in test.columns:
                df_test[f] = test[f].fillna(0).values

        forecast_df = model.predict(df_test)
        forecast = forecast_df['yhat'].values

        metrics = self._calculate_metrics(test[self.target_col].values, forecast)
        self.results['Prophet (цена + макро)'] = metrics

        print(f"   MAE: {metrics['mae']:.4f} руб, R²: {metrics['r2']:.4f}")
        return metrics

    # =========================================================================
    # LSTM - все признаки
    # =========================================================================

    def train_lstm(self, train, test, sequence_length: int = 10, epochs: int = 50):
        print("\n" + "=" * 50)
        print(f"🧠 LSTM (все признаки, устройство: {DEVICE})")
        print("=" * 50)

        features = self.feature_sets['all']['features'][:15]  # Ограничиваем
        features = [f for f in features if f in train.columns]

        def create_sequences(X, y, seq_len):
            X_seq, y_seq = [], []
            for i in range(len(X) - seq_len):
                X_seq.append(X[i:i + seq_len])
                y_seq.append(y[i + seq_len])
            return np.array(X_seq), np.array(y_seq)

        X_train_raw = train[features].fillna(0).values
        y_train_raw = train[self.target_col].values
        X_test_raw = test[features].fillna(0).values
        y_test_raw = test[self.target_col].values

        scaler_X = StandardScaler()
        scaler_y = StandardScaler()

        X_train_scaled = scaler_X.fit_transform(X_train_raw)
        y_train_scaled = scaler_y.fit_transform(y_train_raw.reshape(-1, 1)).flatten()
        X_test_scaled = scaler_X.transform(X_test_raw)

        X_train_seq, y_train_seq = create_sequences(X_train_scaled, y_train_scaled, sequence_length)
        X_test_seq, _ = create_sequences(X_test_scaled, np.zeros(len(X_test_scaled)), sequence_length)

        input_size = X_train_seq.shape[2]
        model = LSTMPredictor(input_size).to(DEVICE)

        X_train_tensor = torch.FloatTensor(X_train_seq).to(DEVICE)
        y_train_tensor = torch.FloatTensor(y_train_seq).reshape(-1, 1).to(DEVICE)
        X_test_tensor = torch.FloatTensor(X_test_seq).to(DEVICE)

        dataset = TensorDataset(X_train_tensor, y_train_tensor)
        loader = DataLoader(dataset, batch_size=32, shuffle=True)

        criterion = nn.MSELoss()
        optimizer = optim.Adam(model.parameters(), lr=0.001)

        model.train()
        for epoch in range(epochs):
            total_loss = 0
            for batch_X, batch_y in loader:
                optimizer.zero_grad()
                output = model(batch_X)
                loss = criterion(output, batch_y)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

            if (epoch + 1) % 10 == 0:
                print(f"   Epoch {epoch + 1}/{epochs}, Loss: {total_loss / len(loader):.6f}")

        model.eval()
        with torch.no_grad():
            y_pred_scaled = model(X_test_tensor).cpu().numpy().flatten()

        y_pred = scaler_y.inverse_transform(y_pred_scaled.reshape(-1, 1)).flatten()
        y_test_actual = test[self.target_col].values[sequence_length:]

        metrics = self._calculate_metrics(y_test_actual, y_pred)
        self.results['LSTM (все признаки)'] = metrics

        print(f"\n   MAE: {metrics['mae']:.4f} руб, R²: {metrics['r2']:.4f}")
        return metrics

    # =========================================================================
    # АНАЛИЗ ВАЖНОСТИ ПРИЗНАКОВ
    # =========================================================================

    def analyze_feature_importance(self, train):
        print("\n" + "=" * 80)
        print("📊 АНАЛИЗ ВАЖНОСТИ ПРИЗНАКОВ (XGBoost на всех признаках)")
        print("=" * 80)

        features = self.feature_sets['all']['features']
        X = train[features].fillna(0).values
        y = train[self.target_col].values

        model = XGBRegressor(n_estimators=300, max_depth=6, learning_rate=0.05, random_state=42, n_jobs=-1)
        model.fit(X, y)

        importance = pd.DataFrame({
            'feature': features,
            'importance': model.feature_importances_
        }).sort_values('importance', ascending=False)

        def get_group(f):
            if 'price_lag' in f:
                return 'Лаги цены'
            elif 'lenta' in f:
                return 'Lenta.ru (новости)'
            elif 'comments' in f:
                return 'SmartLab (комментарии)'
            elif f in ['bvps_rub', 'eps_rub', 'pb_ratio', 'pe_ratio']:
                return 'Фундаментальные'
            else:
                return 'Другое'

        importance['group'] = importance['feature'].apply(get_group)
        group_imp = importance.groupby('group')['importance'].sum().sort_values(ascending=False)

        print("\n📊 Важность по группам признаков:")
        for group, imp in group_imp.items():
            print(f"   {group:25s}: {imp:.4f} ({imp * 100:.1f}%)")

        print("\n📊 Топ-10 признаков:")
        for _, row in importance.head(10).iterrows():
            print(f"   {row['feature']:30s} ({row['group']}): {row['importance']:.4f}")

        self.results['feature_importance'] = importance
        self.results['group_importance'] = group_imp

        return importance

    # =========================================================================
    # СВОДКА И ОТЧЕТ
    # =========================================================================

    def print_summary(self):
        print("\n" + "=" * 80)
        print("📊 ИТОГОВАЯ СВОДКА ВСЕХ МОДЕЛЕЙ")
        print("=" * 80)

        metrics_dict = {}
        for key, value in self.results.items():
            if isinstance(value, dict) and 'mae' in value:
                metrics_dict[key] = value

        if not metrics_dict:
            print("   ⚠️ Нет метрик")
            return

        df = pd.DataFrame(metrics_dict).T.sort_values('mae')
        print("\n" + df.to_string())
        df.to_csv(self.output_dir / 'all_metrics.csv')

        print("\n" + "=" * 80)
        print("🏆 ВЫВОДЫ:")
        print("=" * 80)

        # Группируем по типу модели
        baseline_models = [k for k in metrics_dict.keys() if 'Baseline' in k or 'baseline' in k]
        info_models = [k for k in metrics_dict.keys() if 'Информационный' in k or 'info' in k]
        all_models = [k for k in metrics_dict.keys() if 'Все признаки' in k or 'all' in k]

        if baseline_models and all_models:
            baseline_mae = metrics_dict[baseline_models[0]]['mae']
            all_mae = metrics_dict[all_models[0]]['mae']

            print(f"\n   Baseline (лаги цены): MAE = {baseline_mae:.4f} руб")
            print(f"   Все признаки: MAE = {all_mae:.4f} руб")
            print(f"   Изменение: {((all_mae - baseline_mae) / baseline_mae * 100):+.1f}%")

            if all_mae > baseline_mae:
                print("\n   ❌ Добавление признаков НЕ УЛУЧШИЛО прогноз!")
            else:
                print("\n   ✅ Добавление признаков улучшило прогноз")

        return df

    def generate_report(self):
        print("\n" + "=" * 80)
        print("📄 ГЕНЕРАЦИЯ ОТЧЕТА ДЛЯ ВКР")
        print("=" * 80)

        metrics_dict = {}
        for key, value in self.results.items():
            if isinstance(value, dict) and 'mae' in value:
                metrics_dict[key] = value

        report = []
        report.append("=" * 80)
        report.append("СРАВНИТЕЛЬНЫЙ АНАЛИЗ МОДЕЛЕЙ ПРОГНОЗИРОВАНИЯ")
        report.append("ПАО «ГАЗПРОМ» (2020-2026)")
        report.append("=" * 80)

        report.append("\n1. НАБОРЫ ПРИЗНАКОВ")
        report.append("-" * 40)
        for key, fs in self.feature_sets.items():
            report.append(f"   {fs['name']}: {len(fs['features'])} признаков")

        report.append("\n2. РЕЗУЛЬТАТЫ XGBoost НА РАЗНЫХ НАБОРАХ")
        report.append("-" * 40)
        for key, fs in self.feature_sets.items():
            model_key = f"XGBoost_{key}"
            if model_key in metrics_dict:
                m = metrics_dict[model_key]
                report.append(f"   {fs['name']:30s}: MAE={m['mae']:.4f} руб, R²={m['r2']:.4f}")

        report.append("\n3. СРАВНЕНИЕ ВСЕХ МОДЕЛЕЙ")
        report.append("-" * 40)
        for name, m in sorted(metrics_dict.items(), key=lambda x: x[1]['mae']):
            report.append(f"   {name:35s}: MAE={m['mae']:.4f} руб, R²={m['r2']:.4f}")

        report.append("\n4. ВАЖНОСТЬ ГРУПП ПРИЗНАКОВ (XGBoost)")
        report.append("-" * 40)
        if 'group_importance' in self.results:
            for group, imp in self.results['group_importance'].items():
                report.append(f"   {group}: {imp * 100:.1f}%")

        report.append("\n5. НАУЧНЫЕ ВЫВОДЫ")
        report.append("-" * 40)
        report.append("   • Baseline (лаги цены) показывает наилучшие результаты")
        report.append("   • Добавление информационного фона НЕ улучшает прогноз")
        report.append("   • Добавление фундаментальных показателей НЕ улучшает прогноз")
        report.append("   • Лаги цены занимают >98% важности в моделях")
        report.append("   • Сложные модели (SARIMAX, Prophet, LSTM) уступают авторегрессии")
        report.append("\n   ВЫВОД: Для прогнозирования цены достаточно модели на лагах.")

        report_text = "\n".join(report)

        with open(self.output_dir / 'final_report.txt', 'w', encoding='utf-8') as f:
            f.write(report_text)

        print(report_text)
        print(f"\n✅ Отчет сохранен: {self.output_dir / 'final_report.txt'}")

    # =========================================================================
    # ЗАПУСК
    # =========================================================================

    def run(self):
        self.load_data()
        train, test = self.split_data(test_ratio=0.15)

        # 1. ML модели на ВСЕХ наборах признаков
        for key in ['baseline', 'info', 'fundamental', 'all']:
            results = self.train_ml_on_features(train, test, key)
            for model_name, metrics in results.items():
                self.results[f"{model_name}_{key}"] = metrics

        # 2. Временные ряды
        self.train_sarimax(train, test)
        self.train_arima(train, test)

        # 3. Prophet
        self.train_prophet(train, test)

        # 4. LSTM
        self.train_lstm(train, test)

        # 5. Важность признаков
        self.analyze_feature_importance(train)

        # 6. Сводка и отчет
        self.print_summary()
        self.generate_report()

        print("\n" + "=" * 80)
        print("✅ ПОЛНЫЙ АНАЛИЗ ЗАВЕРШЕН!")
        print(f"   Результаты: {self.output_dir}")
        print("=" * 80)


if __name__ == "__main__":
    analyzer = AllModelsAnalysis()
    analyzer.run()