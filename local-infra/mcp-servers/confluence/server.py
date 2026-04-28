"""Confluence MCP server entry — CONFLUENCE_API_VARIANT picks cloud (default) or legacy."""

import os

variant = os.environ.get("CONFLUENCE_API_VARIANT", "cloud").lower()

if variant == "cloud":
    from cloud import mcp
elif variant == "legacy":
    from legacy import mcp
else:
    raise RuntimeError(
        f"CONFLUENCE_API_VARIANT must be 'cloud' or 'legacy', got {variant!r}"
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
