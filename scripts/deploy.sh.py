# scripts/deploy.sh
#!/bin/bash
# Деплой всей системы

set -e

echo "🚀 Starting Stock Analyzer deployment..."

# 1. Проверка окружения
echo "📋 Checking environment..."
command -v docker >/dev/null 2>&1 || { echo "❌ Docker not installed"; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { echo "❌ Docker Compose not installed"; exit 1; }

# 2. Создание директорий
echo "📁 Creating directories..."
mkdir -p data/raw/moex data/lenta_archive data/features models logs pg_backups

# 3. Проверка модели
if [ ! -f "models/Qwen3.6-35B-A3B-UD-Q3_K_M.gguf" ]; then
    echo "⚠️ LLM model not found. Download it first:"
    echo "   hf download unsloth/Qwen3.6-35B-A3B-GGUF --include '*UD-Q3_K_M*' --local-dir models/"
    exit 1
fi

# 4. Билд образов
echo "🔨 Building Docker images..."
docker compose build

# 5. Запуск
echo "🚀 Starting services..."
docker compose up -d

# 6. Проверка
echo "⏳ Waiting for services..."
sleep 10

echo "✅ Services status:"
docker compose ps

echo ""
echo "📊 Services:"
echo "   Streamlit:     http://localhost:8501"
echo "   LLM API:       http://localhost:8001"
echo "   Grafana:       http://localhost:3000"
echo "   MLflow:        http://localhost:5000"
echo ""
echo "📋 Logs:          docker compose logs -f"
echo "🛑 Stop:          docker compose down"