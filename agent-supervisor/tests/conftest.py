import os

os.environ.setdefault("BACKEND_KIND", "k3s")
os.environ.setdefault("HOST_GATEWAY_IP", "127.0.0.1")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/dummy")
os.environ.setdefault("INFERENCE_ROUTER_URL", "http://litellm:4000")
os.environ.setdefault("MCP_GATEWAY_URL", "http://mcp-gateway:8100")
os.environ.setdefault("LITELLM_API_KEY", "sk-test")
os.environ.setdefault("AVIARY_API_URL", "http://api:8000")
os.environ.setdefault("INTERNAL_API_KEY", "internal-test")
