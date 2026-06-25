import json
import os
import shutil
import sys
from pathlib import Path


APP_NAME = "LensBridgeAI"
PROJECT_ROOT = Path(__file__).resolve().parent
IS_FROZEN = bool(getattr(sys, "frozen", False))
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))


def resource_path(*parts):
    return BUNDLE_ROOT.joinpath(*parts)


if IS_FROZEN:
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
    CONFIG_PATH = DATA_DIR / "config.json"
    DB_PATH = DATA_DIR / "server.db"
    UPLOAD_DIR = DATA_DIR / "uploads"
    TEMP_DIR = DATA_DIR / "temp"
    LOG_DIR = DATA_DIR / "logs"
else:
    DATA_DIR = PROJECT_ROOT
    CONFIG_PATH = PROJECT_ROOT / "server" / "config.json"
    DB_PATH = PROJECT_ROOT / "server" / "server.db"
    UPLOAD_DIR = PROJECT_ROOT / "server" / "uploads"
    TEMP_DIR = PROJECT_ROOT / "temp_captures"
    LOG_DIR = PROJECT_ROOT / "logs"


def ensure_runtime_layout():
    for directory in (DATA_DIR, UPLOAD_DIR, TEMP_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    if IS_FROZEN:
        executable_dir = Path(sys.executable).resolve().parent
        legacy_root = executable_dir.parent if executable_dir.name.lower() == "dist" else None
        legacy_server = legacy_root / "server" if legacy_root else None

        if legacy_server and legacy_server.exists():
            legacy_config = legacy_server / "config.json"
            legacy_db = legacy_server / "server.db"
            legacy_uploads = legacy_server / "uploads"

            if not CONFIG_PATH.exists() and legacy_config.exists():
                shutil.copy2(legacy_config, CONFIG_PATH)
            if not DB_PATH.exists() and legacy_db.exists():
                shutil.copy2(legacy_db, DB_PATH)
            if legacy_uploads.exists() and not any(UPLOAD_DIR.iterdir()):
                shutil.copytree(legacy_uploads, UPLOAD_DIR, dirs_exist_ok=True)

    if not CONFIG_PATH.exists():
        default_config = resource_path("server", "config.default.json")
        if default_config.exists():
            shutil.copy2(default_config, CONFIG_PATH)
        else:
            CONFIG_PATH.write_text(
                json.dumps(
                    {
                        "active_agent": "mock",
                        "server": {"host": "0.0.0.0", "port": 8000},
                        "agents": {},
                        "global_system_prompt": "",
                        "hotkeys": {
                            "toggle": "f8",
                            "send": "f9",
                            "clear": "esc",
                            "retry": "f10",
                            "open": "f12",
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
