"""一键运行所有平台的全部任务。

青龙定时任务命令：
  task run_all.py

自动发现 platforms/ 下所有含 config.yml 的平台并依次执行（_ 开头目录跳过）。
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 兜底：青龙 init.sh 可能未执行，缺第三方依赖时自动按 requirements.txt 安装
try:
    import yaml, requests  # noqa: F401
except ImportError:
    import subprocess
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r",
         os.path.join(ROOT, "requirements.txt"), "-q"]
    )

from common.loader import discover, load_platform
from common.config import load_global_config
from common.notify import notify
from common.log import logger


def main():
    load_global_config()
    names = discover()
    if not names:
        print("未发现任何平台（platforms/ 下需有 <平台>/config.yml）")
        return

    results = []
    for name in names:
        try:
            signers = load_platform(name)
            for s in signers:
                results.append(s.run())
        except Exception as e:
            logger.exception("平台 %s 运行异常: %s", name, e)
            from common.base import SignResult

            results.append(SignResult(name, "运行", False, f"异常: {e}"))

    lines = [str(r) for r in results]
    ok = sum(1 for r in results if r.success)
    summary = f"共 {len(results)} 个任务，成功 {ok}，失败 {len(results) - ok}\n" + "\n".join(lines)
    print(summary)
    notify("CT-Sign 签到汇总", summary)


if __name__ == "__main__":
    main()
