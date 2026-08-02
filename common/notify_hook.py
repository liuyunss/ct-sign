"""通知聚合 hook（可选，默认关闭）。

目的：**在不修改别人脚本代码的前提下，把本仓库及青龙里其他仓库的推送
攒成「一天一批」**——所有调用青龙 send_notify 的内容先写缓存，由一个
独立的「flush 任务」在当天结束时统一推送一次，再清空缓存。

为什么能覆盖「别人的脚本」：青龙里所有 Python 任务最终都调用同一个
系统 notify 模块里的 send_notify（位于 /ql/data/scripts/notify.py）。
我们在 init.sh 里 import 本模块并 install()，monkeypatch 掉这个
send_notify，把它变成「写缓存」。别人的脚本照常 `from notify import
send_notify` 调用，但调用已被我们接管，内容进入缓存而非立即发出。

开关：环境变量 CT_AGGREGATE_NOTIFY=1 才启用；不设置则完全不生效，
青龙 send_notify 保持原样（别人的脚本各自推送，互不影响）。

flush 任务：signs/sign_flush.py（cron 设在所有签到任务之后），
调用 flush_aggregated() 推送并清空缓存。

注意：聚合模式下，所有走 send_notify 的推送（含本仓库、其他仓库）都会
延迟到 flush 任务才发出。如果你希望某些任务立即发，不要启用聚合。
"""

from __future__ import annotations

import json
import os
import sys
import time

CACHE_FILE = "/ql/data/ct_sign_cache.jsonl"
ENABLED = os.environ.get("CT_AGGREGATE_NOTIFY", "").strip() in ("1", "true", "True", "yes", "YES")

_original_send = None


def _write_cache(title: str, content: str, source: str = "unknown") -> None:
    try:
        with open(CACHE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": int(time.time()),
                "title": title,
                "content": content,
                "source": source,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _patched_send_notify(title, content):
    """替代青龙 send_notify：只写缓存，不真正发送。"""
    _write_cache(title, content, source="send_notify")
    return None


def install() -> bool:
    """monkeypatch 青龙 notify.send_notify 为缓存模式。成功返回 True。"""
    global _original_send
    if not ENABLED:
        return False
    if _original_send is not None:
        return True  # 已安装
    candidates = ["/ql/data/scripts", "/ql/data"]
    import glob
    candidates += glob.glob("/ql/data/repo/*")
    added = []
    for d in candidates:
        if os.path.isdir(d) and d not in sys.path:
            sys.path.insert(0, d)
            added.append(d)
    try:
        import notify as ql_notify  # 青龙系统 notify 模块
    except Exception:
        return False
    finally:
        for d in added:
            if d in sys.path:
                sys.path.remove(d)
    if not hasattr(ql_notify, "send_notify"):
        return False
    _original_send = ql_notify.send_notify
    ql_notify.send_notify = _patched_send_notify
    # 同时让后续 `from notify import send_notify` 拿到的是 patch 后的
    sys.modules["notify"] = ql_notify
    return True


def flush_aggregated() -> int:
    """读取缓存、合并推送、清空。返回推送条数（缓存中记录数）。"""
    if not os.path.exists(CACHE_FILE):
        return 0
    lines = []
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    lines.append(json.loads(ln))
                except Exception:
                    pass
    if not lines:
        return 0

    # 合并成一条推送
    blocks = []
    for item in lines:
        blocks.append(f"【{item.get('title', '')}】\n{item.get('content', '')}")
    merged = "\n\n".join(blocks)
    count = len(lines)

    # 复用本仓库 notify 真正发出（此时 _qinglong_send 会调用原始 send_notify）
    # 为避免递归，临时恢复原始实现
    try:
        from .notify import _qinglong_send, _disabled
        if not _disabled() and _original_send is not None:
            # 直接调用原始青龙 send_notify（绕过缓存 patch）
            _original_send("CT-Sign 聚合通知", merged)
    except Exception:
        pass

    # 清空缓存
    try:
        os.remove(CACHE_FILE)
    except Exception:
        pass
    return count
