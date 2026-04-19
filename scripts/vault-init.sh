#!/bin/sh
# Idempotently initialize, unseal, and seed Vault for the dev environment.
# Init keys live next to the data file so the volume is self-contained;
# wiping vaultdata triggers a fresh init on next boot.
set -e

KEYS_FILE=/vault/data/.aviary-init.json
DEV_TOKEN=dev-root-token

if vault status 2>&1 | grep -qE 'Initialized\s+false'; then
  echo "Initializing Vault..."
  vault operator init -key-shares=1 -key-threshold=1 -format=json > "$KEYS_FILE"
  chmod 600 "$KEYS_FILE"
fi

if [ ! -f "$KEYS_FILE" ]; then
  echo "ERROR: Vault is initialized but $KEYS_FILE is missing." >&2
  exit 1
fi

# Avoid a jq dependency: compact the JSON and pull fields with sed.
COMPACT=$(tr -d ' \n\r' < "$KEYS_FILE")
ROOT_TOKEN=$(echo "$COMPACT" | sed -n 's/.*"root_token":"\([^"]*\)".*/\1/p')
UNSEAL_KEY=$(echo "$COMPACT" | sed -n 's/.*"unseal_keys_b64":\["\([^"]*\)".*/\1/p')

if [ -z "$ROOT_TOKEN" ] || [ -z "$UNSEAL_KEY" ]; then
  echo "ERROR: Failed to parse $KEYS_FILE" >&2
  exit 1
fi

if vault status 2>&1 | grep -qE 'Sealed\s+true'; then
  echo "Unsealing Vault..."
  vault operator unseal "$UNSEAL_KEY" >/dev/null
fi

export VAULT_TOKEN="$ROOT_TOKEN"

# Deterministic dev token so the rest of the stack keeps using a static
# VAULT_TOKEN env var. Fails on second run when the token already exists.
vault token create -id="$DEV_TOKEN" -policy=root -no-default-policy -ttl=0 \
  >/dev/null 2>&1 || true

vault secrets enable -version=2 -path=secret kv >/dev/null 2>&1 || true

echo "Vault ready (dev token: $DEV_TOKEN)"
