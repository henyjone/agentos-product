import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


Config = Dict[str, Any]


def find_project_root(start: Optional[Path] = None) -> Path:
    env_root = os.environ.get("PROJECT_ROOT")
    if env_root:
        root = Path(env_root).expanduser().resolve()
        if (root / "config.json").exists():
            return root
        raise FileNotFoundError("PROJECT_ROOT does not contain config.json")

    candidates = []
    if start is not None:
        candidates.append(Path(start).resolve())
    candidates.append(Path.cwd().resolve())
    candidates.append(Path(__file__).resolve())

    for base in candidates:
        current = base if base.is_dir() else base.parent
        for parent in [current] + list(current.parents)[:8]:
            if (parent / "config.json").exists():
                return parent
    raise FileNotFoundError("config.json not found")


def load_config(root: Optional[Path] = None) -> Config:
    project_root = root or find_project_root()
    config_path = project_root / "config.json"
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid config.json: {0}".format(exc)) from exc

    models = data.get("models")
    default_alias = data.get("default_chat_model")
    if not isinstance(models, dict) or not models:
        raise ValueError("config.json must contain non-empty models")
    if not default_alias or default_alias not in models:
        raise ValueError("default_chat_model must exist in models")

    _validate_model_config(models[default_alias])
    return data


def _validate_model_config(model_config: Dict[str, Any]) -> None:
    for key in ("api_base", "api_key", "model"):
        if not model_config.get(key):
            raise ValueError("model config missing required field: {0}".format(key))
    if model_config.get("api_style") not in (None, "openai-compatible"):
        raise ValueError("only openai-compatible api_style is supported")


def get_default_model_config(root: Optional[Path] = None) -> Dict[str, Any]:
    config = load_config(root)
    model_config = config["models"][config["default_chat_model"]]
    _validate_model_config(model_config)
    return dict(model_config)

