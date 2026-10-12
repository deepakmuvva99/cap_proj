# =============================================================
# Streamlit UI Service Dockerfile
# =============================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Minimal packages: curl for healthcheck, libpq5 for PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -m -u 1000 appuser

# Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application source
COPY app/ ./app/

# Streamlit config
RUN mkdir -p /home/appuser/.streamlit
RUN echo '[server]\nheadless = true\nenableCORS = false\naddress = "0.0.0.0"\nport = 8501' > /home/appuser/.streamlit/config.toml
RUN chown -R appuser:appuser /app /home/appuser/.streamlit

USER appuser

EXPOSE 8501

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]
