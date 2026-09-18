FROM python:3.11-slim

WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY app/ .
COPY ingest/ ../ingest/
COPY dbt/ ../dbt/
COPY generator/ ../generator/

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Default: run Streamlit app
CMD ["streamlit", "run", "streamlit_app.py"]
