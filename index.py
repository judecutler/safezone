"""Vercel entry point: Vercel's Python runtime loads the top-level `app` from this file."""
from safezone.app import create_app

app = create_app()
