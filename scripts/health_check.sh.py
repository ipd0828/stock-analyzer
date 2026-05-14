# Скрипт мониторинга здоровья сервисов
# scripts/health_check.sh
#!/bin/bash

echo "🏥 Health Check — $(date)"

# Проверка LLM
if curl -s http://localhost:8001/health > /dev/null 2>&1; then
    echo "✅ LLM server: OK"
else
    echo "❌ LLM server: DOWN"
fi

# Проверка Streamlit
if curl -s http://localhost:8501/_stcore/health > /dev/null 2>&1; then
    echo "✅ Streamlit: OK"
else
    echo "❌ Streamlit: DOWN"
fi

# Проверка PostgreSQL
if docker exec sa-postgres pg_isready -U investor_nick > /dev/null 2>&1; then
    echo "✅ PostgreSQL: OK"
else
    echo "❌ PostgreSQL: DOWN"
fi

# Проверка Grafana
if curl -s http://localhost:3000/api/health > /dev/null 2>&1; then
    echo "✅ Grafana: OK"
else
    echo "❌ Grafana: DOWN"
fi

# Проверка MLflow
if curl -s http://localhost:5000/health > /dev/null 2>&1; then
    echo "✅ MLflow: OK"
else
    echo "❌ MLflow: DOWN"
fi

echo ""