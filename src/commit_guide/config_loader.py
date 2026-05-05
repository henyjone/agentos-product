"""配置加载模块 —— 从项目根目录的 config.json 读取模型配置，支持多模型别名。"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


Config = Dict[str, Any]


def find_project_root(start: Optional[Path] = None) -> Path:
    """向上遍历目录树，找到包含 config.json 的项目根目录。

    优先读取 PROJECT_ROOT 环境变量；未设置时从 start、cwd、__file__ 三个候选路径
    向上最多搜索 8 层父目录。
    """
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
    """加载并校验 config.json，返回完整配置字典。

    校验内容：models 字段非空、default_chat_model 存在于 models 中，
    以及默认模型配置包含必要字段。
    """
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
    """校验单个模型配置是否包含必要字段（api_base、api_key、model）。"""
    for key in ("api_base", "api_key", "model"):
        if not model_config.get(key):
            raise ValueError("model config missing required field: {0}".format(key))
    if model_config.get("api_style") not in (None, "openai-compatible"):
        raise ValueError("only openai-compatible api_style is supported")


def get_model_config(alias: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """按别名获取指定模型的配置字典（副本）。"""
    config = load_config(root)
    try:
        model_config = config["models"][alias]
    except KeyError as exc:
        raise KeyError("model alias not found: {0}".format(alias)) from exc
    _validate_model_config(model_config)
    return dict(model_config)


def get_default_model_config(root: Optional[Path] = None) -> Dict[str, Any]:
    """获取 default_chat_model 指向的模型配置字典（副本）。"""
    config = load_config(root)
    default_alias = config["default_chat_model"]
    model_config = config["models"][default_alias]
    _validate_model_config(model_config)
    return dict(model_config)

