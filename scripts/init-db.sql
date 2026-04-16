-- Create separate database for Keycloak
CREATE DATABASE keycloak;
GRANT ALL PRIVILEGES ON DATABASE keycloak TO aviary;

-- Create separate database for LiteLLM (proxy UI / key + spend tracking).
-- LiteLLM runs its own Prisma migrations on startup against this DB.
CREATE DATABASE litellm;
GRANT ALL PRIVILEGES ON DATABASE litellm TO aviary;

-- Enable uuid extension for aviary database
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
