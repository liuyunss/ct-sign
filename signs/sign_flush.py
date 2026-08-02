#!/usr/bin/env python3
"""CT-Sign 聚合推送 flush 任务（仅 CT_AGGREGATE_NOTIFY=1 时有效）。

用途：在「所有签到任务之后」用一个 cron 运行本任务，把当天攒在缓存里的
所有推送（本仓库 + 青龙里其他仓库经 send_notify 的内容）合并成一条发出，
再清空缓存。这样一天只收到一条汇总通知，而非每个任务各推一条。

关闭：不设置 CT_AGGREGATE_NOTIFY 或没攒到内容时，本任务直接退出、不推送。

青龙定时命令示例（cron 设在所有签到之后，如 23:30）：
  task sign_flush.py
"""

import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (ROOT, os.path.join(ROOT, "scripts")):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

# 青龙 ql repo 部署：白名单只把 sign_*.py 复制到 /ql/data/scripts/，
# common/ 等依赖留在 /ql/data/repo/<同名目录>，需扫描该目录定位真正的仓库根。
ql_repo = "/ql/data/repo"
if os.path.isdir(ql_repo):
    try:
        for _name in sorted(os.listdir(ql_repo)):
            _cand = os.path.join(ql_repo, _name)
            if os.path.isdir(os.path.join(_cand, "common")):
                for _p in (_cand, os.path.join(_cand, "scripts")):
                    if _p and _p not in sys.path:
                        sys.path.insert(0, _p)
    except OSError:
        pass

from common.notify_hook import flush_aggregated, ENABLED


if __name__ == "__main__":
    if not ENABLED:
        print("[flush] CT_AGGREGATE_NOTIFY 未开启，跳过聚合推送。")
        sys.exit(0)
    n = flush_aggregated()
    print(f"[flush] 已合并推送 {n} 条缓存通知并清空。")
