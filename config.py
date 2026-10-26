"""Keys, model, limits, and pricing. gpt-6-luna via Portkey is the only model used."""
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"

# .env lives in the repo folder, or one folder up (teaching-staff layout)
for folder in (ROOT, ROOT.parent):
    if (folder / ".env").exists():
        load_dotenv(folder / ".env")
        break

MODEL = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# USD per 1M tokens (published gpt-6-luna list price, Oct 2026)
PRICE_INPUT, PRICE_CACHED, PRICE_OUTPUT = 0.10, 0.01, 0.50

# Guardrails
MAX_SITES = 3
MAX_INPUT_CHARS = 2000
MAX_TOOL_ROUNDS = 6            # analyst tool-call loop cap per site
SESSION_TOKEN_BUDGET = 150_000  # per browser session; app refuses runs past this
MAX_OUTPUT_TOKENS = 2500        # per model call

_client = None


def client() -> OpenAI:
    global _client
    if _client is None:
        key = os.getenv("PORTKEY_API_KEY", "").strip()
        if not key:
            raise RuntimeError("PORTKEY_API_KEY not found. Put it in .env here or one folder up.")
        _client = OpenAI(api_key=key, base_url=PORTKEY_BASE_URL, timeout=90, max_retries=2,
                         default_headers={"x-portkey-api-key": key})
    return _client


def cost_usd(inp: int, cached: int, out: int) -> float:
    return ((inp - cached) * PRICE_INPUT + cached * PRICE_CACHED + out * PRICE_OUTPUT) / 1e6
