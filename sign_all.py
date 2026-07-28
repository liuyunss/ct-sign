#!/usr/bin/env python3
"""CT-Sign 全部签到入口 —— 一次性签到所有平台。

由 ql repo 白名单 sign_ 直接建成青龙定时任务（一行一任务，青龙原生日志）。
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
# 兼容青龙 scripts 目录：依赖文件（run_all.py / common/ 等）在 /ql/data/repo/<同名目录>
_ql_repo = os.path.join("/ql/data/repo", os.path.basename(ROOT))
if os.path.isdir(_ql_repo):
    ROOT = _ql_repo
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from run_all import main

if __name__ == "__main__":
    main()
