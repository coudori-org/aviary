FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml /app/
RUN pip install --no-cache-dir .
COPY app/ /app/app/

USER nobody
EXPOSE 8080 8081

CMD ["python", "-m", "app.main"]
