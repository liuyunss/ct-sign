"""公共工具函数。

- random_sleep：在 [min, max] 区间内随机休眠，用于"模拟用户随机触发"，
  让固定时间点的定时任务表现为不规律的访问节奏，降低被风控识别的概率。
- split_accounts：多账号 Cookie 拆分（& 或换行分隔）。
全部平台/引擎共用，集中在此避免重复实现。
"""

from __future__ import annotations

import random
import re
import time

from .log import logger


def random_sleep(max_seconds, min_seconds=0, reason="随机延迟"):
    """在 [min_seconds, max_seconds] 之间随机休眠（秒），返回实际休眠秒数。

    - max_seconds <= 0 时直接返回 0，不休眠。
    - 用于签到前/多账号之间，模拟人工随机触发，避免固定节奏被识别。
    """
    if max_seconds is None:
        max_seconds = 0
    max_seconds = float(max_seconds)
    if max_seconds <= 0:
        return 0.0
    lo = 0.0 if min_seconds is None else float(min_seconds)
    if lo < 0:
        lo = 0.0
    hi = max(lo, max_seconds)
    delay = random.uniform(lo, hi)
    logger.info("⏱  %s（范围 %.1f~%.1fs），实际延迟 %.1fs", reason, lo, hi, delay)
    time.sleep(delay)
    return delay


def split_accounts(cookie: str, separator: str = "&"):
    """把一个变量里的多账号 Cookie 拆开。同时支持 & 与换行作为分隔。"""
    if not cookie:
        return []
    parts = re.split(r"[&\n]", cookie)
    return [p.strip() for p in parts if p and p.strip()]


def make_random_delay(max_seconds, min_seconds=0, reason="随机延迟"):
    """兼容别名，语义同 random_sleep。"""
    return random_sleep(max_seconds, min_seconds, reason)
