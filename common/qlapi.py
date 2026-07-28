"""青龙 OpenAPI 封装（可选进阶）。

- 在青龙容器内运行 init 时：自动用容器内部令牌（QL_PRIVATE_TOKEN）免 key 建任务。
- 在容器外运行（你电脑上）想远程建任务：配置 QL_URL + QL_CLIENT_ID/SECRET 换取令牌。
正常情况下你不需要碰这个文件；用 ql repo 订阅 + 容器内 init 即可免 key。
"""

from __future__ import annotations

import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error


def _http_err_msg(e):
    """把 urllib HTTPError 转成带响应体的可读信息，便于排查（如权限 400）。"""
    try:
        body = e.read().decode("utf-8", "ignore")
    except Exception:
        body = ""
    return f"HTTP {getattr(e, 'code', '?')}: {body}"


def _get_token():
    # 1) 容器内私有令牌（兼容多种环境变量名）
    for env in ("QL_PRIVATE_TOKEN", "QL_TOKEN"):
        token = os.environ.get(env)
        if token:
            return token
    # 2) 应用凭据换取
    cid = os.environ.get("QL_CLIENT_ID")
    csec = os.environ.get("QL_CLIENT_SECRET")
    if cid and csec:
        base = os.environ.get("QL_URL", "http://127.0.0.1:5700").rstrip("/")
        try:
            url = f"{base}/open/auth/token?client_id={urllib.parse.quote(cid)}&client_secret={urllib.parse.quote(csec)}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            token = (data.get("data") or {}).get("token")
            if token:
                return token
            # 拿到了响应但没有 token 字段（异常结构），提示出来而非静默失败
            print(f"[CT-Sign] qlapi: /open/auth/token 返回但无 token 字段: {data}",
                  file=sys.stderr)
        except urllib.error.HTTPError as e:
            print(f"[CT-Sign] qlapi: 获取 token 失败 {_http_err_msg(e)}",
                  file=sys.stderr)
        except Exception as e:
            print(f"[CT-Sign] qlapi: 获取 token 异常: {e}", file=sys.stderr)
        return None
    # 3) 读取青龙容器内 auth.json（最稳，容器里一定存在）
    #    兼容多种结构：token 为字符串；tokens 为 {client_id: token} 映射时取首个值
    for path in ("/ql/config/auth.json", "/ql/data/config/auth.json"):
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            tok = data.get("token")
            if isinstance(tok, str) and tok:
                return tok
            tokens = data.get("tokens")
            if isinstance(tokens, dict) and tokens:
                first = next(iter(tokens.values()))
                if isinstance(first, str) and first:
                    return first
            elif isinstance(tokens, str) and tokens:
                return tokens
        except Exception:
            pass
    return None


def get_envs(search: str = ""):
    """列出青龙环境变量。返回 (list|None, error_msg)。"""
    base = os.environ.get("QL_URL", "http://127.0.0.1:5700").rstrip("/")
    token = _get_token()
    if not token:
        return None, "未检测到青龙 API 令牌（容器内自动获取失败且未配置 QL_*）"
    url = f"{base}/open/envs"
    if search:
        url += f"?search={urllib.parse.quote(search)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        return (data.get("data") or []), None
    except urllib.error.HTTPError as e:
        return None, _http_err_msg(e)
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
        url = f"{base}/open/envs"
        method = "PUT"
    else:
        body = [{"name": name, "value": value}]
        url = f"{base}/open/envs"
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
    except urllib.error.HTTPError as e:
        return False, _http_err_msg(e)
    except Exception as e:
        return False, str(e)


def create_cron(name, command, schedule="1 0 * * *", remark=""):
    """在青龙里创建一个定时任务。返回 (成功, 消息)。"""
    base = os.environ.get("QL_URL", "http://127.0.0.1:5700").rstrip("/")
    token = _get_token()
    if not token:
        return False, "未检测到青龙 API 令牌（容器内自动获取失败且未配置 QL_*）"
    body = [{
        "name": name,
        "command": command,
        "schedule": schedule,
        "remark": remark,
        "task": True,
    }]
    url = f"{base}/open/crons"
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


def list_crons():
    """列出青龙所有定时任务。返回 (list|None, error_msg)。"""
    base = os.environ.get("QL_URL", "http://127.0.0.1:5700").rstrip("/")
    token = _get_token()
    if not token:
        return None, "未检测到青龙 API 令牌"
    url = f"{base}/open/crons"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        return (data.get("data") or []), None
    except urllib.error.HTTPError as e:
        return None, _http_err_msg(e)
    except Exception as e:
        return None, str(e)


def delete_cron(cron_id):
    """删除一个定时任务。返回 (ok, msg)。"""
    base = os.environ.get("QL_URL", "http://127.0.0.1:5700").rstrip("/")
    token = _get_token()
    if not token:
        return False, "未检测到青龙 API 令牌"
    url = f"{base}/open/crons"
    body = [cron_id]
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read())
        if resp.get("code") == 200:
            return True, "ok"
        return False, str(resp)
    except urllib.error.HTTPError as e:
        return False, _http_err_msg(e)
    except Exception as e:
        return False, str(e)


def cron_exists(name):
    """是否已存在同名定时任务。"""
    crons, err = list_crons()
    if crons is None:
        return False
    return any((c.get("name") == name) for c in crons)
