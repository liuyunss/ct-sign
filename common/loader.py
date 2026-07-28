"""加载器：读取 platforms/<名>/config.yml，构造对应的 Signer 列表。

- 每个平台是一个目录，内含 config.yml（从 templates/forum_sign.yml 复制填好）。
- config.yml 顶层是平台公共字段（base_url/cookie_env/engine），
  tasks 列表描述该平台要跑的多个任务（签到/抽奖/做任务…）。
- 多任务类型从第一天就支持：加一个 task 条目即可，不动引擎。
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import get_global, load_global_config
from .engines import ENGINE_MAP
from .log import logger

PLATFORMS_DIR = Path(__file__).resolve().parent.parent / "platforms"


def _load_yaml(path):
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}



def load_platform(name):
    """返回该平台的所有 Signer 实例列表。"""
    cfg_path = PLATFORMS_DIR / name / "config.yml"
    if not cfg_path.exists():
        logger.error("未找到平台配置: %s", cfg_path)
        return []
    cfg = _load_yaml(cfg_path)
    engine = cfg.get("engine", "forum")
    cls = ENGINE_MAP.get(engine)
    if not cls:
        logger.error("平台 %s 使用了未知引擎: %s", name, engine)
        return []

    base_url = cfg.get("base_url", "")
    cookie_env = cfg.get("cookie_env", "")
    account_sep = cfg.get("account_separator", "&")
    proxy = get_global("proxy", "") or os.environ.get("CT_PROXY", "")
    try:
        random_delay = int(get_global("random_delay", 0) or os.environ.get("CT_RANDOM_DELAY", 0) or 0)
    except Exception:
        random_delay = 0
    try:
        random_delay_min = int(get_global("random_delay_min", 0) or os.environ.get("CT_RANDOM_DELAY_MIN", 0) or 0)
    except Exception:
        random_delay_min = 0
    if random_delay_min > random_delay:
        random_delay_min = random_delay

    signers = []
    for task in cfg.get("tasks", []):
        tcfg = {"base_url": base_url, "cookie_env": cookie_env,
                "login": cfg.get("login")}
        tcfg.update(task)  # 任务级字段覆盖公共字段
        signers.append(cls(
            platform=cfg.get("platform", name),
            task_cfg=tcfg,
            cookie_env=cookie_env,
            account_separator=account_sep,
            proxy=proxy,
            random_delay=random_delay,
            random_delay_min=random_delay_min,
        ))
    return signers


def discover():
    """发现所有有效平台（含 config.yml 且不以 _ 开头的目录）。"""
    if not PLATFORMS_DIR.exists():
        return []
    skip = set(get_global("skip_platforms") or [])
    names = []
    for d in sorted(os.listdir(PLATFORMS_DIR)):
        sub = PLATFORMS_DIR / d
        if not sub.is_dir():
            continue
        if d.startswith("_"):
            continue
        if not (sub / "config.yml").exists():
            continue
        if d in skip:
            continue
        names.append(d)
    return names
