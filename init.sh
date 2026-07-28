"""CT-Sign 初始化（容器内被 ql repo 的初始化命令调用，免 key 建任务）。

行为：
  1) 安装 Python 依赖（requirements.txt）
  2) 调 init.py 读取所有平台，在青龙里自动建好定时任务
     - 在青龙容器内运行：自动用容器内部令牌，无需任何 key
     - 在容器外运行：未检测到令牌则只校验配置，不建任务（提示用 ql repo 订阅）

青龙「添加仓库」时的初始化命令填写：
  init.sh
"""

#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "[CT-Sign] 安装 Python 依赖..."
python3 -m pip install -r requirements.txt -q

echo "[CT-Sign] 依赖就绪。定时任务由 ql repo 白名单 sign_ 自动建出（每个平台一行任务）。"
