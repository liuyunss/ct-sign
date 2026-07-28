#!/usr/bin/env python3
"""CT-Sign 全部签到入口 —— 一次性签到所有平台。

由 ql repo 白名单 sign_ 直接建成青龙定时任务（一行一任务，青龙原生日志）。
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from run_all import main

if __name__ == "__main__":
    main()
