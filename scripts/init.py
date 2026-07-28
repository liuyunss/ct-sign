"""init.py：清理 ql repo / 旧订阅误建的野任务（手动兜底工具）。

【推荐】日常用 ql repo 白名单 sign_ 订阅（见 README），青龙会把每个 sign_<平台>.py
直接建成一行定时任务，无需本脚本、也不依赖青龙 API 令牌，天然无野任务。

本脚本仅用于「手动兜底清理」：当某些原因（旧黑名单命令、手动误操作）在青龙里残留了
xxx.py / __init__.py / common/*.py / scripts/*.py / init.py 这类文件名式野任务时，
在青龙容器内运行 `python3 scripts/init.py` 即可把它们清掉。

用法：
  python3 scripts/init.py            # 清理野任务（默认）
  python3 scripts/init.py --dry-run  # 只列出会清理的，不删除
  python3 scripts/init.py --clean    # 同默认（显式写法）

安全边界：本脚本只清理「本仓库目录内、引用 .py 且不是 sign_ 入口」的任务，
不会动你其它仓库或无关任务。
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from common.qlapi import list_crons, delete_cron

PREFIX = "CT-Sign"
# 青龙里本仓库的目录名（如 liuyunss_ct-sign_master）；只清理这个目录下的野任务
REPO_DIR = os.path.basename(ROOT)

# 已知内部文件名兜底（仅当出现在本仓库目录内时才算野任务）
STRAY_HINTS = ("scripts/run_platform.py", "scripts/run_all.py", "scripts/init.py",
               "init.py", "__init__.py", "common/", "engines/")


def _is_stray(task: dict) -> bool:
    """判断一个定时任务是不是本仓库误建的野任务（非 sign_*.py 入口）。

    判定顺序（越靠前越安全）：
      1) 我们自己建的 PREFIX 任务 → 保留；
      2) 命令含 sign_ 入口 → 合法任务，保留；
      3) 不属于本仓库目录 → 不动（避免误删其它仓库/无关任务）；
      4) 本仓库目录内、引用了 .py 且不是 sign_ 入口 → 野任务；
      5) 已知内部文件名兜底。
    """
    name = task.get("name", "")
    cmd = task.get("command", "")
    if name.startswith(PREFIX):
        return False
    if "sign_" in cmd:
        return False
    if not REPO_DIR or REPO_DIR not in cmd:
        return False
    if ".py" in cmd:
        return True
    return any(h in cmd for h in STRAY_HINTS)


def cleanup_stray(dry_run: bool = False) -> int:
    """清理本仓库误建的野任务，返回删除数量。"""
    crons, err = list_crons()
    if crons is None:
        print(f"[提示] 无法列出任务（{err}），跳过清理。")
        print("        请在青龙容器内运行本脚本（需要能读取青龙 API 令牌）。")
        return 0
    targets = [t for t in crons if _is_stray(t)]
    if not targets:
        print("[清理] 未发现本仓库的野任务，无需清理。")
        return 0
    removed = 0
    for t in targets:
        label = f"{t.get('name')}  ->  {t.get('command')}"
        if dry_run:
            print(f"[将清理] {label}")
            removed += 1
            continue
        ok, _ = delete_cron(t.get("id"))
        if ok:
            removed += 1
            print(f"[已清理] {label}")
        else:
            print(f"[失败] 删除失败：{label}")
    if dry_run:
        print(f"[清理] 预览：将清理 {removed} 个野任务（--dry-run 不实际删除）")
    else:
        print(f"[清理] 共清理 {removed} 个野任务")
    return removed


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    print(f"[CT-Sign] 野任务清理（仓库目录：{REPO_DIR}）")
    if dry_run:
        print("[CT-Sign] 预览模式：仅列出，不删除")
    cleanup_stray(dry_run=dry_run)


if __name__ == "__main__":
    main()
