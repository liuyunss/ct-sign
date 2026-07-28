"""配置读取。

- 环境变量：所有密钥（Cookie 等）来自青龙环境变量，绝不入代码/仓库。
- 全局配置：config/config.yml（代理/延迟/跳过/通知前缀等），可选。
- 本地调试：仓库根 .env 会被自动加载（不进 git，仅本地用）。
"""

from __future__ import annotations

import os

# 本地调试：仓库根目录的 .env 自动加载（仅当变量未设置时）
try:
    from pathlib import Path

    _ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
    if _ENV_FILE.exists():
        with _ENV_FILE.open("r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if not _line or _line.startswith("#") or "=" not in _line:
                    continue
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
except Exception:
    pass

_GLOBAL = {}


def _load_global_config(path=None):
    global _GLOBAL
    if path is None:
        path = Path(__file__).resolve().parent.parent / "config" / "config.yml"
    else:
        path = Path(path)
    if path.exists():
        try:
            import yaml

            with path.open("r", encoding="utf-8") as f:
                _GLOBAL = yaml.safe_load(f) or {}
        except Exception:
            _GLOBAL = {}
    return _GLOBAL


def load_global_config(path=None):
    """加载全局配置（幂等）。"""
    return _load_global_config(path)


def get_global(key, default=None):
    """读取全局配置项；未加载时先尝试加载。"""
    if not _GLOBAL:
        _load_global_config()
    return _GLOBAL.get(key, default)


def get_env(name, default=None):
    """读取环境变量，缺失返回 default。"""
    return os.environ.get(name, default)


def require_env(name):
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"缺少必需的环境变量: {name}")
    return val
