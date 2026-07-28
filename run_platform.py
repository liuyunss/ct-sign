"""运行单个平台的所有任务。

用法：
  python run_platform.py <平台名>
  python run_platform.py fuliba

青龙定时任务命令：
  task run_platform.py fuliba
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from common.loader import load_platform
from common.notify import notify
from common.log import logger


def main(name=None):
    if name is None:
        if len(sys.argv) < 2:
            logger.error("用法: python run_platform.py <平台名>")
            sys.exit(2)
        name = sys.argv[1]
    signers = load_platform(name)
    if not signers:
        logger.error("平台 %s 无可执行任务（检查 platforms/%s/config.yml）", name, name)
        sys.exit(1)

    results = [s.run() for s in signers]
    summary = "\n".join(str(r) for r in results)
    print(summary)
    notify(f"CT-Sign · {signers[0].platform}", summary)


if __name__ == "__main__":
    main()
