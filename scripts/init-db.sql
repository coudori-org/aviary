-- Create separate database for Keycloak
CREATE DATABASE keycloak;
GRANT ALL PRIVILEGES ON DATABASE keycloak TO aviary;

-- Create separate database for LiteLLM (proxy UI / key + spend tracking).
-- LiteLLM runs its own Prisma migrations on startup against this DB.
CREATE DATABASE litellm;
GRANT ALL PRIVILEGES ON DATABASE litellm TO aviary;

-- Temporal server uses two separate databases (main history store + visibility
-- index). The `auto-setup` image runs its own schema migrations on startup.
CREATE DATABASE temporal;
GRANT ALL PRIVILEGES ON DATABASE temporal TO aviary;
CREATE DATABASE temporal_visibility;
GRANT ALL PRIVILEGES ON DATABASE temporal_visibility TO aviary;

-- Enable uuid extension for aviary database
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
