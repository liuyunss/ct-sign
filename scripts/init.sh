"""CT-Sign 初始化（容器内被 ql repo 的初始化命令调用）。

行为：
  1) 安装 Python 依赖（requirements.txt）
  2) 依赖就绪后，定时任务由 ql repo 白名单 sign_ 自动建出（每个平台一行任务，
     无需本脚本建任务，也不依赖青龙 API 令牌）。

注：init.py 现在只做「野任务清理」兜底工具（见 scripts/init.py 说明），不再建任务；
正常用 ql repo 订阅不需要调 init.py。

青龙「添加仓库」时的初始化命令填写：
  scripts/init.sh
"""

#!/usr/bin/env bash
set -e

# 定位仓库根目录：优先脚本所在目录；找不到 requirements.txt 则去 /ql/data/repo/<同名目录>
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ ! -f "$ROOT_DIR/requirements.txt" ]; then
  _REPO="/ql/data/repo/$(basename "$ROOT_DIR")"
  [ -f "$_REPO/requirements.txt" ] && ROOT_DIR="$_REPO"
fi
cd "$ROOT_DIR"

echo "[CT-Sign] 安装 Python 依赖..."
python3 -m pip install -r requirements.txt -q

echo "[CT-Sign] 依赖就绪。定时任务由 ql repo 白名单 sign_ 自动建出（每个平台一行任务）。"

# 把白名单建出的英文名任务（sign_xxx.py）重命名为中文友好名（如「3G壁纸 签到」）。
# 在青龙容器内运行，自动读取容器内 auth.json 令牌；拿不到令牌或出错则静默跳过，
# 不影响签到。失败也不中断 init.sh（set -e）。
echo "[CT-Sign] 将定时任务重命名为中文名..."
python3 scripts/rename_tasks.py || true
