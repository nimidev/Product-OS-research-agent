"""Interactive setup wizard — `python -m research_agent setup`."""

from __future__ import annotations

import getpass
import os
import platform
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
DB_DEFAULT = "research_agent.db"
QDRANT_LOCAL_DIR = PROJECT_ROOT / "qdrant_data"
UI_DIR = PROJECT_ROOT / "ui"
VENV_DIR = PROJECT_ROOT / ".venv"

# Minimum versions
MIN_PYTHON = (3, 11)
MIN_NODE_MAJOR = 20

# Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

TOTAL_STEPS = 5


def _ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def _warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{RESET} {msg}")


def _step(num: int, title: str) -> None:
    print(f"\n{BOLD}[{num}/{TOTAL_STEPS}] {title}{RESET}")


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


# ── Step 1: Environment check ────────────────────────────────────────────────


def _check_python() -> bool:
    v = sys.version_info
    ok = (v.major, v.minor) >= MIN_PYTHON
    if ok:
        _ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        _fail(f"Python {v.major}.{v.minor}.{v.micro} (need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)")
    return ok


def _check_node() -> tuple[bool, str | None]:
    node = shutil.which("node")
    if not node:
        _warn("Node.js not found — UI will not be set up")
        return False, None

    result = _run(["node", "--version"])
    version_str = result.stdout.strip().lstrip("v")
    try:
        major = int(version_str.split(".")[0])
    except (ValueError, IndexError):
        _warn(f"Node.js {version_str} — could not parse version")
        return False, version_str

    if major >= MIN_NODE_MAJOR:
        _ok(f"Node.js {version_str}")
        return True, version_str
    else:
        _warn(f"Node.js {version_str} (need {MIN_NODE_MAJOR}+, UI setup will be skipped)")
        return False, version_str


def _check_docker() -> bool:
    docker = shutil.which("docker")
    if not docker:
        _ok("Docker not found — that's OK, using local storage mode")
        return False
    result = _run(["docker", "--version"])
    version_str = result.stdout.strip()
    _ok(f"{version_str} (not required — using local storage mode)")
    return True


def step_environment() -> dict:
    """Step 1: Check environment. Returns dict with detection results."""
    _step(1, "Checking environment...")
    python_ok = _check_python()
    if not python_ok:
        print(f"\n{RED}Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required. Aborting.{RESET}")
        sys.exit(1)

    node_ok, node_version = _check_node()
    docker_ok = _check_docker()
    return {"python_ok": python_ok, "node_ok": node_ok, "docker_ok": docker_ok}


# ── Step 2: Dependencies ─────────────────────────────────────────────────────


def _is_venv_active() -> bool:
    return sys.prefix != sys.base_prefix


def _deps_installed() -> bool:
    try:
        import fastapi  # noqa: F401
        import qdrant_client  # noqa: F401
        import openai  # noqa: F401

        return True
    except ImportError:
        return False


def _ui_deps_installed() -> bool:
    return (UI_DIR / "node_modules").is_dir()


def step_dependencies(env: dict) -> None:
    """Step 2: Install Python (and optionally Node.js) dependencies."""
    _step(2, "Installing dependencies...")

    if _is_venv_active() and _deps_installed():
        _ok("Python packages already installed")
    elif _is_venv_active():
        print("  Installing Python packages...")
        result = _run(
            [sys.executable, "-m", "pip", "install", "-r", str(PROJECT_ROOT / "requirements.txt")],
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            _ok("Python packages installed")
        else:
            _fail("pip install failed")
            print(result.stderr[:500])
            sys.exit(1)
    else:
        if VENV_DIR.exists() and _deps_installed():
            _ok("Python packages already installed (venv exists)")
        elif VENV_DIR.exists():
            _warn(
                "Virtual environment exists but packages are missing.\n"
                f"    Run: source {VENV_DIR}/bin/activate && pip install -r requirements.txt"
            )
        else:
            _warn(
                "No virtual environment active.\n"
                f"    Run: python3 -m venv .venv && source .venv/bin/activate && "
                f"pip install -r requirements.txt\n"
                "    Then re-run: python -m research_agent setup"
            )

    if env.get("node_ok"):
        if _ui_deps_installed():
            _ok("UI packages already installed")
        else:
            print("  Installing UI packages (npm install)...")
            result = _run(["npm", "install"], cwd=str(UI_DIR))
            if result.returncode == 0:
                _ok("UI packages installed")
            else:
                _warn("npm install failed — you can set up the UI later")
    elif not env.get("node_ok"):
        _warn(
            f"Node.js {MIN_NODE_MAJOR}+ needed for the web interface.\n"
            "    Install from: https://nodejs.org/\n"
            "    Then re-run: python -m research_agent setup"
        )


# ── Step 3: OpenAI API key ───────────────────────────────────────────────────


def _read_env_file() -> dict[str, str]:
    """Parse .env file into a dict."""
    env: dict[str, str] = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def _write_env_file(values: dict[str, str]) -> None:
    """Write/update .env file preserving comments and adding new keys."""
    lines: list[str] = []
    existing_keys: set[str] = set()

    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in values:
                    lines.append(f"{key}={values[key]}")
                    existing_keys.add(key)
                else:
                    lines.append(line)
            else:
                lines.append(line)
    else:
        if ENV_EXAMPLE.exists():
            for line in ENV_EXAMPLE.read_text().splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key = stripped.split("=", 1)[0].strip()
                    if key in values:
                        lines.append(f"{key}={values[key]}")
                        existing_keys.add(key)
                    else:
                        lines.append(line)
                else:
                    lines.append(line)

    for key, value in values.items():
        if key not in existing_keys:
            lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(lines) + "\n")


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return key[:4] + "•" * (len(key) - 8) + key[-4:]


