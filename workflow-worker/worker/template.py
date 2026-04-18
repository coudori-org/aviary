"""Shared sandboxed Jinja environment.

`StrictUndefined` fails loud on missing keys instead of rendering empty.
`autoescape=False` keeps payloads verbatim — we're not producing HTML.
"""

from __future__ import annotations

from jinja2 import Environment, StrictUndefined

jinja_env = Environment(undefined=StrictUndefined, autoescape=False)
