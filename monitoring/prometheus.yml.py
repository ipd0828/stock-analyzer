# monitoring/prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'streamlit'
    static_configs:
      - targets: ['streamlit:8501']
    metrics_path: '/_stcore/metrics'

  - job_name: 'llm-server'
    static_configs:
      - targets: ['llm:8001']
    metrics_path: '/health'

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres:5432']