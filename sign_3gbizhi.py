#!/usr/bin/env python3
"""CT-Sign 平台签到入口 —— 3G壁纸。

由 ql repo 白名单 sign_ 直接建成青龙定时任务（一行一任务，青龙原生日志）。
此文件由仓库提供，请勿手改；新增平台时复制本文件、把 main() 的平台 key 改成目录名即可。
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from run_platform import main

if __name__ == "__main__":
    main("3gbizhi")
