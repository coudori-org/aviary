from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    agent_supervisor_url: str

    # Vault
    vault_addr: str
    vault_token: str

    # Keycloak Admin
    keycloak_url: str
    keycloak_admin: str
    keycloak_admin_password: str
    keycloak_realm: str = "aviary"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
