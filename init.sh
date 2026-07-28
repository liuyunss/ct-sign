"""CT-Sign 初始化（容器内被 ql repo 的初始化命令调用）。

行为：
  1) 安装 Python 依赖（requirements.txt）
  2) 依赖就绪后，定时任务由 ql repo 白名单 sign_ 自动建出（每个平台一行任务，
     无需本脚本建任务，也不依赖青龙 API 令牌）。

注：init.py 现在只做「野任务清理」兜底工具（见 init.py 说明），不再建任务；
正常用 ql repo 订阅不需要调 init.py。

青龙「添加仓库」时的初始化命令填写：
  init.sh
"""

#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "[CT-Sign] 安装 Python 依赖..."
python3 -m pip install -r requirements.txt -q

echo "[CT-Sign] 依赖就绪。定时任务由 ql repo 白名单 sign_ 自动建出（每个平台一行任务）。"
