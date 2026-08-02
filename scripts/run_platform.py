"""运行单个平台的所有任务。

用法：
  python scripts/run_platform.py <平台名>
  python scripts/run_platform.py fuliba

青龙定时任务命令（入口为根目录 sign_<平台>.py，它转发到这里）：
  task sign_fuliba.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 青龙自带 notify 模块（含 send_notify）位于 /ql/data/scripts，加入 path
# 以便复用面板已配的推送渠道（与 smzdm_script 等仓库行为一致）。
_ql_scripts = "/ql/data/scripts"
if os.path.isdir(_ql_scripts) and _ql_scripts not in sys.path:
    sys.path.insert(0, _ql_scripts)

# 兜底：青龙 init.sh 可能未执行，缺第三方依赖时自动按 requirements.txt 安装
try:
    import yaml, requests  # noqa: F401
except ImportError:
    import subprocess
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r",
         os.path.join(ROOT, "requirements.txt"), "-q"]
    )

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
    notify(f"CT-Sign · {signers[0].platform}", summary)


if __name__ == "__main__":
    main()
