"""init.py：读取所有平台，在青龙里自动创建定时任务（被 init.sh 调用）。

- 容器内：自动获取青龙内部令牌，免 key 建任务。
- 容器外：无令牌则跳过建任务，仅做配置校验 + 提示。

任务计划（cron）可用环境变量 CT_CRON 覆盖，默认每天 00:01（1 0 * * *）。
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from common.config import load_global_config
from common.loader import discover, load_platform
from common.qlapi import create_cron

SCHEDULE = os.environ.get("CT_CRON", "1 0 * * *")


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
        platform = signers[0].platform
        ok, msg = create_cron(f"CT-Sign {platform} 签到",
                              f"task run_platform.py {name}", SCHEDULE)
        state = "OK" if ok else "SKIP"
        print(f"[{state}] 建任务 {platform}：{msg}")
        if ok:
            created += 1

    ok, msg = create_cron("CT-Sign 全部签到", "task run_all.py", SCHEDULE)
    state = "OK" if ok else "SKIP"
    print(f"[{state}] 建任务 全部签到：{msg}")
    if ok:
        created += 1

    if created == 0:
        print("\n提示：当前环境未检测到青龙 API 令牌，已跳过建任务。"
              "请用 ql repo 订阅本仓库并在容器内运行 init.sh，即可自动建任务；"
              "或手动在青龙「定时任务」按文档建任务。")


if __name__ == "__main__":
    main()
