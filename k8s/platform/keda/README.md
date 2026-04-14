# Vendored KEDA release manifests

The `keda-<version>.yaml` files here are verbatim copies of the upstream
KEDA release bundles, checked in so `setup-dev.sh` works offline and with a
pinned version.

## Upgrading

```bash
VERSION=2.15.2   # set the new version
curl -fsSL -o k8s/platform/keda/keda-${VERSION}.yaml \
  https://github.com/kedacore/keda/releases/download/v${VERSION}/keda-${VERSION}.yaml

# Bump KEDA_VERSION in scripts/setup-dev.sh, commit both files together.
# Delete the old keda-*.yaml after verifying the upgrade works.
```

Upstream: <https://github.com/kedacore/keda/releases>
