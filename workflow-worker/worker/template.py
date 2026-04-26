from __future__ import annotations

from jinja2 import Environment, StrictUndefined

jinja_env = Environment(undefined=StrictUndefined, autoescape=False)
