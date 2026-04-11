// File backend so secrets persist across `quick-rebuild.sh full`.
// vault-init handles initialize/unseal/dev-token bootstrap.

storage "file" {
  path = "/vault/data"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}

disable_mlock = true
api_addr      = "http://0.0.0.0:8200"
ui            = true
