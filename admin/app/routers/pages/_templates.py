"""Shared Jinja2 templates instance for all page routers."""

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
