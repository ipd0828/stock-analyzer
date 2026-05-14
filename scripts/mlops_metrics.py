# scripts/mlops_metrics.py
"""
MLOps: логирование метрик модели в MLflow
"""

import mlflow
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json

MLFLOW_TRACKING_URI = "http://localhost:5000"
EXPERIMENT_NAME = "stock_analyzer"

mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
mlflow.set_experiment(EXPERIMENT_NAME)


def log_model_metrics(ticker: str, model_name: str, metrics: dict,
                      features: list, dataset_info: dict):
    """Логирует метрики модели в MLflow"""

    with mlflow.start_run(run_name=f"{ticker}_{model_name}_{datetime.now().strftime('%Y%m%d_%H%M')}"):
        # Параметры
        mlflow.log_param("ticker", ticker)
        mlflow.log_param("model", model_name)
        mlflow.log_param("train_size", metrics.get('train_size', 0))
        mlflow.log_param("test_size", metrics.get('test_size', 0))
        mlflow.log_param("features_count", len(features))

        # Метрики
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                mlflow.log_metric(key, value)

        # Тэги
        mlflow.set_tag("dataset_version", dataset_info.get('version', 'unknown'))
        mlflow.set_tag("data_period", f"{dataset_info.get('start_date')}_{dataset_info.get('end_date')}")

        # Артефакты
        features_df = pd.DataFrame({'feature': features})
        features_df.to_csv("features.csv", index=False)
        mlflow.log_artifact("features.csv")


def log_prediction_quality(ticker: str, y_true: np.array, y_pred: np.array,
                           model_name: str = "Ridge"):
    """Логирует качество предсказания"""
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)

    # Алерт при деградации
    if r2 < 0.85:
        print(f"⚠️ ALERT: {ticker} {model_name} R² dropped to {r2:.4f}")

    return {'mae': mae, 'rmse': rmse, 'r2': r2}


def monitor_data_drift(reference_df: pd.DataFrame, current_df: pd.DataFrame,
                       threshold: float = 0.1):
    """
    Мониторинг дрейфа данных через PSI (Population Stability Index)
    """
    psi_values = {}

    for col in reference_df.select_dtypes(include=[np.number]).columns:
        if col in current_df.columns:
            # Разбиваем на 10 бинов
            ref_hist = np.histogram(reference_df[col].dropna(), bins=10)[0]
            cur_hist = np.histogram(current_df[col].dropna(), bins=10)[0]

            # Нормализуем
            ref_dist = ref_hist / ref_hist.sum()
            cur_dist = cur_hist / cur_hist.sum()

            # PSI
            psi = np.sum((cur_dist - ref_dist) * np.log((cur_dist + 1e-10) / (ref_dist + 1e-10)))
            psi_values[col] = psi

            if psi > threshold:
                print(f"⚠️ DRIFT: {col} PSI={psi:.4f}")

    return psi_values