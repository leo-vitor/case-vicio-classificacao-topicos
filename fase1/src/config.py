import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "outputs"
CACHE = OUT / "cache"
OUT.mkdir(exist_ok=True)
CACHE.mkdir(exist_ok=True)


def env(key, default):
    return os.getenv(key, default)


JUDGE_BACKEND = env("JUDGE_BACKEND", "gemini")
JUDGE_MODELS = [m.strip() for m in env("JUDGE_MODELS", "gemini-2.5-flash").split(",") if m.strip()]
RUNS_PER_MODEL = int(env("RUNS_PER_MODEL", "3"))
TEMPERATURE = float(env("TEMPERATURE", "0.4"))
JUDGE_WORKERS = int(env("JUDGE_WORKERS", "4"))

EMBEDDINGS = env("EMBEDDINGS", "tfidf")
EMBEDDING_MODEL = env("EMBEDDING_MODEL", "gemini-embedding-001")
TOP_K = int(env("TOP_K", "10"))

THRESH = float(env("THRESH", "0.85"))
LIXEIRA_MIN_Q = int(env("LIXEIRA_MIN_Q", "40"))
LIXEIRA_EXTRA = float(env("LIXEIRA_EXTRA", "0.05"))
LIMIT = int(env("LIMIT", "0"))
