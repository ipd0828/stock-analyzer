#!/bin/bash
# run_pipeline.sh
# Запуск LLM-сервера + Docker Compose

set -e

echo "🚀 Starting Stock Analyzer Pipeline..."

# 1. Проверка модели
if [ ! -f "Qwen3.6-35B-A3B-UD-Q3_K_M.gguf" ]; then
    if [ -f "models/Qwen3.6-35B-A3B-UD-Q3_K_M.gguf" ]; then
        MODEL_PATH="models/Qwen3.6-35B-A3B-UD-Q3_K_M.gguf"
    else
        echo "❌ Model not found! Put it in ./models/"
        exit 1
    fi
else
    MODEL_PATH="Qwen3.6-35B-A3B-UD-Q3_K_M.gguf"
fi

# 2. Запуск LLM-сервера (в фоне)
echo "🧠 Starting LLM server..."
./llama.cpp/build/bin/llama-server \
    -m "$MODEL_PATH" \
    -ngl 30 \
    -c 8192 \
    --host 0.0.0.0 \
    --port 8001 \
    --chat-template-kwargs '{"enable_thinking":false}' \
    --embeddings &
LLM_PID=$!
echo "   LLM PID: $LLM_PID"

# Ждём готовности
echo "⏳ Waiting for LLM server..."
for i in {1..30}; do
    if curl -s http://localhost:8001/health > /dev/null 2>&1; then
        echo "✅ LLM server ready"
        break
    fi
    sleep 2
done

# 3. Запуск Docker Compose
echo "🐳 Starting Docker services..."
docker compose up -d

# 4. Статус
echo ""
echo "✅ Pipeline запущен!"
echo ""
echo "📊 Services:"
echo "   LLM Server:   http://localhost:8001 (PID: $LLM_PID)"
echo "   Streamlit:    http://localhost:8501"
echo "   PostgreSQL:   localhost:5432"
echo "   Grafana:      http://localhost:3000 (admin/${GRAFANA_PASSWORD:-admin})"
echo "   MLflow:       http://localhost:5000"
echo "   Prometheus:   http://localhost:9090"
echo ""
echo "📋 Остановка:"
echo "   kill $LLM_PID && docker compose down"
echo ""

# Ждём Ctrl+C
trap "echo '🛑 Stopping...'; kill $LLM_PID; docker compose down; exit 0" SIGINT SIGTERM
wait $LLM_PID