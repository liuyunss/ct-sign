"""通知：默认打印摘要（青龙自带通知会抓取任务日志推送），
可选脚本内直推到 Server酱 / Pushplus / Bark / 企业微信 / 钉钉（不配则不推）。
"""

from __future__ import annotations

import os
import json
import urllib.request
import urllib.parse

from .log import logger


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


def notify(title, content):
    # 1) 打印，青龙自带通知会抓取任务日志推送
    print(f"\n==== {title} ====\n{content}\n")
    # 2) 若配置了直推渠道，额外推一次（best-effort）
    try:
        _push(title, content)
    except Exception as e:
        logger.warning("直推异常: %s", e)
