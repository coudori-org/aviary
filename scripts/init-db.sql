-- Create separate database for Keycloak
CREATE DATABASE keycloak;
GRANT ALL PRIVILEGES ON DATABASE keycloak TO aviary;

-- Enable uuid extension for aviary database
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
