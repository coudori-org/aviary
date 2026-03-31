/**
 * Node.js proxy bootstrap — loaded via NODE_OPTIONS="--require /app/scripts/proxy-bootstrap.js"
 *
 * Node.js's built-in fetch() (undici) does NOT respect HTTP_PROXY/HTTPS_PROXY.
 * This script sets undici's EnvHttpProxyAgent as the global dispatcher so all
 * fetch() calls route through the egress proxy.
 *
 * Requires `undici` npm package installed globally (see Dockerfile).
 * Uses absolute path because Node.js doesn't include /usr/lib/node_modules
 * in require() search paths by default.
 *
 * Node 24+ can use NODE_USE_ENV_PROXY=1 instead, making this unnecessary.
 */
"use strict";

if (process.env.HTTP_PROXY || process.env.HTTPS_PROXY) {
  try {
    const { setGlobalDispatcher, EnvHttpProxyAgent } = require("/usr/lib/node_modules/undici");
    setGlobalDispatcher(new EnvHttpProxyAgent());
  } catch (_) {
    // undici not available — skip silently
  }
}
