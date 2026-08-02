#!/usr/bin/env python3
"""CT-Sign 平台签到入口 —— Hyperdown。

由 ql repo 白名单 sign_ 直接建成青龙定时任务（一行一任务，青龙原生日志）。
此文件由仓库提供，请勿手改；新增平台时复制本文件、把 main() 的平台 key 改成目录名即可。
"""

import os
import sys


def _resolve_repo_root():
    """定位仓库根目录。

    - 本地开发：本文件在 <repo>/signs/ 或 <repo>/，父目录即仓库根。
    - 青龙 ql repo 部署：白名单只把 sign_*.py 复制到 /ql/data/scripts/，
      依赖（scripts/、common/、platforms/）留在 /ql/data/repo/<同名目录>，
      需扫描该目录定位真正的仓库根。
    """
    here = os.path.dirname(os.path.realpath(__file__))
    candidates = [here, os.path.dirname(here)]
    ql_repo = "/ql/data/repo"
    if os.path.isdir(ql_repo):
        try:
            for _name in sorted(os.listdir(ql_repo)):
                candidates.append(os.path.join(ql_repo, _name))
        except OSError:
            pass
    for _c in candidates:
        if os.path.isdir(os.path.join(_c, "common")) and os.path.isdir(os.path.join(_c, "platforms")):
            return _c
    return candidates[0]


REPO_ROOT = _resolve_repo_root()
for _p in (REPO_ROOT, os.path.join(REPO_ROOT, "scripts")):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.run_platform import main

if __name__ == "__main__":
    main("hyperdown")
