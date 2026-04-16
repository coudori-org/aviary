import os

os.environ.setdefault("SUPERVISOR_DEFAULT_RUNTIME_ENDPOINT", "http://aviary-env-default.agents.svc:3000")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("METRICS_ENABLED", "true")
