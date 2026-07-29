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
    """尝试调用青龙自带通知 send_notify（复用青龙面板已配的通道）。"""
    # 青龙系统 notify 模块通常位于 /ql/data/scripts/notify.py，
    # 任务运行时该目录未必在 sys.path，这里手动补上再导入。
    added = []
    for d in ("/ql/data/scripts", "/ql/data"):
        if os.path.isdir(d) and d not in sys.path:
            sys.path.insert(0, d)
            added.append(d)
    try:
        from notify import send_notify  # 青龙自带 notify 模块
    except Exception as e:
        logger.debug("未检测到青龙自带 notify 模块（%s），改用脚本内直推兜底", e)
        return False
    finally:
        for d in added:
            if d in sys.path:
                sys.path.remove(d)
    try:
        send_notify(title, content)
        return True
    except Exception as e:
        logger.warning("青龙 send_notify 调用失败（%s），改用脚本内直推兜底", e)
        return False


def notify(title, content):
    # 1) 始终打印，保证任务日志里有完整结果（青龙也会抓取日志）
    print(f"\n==== {title} ====\n{content}\n")

    if _disabled():
        logger.info("CT_DISABLE_NOTIFY 已设置，跳过推送（仅打印日志）")
        return

    # 2) 优先走青龙自带通知（用户已在青龙配置好通道）
    if _qinglong_send(title, content):
        return

    # 3) 非青龙环境：脚本内直推渠道兜底
    try:
        _push(title, content)
    except Exception as e:
        logger.warning("直推异常: %s", e)
