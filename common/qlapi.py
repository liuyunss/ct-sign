"""青龙 OpenAPI 封装（可选进阶）。

- 在青龙容器内运行 init 时：自动用容器内部令牌（QL_PRIVATE_TOKEN）免 key 建任务。
- 在容器外运行（你电脑上）想远程建任务：配置 QL_URL + QL_CLIENT_ID/SECRET 换取令牌。
正常情况下你不需要碰这个文件；用 ql repo 订阅 + 容器内 init 即可免 key。
"""

from __future__ import annotations

import os
import json
import urllib.request
import urllib.parse


def _get_token():
    # 1) 容器内私有令牌
    token = os.environ.get("QL_PRIVATE_TOKEN")
    if token:
        return token
    # 2) 应用凭据换取
    cid = os.environ.get("QL_CLIENT_ID")
    csec = os.environ.get("QL_CLIENT_SECRET")
    if cid and csec:
        base = os.environ.get("QL_URL", "http://127.0.0.1:5700").rstrip("/")
        try:
            url = f"{base}/openapi/auth/token?client_id={urllib.parse.quote(cid)}&client_secret={urllib.parse.quote(csec)}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            return (data.get("data") or {}).get("token")
        except Exception:
            return None
    return None


def get_envs(search: str = ""):
    """列出青龙环境变量。返回 (list|None, error_msg)。"""
    base = os.environ.get("QL_URL", "http://127.0.0.1:5700").rstrip("/")
    token = _get_token()
    if not token:
        return None, "未检测到青龙 API 令牌（容器内自动获取失败且未配置 QL_*）"
    url = f"{base}/openapi/envs"
    if search:
        url += f"?search={urllib.parse.quote(search)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        return (data.get("data") or []), None
    except Exception as e:
        return None, str(e)


def update_env_value(name: str, value: str):
    """更新青龙环境变量；不存在则创建。返回 (ok, msg)。

    用于把登录刷新后的 Cookie 自动写回 CT_<平台>_COOKIE，
    下次运行直接走 Cookie，无需每次都登录。
    """
    envs, err = get_envs(name)
    if envs is None:
        return False, err or "读取环境变量失败"
    match = next((e for e in envs if e.get("name") == name), None)
    base = os.environ.get("QL_URL", "http://127.0.0.1:5700").rstrip("/")
    token = _get_token()
    if not token:
        return False, "未检测到青龙 API 令牌"
    if match:
        env_id = match.get("id")
        body = [{"id": env_id, "name": name, "value": value,
                 "remarks": match.get("remarks", "")}]
        url = f"{base}/openapi/envs"
        method = "PUT"
    else:
        body = [{"name": name, "value": value}]
        url = f"{base}/openapi/envs"
        method = "POST"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read())
        if resp.get("code") == 200:
            return True, "ok"
        return False, str(resp)
    except Exception as e:
        return False, str(e)


def create_cron(name, command, schedule="1 0 * * *"):
    """在青龙里创建一个定时任务。返回 (成功, 消息)。"""
    base = os.environ.get("QL_URL", "http://127.0.0.1:5700").rstrip("/")
    token = _get_token()
    if not token:
        return False, "未检测到青龙 API 令牌（容器内自动获取失败且未配置 QL_*）"
    body = [{
        "name": name,
        "command": command,
        "schedule": schedule,
        "task": True,
    }]
    url = f"{base}/openapi/crons"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return True, r.read().decode("utf-8", "ignore")
    except Exception as e:
        return False, str(e)
