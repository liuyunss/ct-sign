"""轻量日志封装，输出到 stdout（青龙会抓取任务日志推送）。"""

from __future__ import annotations

import logging

logger = logging.getLogger("ct_sign")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)
