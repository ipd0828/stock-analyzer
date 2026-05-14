# scripts/model_registry.py
"""
Реестр моделей с версионированием
"""

import json
from pathlib import Path
from datetime import datetime
import pickle
import pandas as pd

MODEL_REGISTRY = Path("models/registry")


class ModelRegistry:
    """Управление версиями моделей"""

    def __init__(self):
        MODEL_REGISTRY.mkdir(parents=True, exist_ok=True)
        self.registry_file = MODEL_REGISTRY / "registry.json"
        self.registry = self._load()

    def _load(self):
        if self.registry_file.exists():
            with open(self.registry_file) as f:
                return json.load(f)
        return {"models": {}, "latest": {}}

    def _save(self):
        with open(self.registry_file, 'w') as f:
            json.dump(self.registry, f, indent=2)

    def register(self, ticker: str, model_type: str, model, metrics: dict):
        """Регистрирует новую версию модели"""
        version = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_key = f"{ticker}_{model_type}"

        # Сохраняем модель
        model_dir = MODEL_REGISTRY / model_key / version
        model_dir.mkdir(parents=True, exist_ok=True)

        with open(model_dir / "model.pkl", 'wb') as f:
            pickle.dump(model, f)

        # Сохраняем метрики
        with open(model_dir / "metrics.json", 'w') as f:
            json.dump(metrics, f, indent=2)

        # Обновляем реестр
        if model_key not in self.registry['models']:
            self.registry['models'][model_key] = []

        self.registry['models'][model_key].append({
            'version': version,
            'timestamp': datetime.now().isoformat(),
            'metrics': metrics
        })

        self.registry['latest'][model_key] = version
        self._save()

        print(f"✅ Registered {model_key} v{version}")
        print(f"   MAE: {metrics.get('mae_close', 'N/A'):.4f}")

    def load_latest(self, ticker: str, model_type: str):
        """Загружает последнюю версию модели"""
        model_key = f"{ticker}_{model_type}"

        if model_key not in self.registry['latest']:
            return None

        version = self.registry['latest'][model_key]
        model_path = MODEL_REGISTRY / model_key / version / "model.pkl"

        if model_path.exists():
            with open(model_path, 'rb') as f:
                return pickle.load(f)

        return None

    def get_history(self, ticker: str, model_type: str):
        """Возвращает историю метрик модели"""
        model_key = f"{ticker}_{model_type}"
        if model_key in self.registry['models']:
            return pd.DataFrame(self.registry['models'][model_key])
        return pd.DataFrame()

    def promote_to_production(self, ticker: str, model_type: str, version: str):
        """Промоутит версию в production"""
        model_key = f"{ticker}_{model_type}"

        if model_key not in self.registry['models']:
            return False

        # Проверяем что версия существует
        versions = [m['version'] for m in self.registry['models'][model_key]]
        if version not in versions:
            return False

        # Проверяем качество (R² > 0.85)
        model_info = self.registry['models'][model_key][versions.index(version)]
        r2 = model_info['metrics'].get('r2_close', 0)

        if r2 < 0.85:
            print(f"⚠️ Cannot promote: R² = {r2:.4f} < 0.85")
            return False

        self.registry['latest'][model_key] = version
        self._save()

        print(f"✅ Promoted {model_key} v{version} to production")
        return True


# CLI для управления моделями
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Model Registry CLI")
    parser.add_argument('action', choices=['list', 'promote', 'compare'])
    parser.add_argument('--ticker', default='GAZP')
    parser.add_argument('--model', default='Ridge')

    args = parser.parse_args()

    registry = ModelRegistry()

    if args.action == 'list':
        model_key = f"{args.ticker}_{args.model}"
        history = registry.get_history(args.ticker, args.model)
        if len(history) > 0:
            print(f"\n{model_key} versions:")
            print(history[['version', 'timestamp', 'metrics']].to_string())
        else:
            print(f"No versions for {model_key}")

    elif args.action == 'compare':
        history = registry.get_history(args.ticker, args.model)
        if len(history) > 1:
            latest = history.iloc[-1]
            prev = history.iloc[-2]
            mae_change = (latest['metrics']['mae_close'] - prev['metrics']['mae_close']) / prev['metrics'][
                'mae_close'] * 100
            r2_change = latest['metrics']['r2_close'] - prev['metrics']['r2_close']
            print(f"\n{args.ticker} {args.model}:")
            print(
                f"  MAE: {prev['metrics']['mae_close']:.4f} → {latest['metrics']['mae_close']:.4f} ({mae_change:+.1f}%)")
            print(f"  R²:  {prev['metrics']['r2_close']:.4f} → {latest['metrics']['r2_close']:.4f} ({r2_change:+.4f})")