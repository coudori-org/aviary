FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install shared package first
COPY shared/ /shared/
RUN pip install --no-cache-dir /shared

COPY controller/pyproject.toml /app/
RUN pip install --no-cache-dir -e .

COPY controller/ /app/

EXPOSE 9000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
