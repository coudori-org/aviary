FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install shared package first (satisfies aviary-shared dependency)
COPY shared/ /shared/
RUN pip install --no-cache-dir /shared

# Install Python deps
COPY admin/pyproject.toml /app/
RUN pip install --no-cache-dir -e .

# Copy application code (overridden by volume mount in dev)
COPY admin/ /app/

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
