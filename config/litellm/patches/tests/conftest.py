import os
import sys
from pathlib import Path

PATCHES_DIR = Path(__file__).resolve().parent.parent
if str(PATCHES_DIR) not in sys.path:
    sys.path.insert(0, str(PATCHES_DIR))

os.environ.setdefault("OIDC_ISSUER", "http://localhost:8080/realms/aviary")
os.environ.setdefault("OIDC_INTERNAL_ISSUER", "http://keycloak:8080/realms/aviary")
os.environ.setdefault("VAULT_ADDR", "http://localhost:8200")
os.environ.setdefault("VAULT_TOKEN", "dev-root-token")
