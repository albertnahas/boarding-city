"""Settings from the environment (or a .env file in the working directory). The API key is only ever read, never written."""
import os
from pathlib import Path

ROOT = Path.cwd()


def load_env(path=ROOT / ".env"):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


load_env()

FAST_MODEL = os.environ.get("BOARDING_FAST_MODEL", "gpt-6-luna")      # file picking, naming, headlines
TRACE_MODEL = os.environ.get("BOARDING_TRACE_MODEL", "gpt-6.1-terra")  # flow traces
TRACE_EFFORT = os.environ.get("BOARDING_TRACE_EFFORT", "low")
# $ per 1M tokens (input, output), for the cost report only
PRICES = {"gpt-6-luna": (0.10, 0.50), "gpt-6.1-terra": (1.0, 5.0), "gpt-6.1-sol": (2.0, 10.0), "gpt-5.5": (5.0, 30.0)}
TIMEOUT = int(os.environ.get("BOARDING_TIMEOUT", "180"))
RETRIES = int(os.environ.get("BOARDING_RETRIES", "3"))
CACHE = ROOT / ".cache"
SITE = ROOT / "site"
ASSETS = Path(__file__).parent / "assets"
