#!/bin/bash
# src/llama_classifier/start_server.sh

cd ~/PycharmProjects/stockanalyser_2/llama.cpp

./build/bin/llama-server \
    -m /home/ipd0828-777/PycharmProjects/stockanalyser_2/unsloth/Qwen3.5-9B-GGUF/Qwen3.5-9B-UD-Q6_K_XL.gguf \
    --host 127.0.0.1 \
    --port 8001 \
    -t 8 \
    -ngl 99 \
    --ctx-size 8192

echo "✅ Сервер запущен на http://127.0.0.1:8001"