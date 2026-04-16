import os

os.environ.setdefault("SUPERVISOR_DEFAULT_RUNTIME_ENDPOINT", "http://aviary-env-default.agents.svc:3000")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("METRICS_ENABLED", "true")
os.environ.setdefault("OIDC_ISSUER", "http://localhost:8080/realms/aviary")
os.environ.setdefault("OIDC_INTERNAL_ISSUER", "http://keycloak:8080/realms/aviary")
os.environ.setdefault("VAULT_ADDR", "http://localhost:8200")
os.environ.setdefault("VAULT_TOKEN", "dev-root-token")
