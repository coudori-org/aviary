"""Shared Pydantic helpers — UUID→str BeforeValidator used across every
response schema so ORM ``uuid.UUID`` values serialize as plain strings
for the wire contract (frontend expects ``id: string``)."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BeforeValidator


def _to_str(v):
    return str(v) if isinstance(v, uuid.UUID) else v


UuidStr = Annotated[str, BeforeValidator(_to_str)]
OptionalUuidStr = Annotated[str | None, BeforeValidator(_to_str)]

# ``model_config_json`` collides with Pydantic v2's reserved ``model_`` prefix;
# every schema that carries this field opts into
# ``protected_namespaces=()`` via this sentinel for clarity.
MODEL_CONFIG_ALIAS = {"alias": "model_config"}