def _validate_openai_key(api_key: str) -> bool:
    """Validate the OpenAI API key with a minimal embedding call."""
    try:
        import openai

        client = openai.OpenAI(api_key=api_key)
        client.embeddings.create(input="test", model="text-embedding-3-small")
        return True
    except Exception:
        return False


def step_openai_key() -> str:
    """Step 3: Configure OpenAI API key. Returns the validated key."""
    _step(3, "OpenAI API Key")
    print("  This powers search & synthesis.")
    print(f"  Get one at: {BOLD}https://platform.openai.com/api-keys{RESET}")

    env = _read_env_file()
    existing_key = env.get("OPENAI_API_KEY", "")
    if existing_key and existing_key != "sk-your-key-here":
        print(f"  Existing key found: {_mask_key(existing_key)}")
        print("  Validating...", end=" ", flush=True)
        if _validate_openai_key(existing_key):
            print()
            _ok("Key validated (embedding test passed)")
            return existing_key
        else:
            print()
            _warn("Existing key is invalid or expired")

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        print("  Paste your API key (input is hidden): ", end="", flush=True)
        key = getpass.getpass("")
        if not key.strip():
            _warn("No key entered")
            continue

        print(f"  Received key: {_mask_key(key.strip())}")
        print("  Validating...", end=" ", flush=True)
        if _validate_openai_key(key.strip()):
            print()
            _ok("Key validated (embedding test passed)")
            _write_env_file({"OPENAI_API_KEY": key.strip()})
            return key.strip()
        else:
            print()
            _fail(f"Invalid key (attempt {attempt}/{max_attempts})")
            if attempt < max_attempts:
                print("  Check that your key is correct and billing is active.")

    print(f"\n{RED}Could not validate API key after {max_attempts} attempts.{RESET}")
    print("  You can manually set OPENAI_API_KEY in .env and re-run setup.")
    sys.exit(1)


# ── Step 4: Storage init ─────────────────────────────────────────────────────


def step_storage() -> None:
    """Step 4: Initialize Qdrant local storage and SQLite DB."""
    _step(4, "Initializing storage...")

    QDRANT_LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    _ok(f"Vector store ready (local mode → {QDRANT_LOCAL_DIR.relative_to(PROJECT_ROOT)})")

    env = _read_env_file()
    env.setdefault("QDRANT_MODE", "local")
    env.setdefault("QDRANT_LOCAL_PATH", str(QDRANT_LOCAL_DIR))
    _write_env_file(env)

    db_path = PROJECT_ROOT / env.get("DATABASE_PATH", DB_DEFAULT)
    if db_path.exists():
        _ok("Database already exists")
    else:
        _ok("Database will be created on first run")


# ── Step 5: Start services ───────────────────────────────────────────────────


def _wait_for_url(url: str, timeout: int = 15) -> bool:
    """Poll a URL until it returns 200 or timeout expires."""
    import time
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def step_start_services(env: dict) -> None:
    """Step 5: Start API (and UI if Node.js available), open browser."""
    _step(5, "Starting services...")

    api_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "research_agent.api.server:app",
         "--host", "0.0.0.0", "--port", "8000"],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _ok(f"API starting at http://localhost:8000 (pid {api_proc.pid})")

    ui_proc = None
    has_ui = env.get("node_ok") and _ui_deps_installed()
    if has_ui:
        ui_proc = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(UI_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _ok(f"UI starting at http://localhost:3000 (pid {ui_proc.pid})")

    print("\n  Waiting for API...", end="", flush=True)
    if _wait_for_url("http://localhost:8000/health", timeout=20):
        print(f" {GREEN}ready{RESET}")
    else:
        print(f" {YELLOW}slow to start (may still be loading){RESET}")

    if has_ui:
        print("  Waiting for UI...", end="", flush=True)
        if _wait_for_url("http://localhost:3000", timeout=20):
            print(f" {GREEN}ready{RESET}")
        else:
            print(f" {YELLOW}slow to start (may still be loading){RESET}")

        print(f"\n  Opening browser → http://localhost:3000")
        webbrowser.open("http://localhost:3000")
    else:
        print(f"\n  {YELLOW}⚠  UI not available — Node.js {MIN_NODE_MAJOR}+ is required{RESET}")
        print(f"     (Tailwind CSS v4 needs Node 20+ native bindings)")
        print(f"\n  To fix:")
        print(f"    1. Install Node.js 20+ from {BOLD}https://nodejs.org/{RESET}")
        print(f"       or: {BOLD}nvm install 20 && nvm use 20{RESET}")
        print(f"    2. Re-run: {BOLD}python -m research_agent setup{RESET}")
        print(f"\n  API is running at http://localhost:8000/health")

    print(f"\n{GREEN}{BOLD}✅ Setup complete!{RESET}")
    print(f"\n  {BOLD}Tip:{RESET} Run '{BOLD}python -m research_agent doctor{RESET}' anytime")
    print("  to check your setup health.\n")

    print("  Press Ctrl+C to stop the services.\n")

    try:
        api_proc.wait()
    except KeyboardInterrupt:
        print("\n  Stopping services...")
        api_proc.terminate()
        if ui_proc:
            ui_proc.terminate()
        print("  Done.")


# ── Main orchestrator ─────────────────────────────────────────────────────────


def run_setup() -> None:
    """Run the full interactive setup wizard."""
    print(f"\n{BOLD}Welcome to Research Agent Setup{RESET}")
    print(f"This will take about {BOLD}5 minutes{RESET}.\n")

    env = step_environment()
    step_dependencies(env)
    step_openai_key()
    step_storage()
    step_start_services(env)
