"""init.py：读取所有平台，在青龙里自动创建定时任务（被 init.sh 调用）。

- 容器内：自动获取青龙内部令牌，免 key 建任务。
- 容器外：无令牌则跳过建任务，仅做配置校验 + 提示。

任务计划（cron）可用环境变量 CT_CRON 覆盖，默认每天 00:01（1 0 * * *）。

任务命名统一前缀「CT-Sign」，并显示中文平台名，便于在青龙定时任务界面一眼分辨。
同时会自动清理 ql repo 订阅时误建的「文件名式」野任务（如 run_all.py、init.py 等）。
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from common.config import load_global_config
from common.loader import discover, load_platform
from common.qlapi import create_cron, list_crons, delete_cron, cron_exists

SCHEDULE = os.environ.get("CT_CRON", "1 0 * * *")
PREFIX = "CT-Sign"

# 文件夹名 -> 中文显示名（让定时任务名字一眼能看懂）
DISPLAY = {
    "fuelba": "福利吧",
    "gopojie": "狗破解",
    "kxdao": "科学刀",
    "youjiaoku": "幼教库",
    "pinggu": "经管之家",
    "3gbizhi": "3G壁纸",
}

# ql repo 订阅会自动把仓库里的 .py 当成任务建出来（名字是文件名），这些是要清理的野任务特征
STRAY_HINTS = ("run_platform.py", "run_all.py", "init.py", "common/")


def _is_stray(task: dict) -> bool:
    """判断一个定时任务是不是 ql repo 误建的野任务（非我们 CT-Sign 管理的）。"""
    name = task.get("name", "")
    cmd = task.get("command", "")
    if name.startswith(PREFIX):
        return False  # 我们自己建的，保留
    return any(h in cmd for h in STRAY_HINTS)


def cleanup_stray() -> int:
    """清理 ql repo 误建的野任务，返回删除数量。"""
    crons, err = list_crons()
    if crons is None:
        print(f"[提示] 无法列出任务（{err}），跳过清理野任务。")
        return 0
    removed = 0
    for t in crons:
        if _is_stray(t):
            ok, _ = delete_cron(t.get("id"))
            if ok:
                removed += 1
                print(f"[清理] 删除野任务：{t.get('name')}  ->  {t.get('command')}")
    if removed:
        print(f"[清理] 共删除 {removed} 个野任务")
    return removed


def _remark_for(signer) -> str:
    login_cfg = (signer.task_cfg or {}).get("login", {}) or {}
    envs = []
    if signer.cookie_env:
        envs.append(signer.cookie_env)
    if login_cfg.get("auth_env"):
        envs.append(login_cfg["auth_env"])
    return "变量：" + " / ".join(envs) if envs else ""


def main():
    load_global_config()
    names = discover()
    if not names:
        print("未发现任何平台（platforms/ 下需有 <平台>/config.yml）")
        return

    created = 0
    for name in names:
        signers = load_platform(name)
        if not signers:
            continue
        signer = signers[0]
        disp = DISPLAY.get(name, signer.platform)
        task_name = f"{PREFIX} {disp} 签到"
        if cron_exists(task_name):
            print(f"[跳过] 已存在同名任务：{task_name}")
            continue
        ok, msg = create_cron(
            task_name,
            f"task run_platform.py {name}",
            SCHEDULE,
            remark=_remark_for(signer),
        )
        state = "OK" if ok else "SKIP"
        print(f"[{state}] 建任务 {disp}：{msg}")
        if ok:
            created += 1

    all_name = f"{PREFIX} 全部签到"
    if not cron_exists(all_name):
        ok, msg = create_cron(all_name, "task run_all.py", SCHEDULE,
                               remark="一次性签到所有平台")
        state = "OK" if ok else "SKIP"
        print(f"[{state}] 建任务 全部签到：{msg}")
        if ok:
            created += 1

    # 清理 ql repo 误建的野任务（run_all.py / init.py 等文件名任务）
    cleanup_stray()

    if created == 0:
        print("\n提示：当前环境未检测到青龙 API 令牌，已跳过建任务。"
              "请用 ql repo 订阅本仓库并在容器内运行 init.sh，即可自动建任务；"
              "或手动在青龙「定时任务」按文档建任务。")


if __name__ == "__main__":
    main()
