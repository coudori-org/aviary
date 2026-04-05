FROM python:3.12-slim

RUN pip install --no-cache-dir "mcp>=1.0.0" uvicorn starlette

WORKDIR /app

ARG MCP_SERVER_NAME
COPY ${MCP_SERVER_NAME}/server.py /app/server.py

CMD ["python", "server.py"]
