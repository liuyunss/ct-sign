"""通知：把签到结果推送出去。

优先级：
  1) 优先走**青龙自带通知** `send_notify`（用户在青龙面板配置好的通道，
     仓库变动通知也是走这条）——只要脚本在青龙里跑，签到结果就走同一通道，
     不用再单独配 Server酱/Pushplus 等。
  2) 非青龙环境（本地调试）时，若配置了脚本内直推渠道（Server酱/Pushplus/Bark/
     企业微信/钉钉）则直推一次作为兜底；都没配就只打印到日志。

关闭：设置环境变量 CT_DISABLE_NOTIFY=1 可禁用推送（仅打印日志）。
"""

from __future__ import annotations

import os
import sys
import json
import urllib.request
import urllib.parse

from .log import logger


def _disabled():
    return os.environ.get("CT_DISABLE_NOTIFY", "").strip() in ("1", "true", "True", "yes", "YES")


def _post_json(url, payload, timeout=10):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore")
    except Exception as e:  # best-effort
        logger.warning("通知直推失败: %s", e)
        return ""


def _push(title, content):
    # Server酱
    sckey = os.environ.get("PUSH_KEY") or os.environ.get("SERVERCHAN_SCKEY")
    if sckey:
        _post_json(f"https://sctapi.ftqq.com/{sckey}.send",
                   {"title": title, "desp": content})
    # Pushplus（项目前缀变量）
    pushplus = os.environ.get("CT_PUSHPLUS_TOKEN")
    if pushplus:
        _post_json("https://www.pushplus.plus/send",
                   {"token": pushplus, "title": title, "content": content})
    # Bark
    bark = os.environ.get("BARK_PUSH")
    if bark:
        _post_json(f"{bark.rstrip('/')}/push", {"title": title, "body": content})
    # 企业微信机器人
    qywx = os.environ.get("QYWX_KEY") or os.environ.get("QYWX_ROBOT_KEY")
    if qywx:
        _post_json(f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={qywx}",
                   {"msgtype": "text", "text": {"content": f"{title}\n{content}"}})
    # 钉钉机器人
    ding = os.environ.get("DD_BOT_TOKEN")
    if ding:
        _post_json(f"https://oapi.dingtalk.com/robot/send?access_token={ding}",
                   {"msgtype": "text", "text": {"content": f"{title}\n{content}"}})


def _qinglong_send(title, content) -> bool:
    """尝试调用青龙自带通知 send_notify（复用青龙面板已配的通道）。

    青龙拉取的任务运行时，会把系统 notify 模块（含 send_notify）注入到
    sys.modules / sys.path。优先直接 import；若失败，再尝试把常见所在目录
    （/ql/data/scripts、/ql/data/repo/<仓库名>）补进 sys.path 后导入。
    这与 hex-ci/smzdm_script、smallfawn/QLScriptPublic 等仓库调用青龙
    send_notify 的方式一致——它们都只调一次 send_notify 即可复用面板渠道。
    """
    def _try_import():
        try:
            from notify import send_notify  # 青龙自带 notify 模块
            return send_notify
        except Exception:
            return None

    send_notify = _try_import()
    if send_notify is None:
        # 青龙任务进程的工作目录可能不是 /ql/data/scripts，手动补路径
        import glob
        added = []
        candidates = ["/ql/data/scripts", "/ql/data"]
        candidates += glob.glob("/ql/data/repo/*")
        for d in candidates:
            if os.path.isdir(d) and d not in sys.path:
                sys.path.insert(0, d)
                added.append(d)
        try:
            send_notify = _try_import()
        finally:
            for d in added:
                if d in sys.path:
                    sys.path.remove(d)
    if send_notify is None:
        logger.debug("未检测到青龙自带 notify 模块，改用脚本内直推兜底")
        return False
    try:
        send_notify(title, content)
        return True
    except Exception as e:
        logger.warning("青龙 send_notify 调用失败（%s），改用脚本内直推兜底", e)
        return False


def _random_quote() -> str:
    """随机一句话彩蛋（一言 API）。拉取失败则用本地预置文案，绝不阻塞推送。

    关闭：环境变量 CT_DISABLE_QUOTE=1 则不附加彩蛋。
    """
    if os.environ.get("CT_DISABLE_QUOTE", "").strip() in ("1", "true", "True", "yes", "YES"):
        return ""
    fallback = [
        "签到一时爽，一直签到一直爽。",
        "今天的努力，是明天流量的底气。",
        "坚持每日签到，流量不请自来。",
        "种一棵树最好的时间是十年前，其次是每天签到。",
        "自律即自由，签到即习惯。",
    ]
    try:
        req = urllib.request.Request(
            "https://v1.hitokoto.cn/",
            headers={"User-Agent": "CT-Sign/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        hit = (data.get("hitokoto") or "").strip()
        src = (data.get("from") or "").strip()
        if hit:
            return f"{hit}" + (f" —— {src}" if src else "")
    except Exception as e:
        logger.debug("一言获取失败，使用本地兜底文案: %s", e)
    import random
    return random.choice(fallback)


def notify(title, content):
    # 0) 聚合模式：本仓库自身也只写缓存，由 flush 任务统一推送
    if os.environ.get("CT_AGGREGATE_NOTIFY", "").strip() in ("1", "true", "True", "yes", "YES"):
        try:
            from .notify_hook import _write_cache
            _write_cache(title, content, source="ct-sign")
        except Exception:
            pass
        print(f"\n==== {title} ====\n{content}\n")
        return

    # 1) 始终打印，保证任务日志里有完整结果（青龙也会抓取日志）
    print(f"\n==== {title} ====\n{content}\n")

    if _disabled():
        logger.info("CT_DISABLE_NOTIFY 已设置，跳过推送（仅打印日志）")
        return

    # 1.5) 拼接随机彩蛋（不影响主内容，仅展示用）
    quote = _random_quote()
    if quote:
        content = f"{content}\n\n—— {quote}"

    # 2) 优先走青龙自带通知（用户已在青龙配置好通道）
    if _qinglong_send(title, content):
        return

    # 3) 非青龙环境：脚本内直推渠道兜底
    try:
        _push(title, content)
    except Exception as e:
        logger.warning("直推异常: %s", e)
