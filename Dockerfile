FROM python:3.11-slim

WORKDIR /workspace

# Copy entire project
COPY . /workspace/

# Install system dependencies
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install -q numpy duckdb pandas dbt-core dbt-duckdb plotly streamlit 2>&1 | grep -v '^WARNING\|^\[notice\]' || true

# Set environment
ENV PYTHONUNBUFFERED=1
ENV DBT_PROFILES_DIR=/workspace

# Default command
CMD ["echo", "Use: docker-compose --profile init up OR docker-compose --profile app up"]
