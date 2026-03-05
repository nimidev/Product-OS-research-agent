"""Health check diagnostic — `python -m research_agent doctor`."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def _warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{RESET} {msg}")


def _check_python() -> bool:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 11)
    if ok:
        _ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        _fail(f"Python {v.major}.{v.minor}.{v.micro} (need 3.11+)")
    return ok


def _check_deps() -> bool:
    required = ["fastapi", "qdrant_client", "openai", "pydantic", "sqlalchemy"]
    missing = []
    for mod in required:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        _fail(f"Missing packages: {', '.join(missing)}")
        return False
    _ok("All core dependencies installed")
    return True


def _check_env_file() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        _fail(".env file not found — run 'python -m research_agent setup'")
        return {}
    _ok(".env file exists")
    env: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def _check_openai_key(env: dict[str, str]) -> bool:
    key = env.get("OPENAI_API_KEY", "")
    if not key or key == "sk-your-key-here":
        _fail("OpenAI API key not configured")
        return False

    try:
        import openai
        client = openai.OpenAI(api_key=key)
        client.embeddings.create(input="health check", model="text-embedding-3-small")
        _ok("OpenAI API key valid (embedding test passed)")
        return True
    except Exception as e:
        _fail(f"OpenAI API key invalid: {e}")
        return False


def _check_qdrant(env: dict[str, str]) -> tuple[bool, int]:
    import asyncio

    mode = env.get("QDRANT_MODE", "local")
    local_path = env.get("QDRANT_LOCAL_PATH", "./qdrant_data")

    async def _check() -> tuple[bool, int]:
        try:
            from research_agent.config.loader import create_vector_store, get_settings
            settings = get_settings()
            store = create_vector_store(settings)
            count = await store.count()
            await store.close()
            return True, count
        except Exception:
            return False, 0

    ok, count = asyncio.run(_check())
    if ok:
        limit_str = " / 20,000" if mode == "local" else ""
        _ok(f"Qdrant accessible ({mode} mode) — {count:,}{limit_str} vectors")
    else:
        _fail(f"Qdrant not accessible ({mode} mode)")
    return ok, count


def _check_database(env: dict[str, str]) -> bool:
    db_path = PROJECT_ROOT / env.get("DATABASE_PATH", "research_agent.db")
    if db_path.exists():
        size_kb = db_path.stat().st_size / 1024
        _ok(f"Database exists ({size_kb:.0f} KB)")
        return True
    _warn("Database not yet created (will be created on first run)")
    return True


def _check_service(name: str, url: str) -> bool:
    try:
        import urllib.request
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                _ok(f"{name} reachable at {url}")
                return True
    except Exception:
        pass
    _warn(f"{name} not reachable at {url}")
    return False


def run_doctor() -> None:
    """Run all health checks and report status."""
    print(f"\n{BOLD}Research Agent — Health Check{RESET}\n")

    _check_python()
    deps_ok = _check_deps()
    if not deps_ok:
        print(f"\n  Install with: pip install -r requirements.txt\n")
        return

    env = _check_env_file()
    _check_openai_key(env)
    _check_qdrant(env)
    _check_database(env)
    _check_service("API server", "http://localhost:8000/health")
    _check_service("UI server", "http://localhost:3000")

    print()
