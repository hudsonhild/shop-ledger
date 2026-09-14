"""Configuration, resolved from the environment and an optional .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Read a .env file into os.environ without overwriting real env vars."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _find_dotenv() -> Path | None:
    """Walk up from the working directory looking for a .env."""
    here = Path.cwd().resolve()
    for directory in (here, *here.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


@dataclass(frozen=True)
class Config:
    api_key: str
    data_dir: Path
    panel_size: int
    min_credits: int
    default_vpu: float
    engagement_k: float

    @property
    def db_path(self) -> Path:
        return self.data_dir / "shop-ledger.db"

    @property
    def out_dir(self) -> Path:
        return self.data_dir / "out"


class ConfigError(RuntimeError):
    pass


def load(require_key: bool = True) -> Config:
    dotenv = _find_dotenv()
    if dotenv:
        _load_dotenv(dotenv)

    api_key = os.environ.get("SCRAPECREATORS_API_KEY", "").strip()
    if require_key and not api_key:
        raise ConfigError(
            "No SCRAPECREATORS_API_KEY found.\n"
            "  1. Get a free key at https://scrapecreators.com (10,000 calls, no card)\n"
            "  2. cp .env.example .env\n"
            "  3. Put the key in .env\n"
            "The key is read from .env or the environment and is never written to the database."
        )

    data_dir = Path(os.environ.get("SHOPLEDGER_DATA_DIR", "./data")).expanduser().resolve()

    def _num(name: str, default: float) -> float:
        raw = os.environ.get(name, "").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError as exc:
            raise ConfigError(f"{name} must be a number, got {raw!r}") from exc

    return Config(
        api_key=api_key,
        data_dir=data_dir,
        panel_size=int(_num("SHOPLEDGER_PANEL_SIZE", 50)),
        min_credits=int(_num("SHOPLEDGER_MIN_CREDITS", 200)),
        default_vpu=_num("SHOPLEDGER_DEFAULT_VPU", 2000),
        engagement_k=_num("SHOPLEDGER_ENGAGEMENT_K", 10),
    )
