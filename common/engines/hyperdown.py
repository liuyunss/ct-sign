"""Hyperdown 引擎。

适用于 https://hyperdown.net 的每日签到：
- 登录：POST /api/v1/auth/login（邮箱+密码 JSON），返回 access_token / refresh_token
- 查询：GET /api/v1/me/，返回 user.is_check_in 等字段
- 签到：POST /api/v1/me/checkins，请求体经 SealJSON 加密（ECDH+HKDF+XChaCha20+HMAC）

与框架的契合点：
- 凭证变量 CT_HYPERDOWN_AUTH（一体化 `token||邮箱||密码`）或 CT_HYPERDOWN_COOKIE（纯 token）
- _login(邮箱, 密码) 返回 access_token 字符串（框架视为 cookie）
- _run_one(token) 用 token 查询+签到

依赖：cryptography、PyNaCl
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import ssl
import time
import urllib.error
import urllib.request
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

try:
    from nacl.bindings import (
        crypto_aead_xchacha20poly1305_ietf_encrypt,
        crypto_scalarmult,
    )
except ImportError as exc:  # pragma: no cover
    raise SystemExit("缺少 PyNaCl: pip install pynacl cryptography") from exc

from ..base import BaseSigner, SignResult
from ..login import LoginError

# ── Secure API (seal_json) ──────────────────────────────────────────────

_PEER_PUB_HEX = (
    "dd85f63f107a32ce3def4835fe56c27865a1557fedad19adbd72ff81ea2e1025"
)
SALT_PREFIX = b"hyperdown-secure-api:v1:"
SECURE_HEADER = "v1"

KDF_VARIANT = os.environ.get("HYPERDOWN_KDF_VARIANT", "ecdh_re_primary")
SIGN_VARIANT = os.environ.get("HYPERDOWN_SIGN_VARIANT", "v3_token_nul")
B64_VARIANT = os.environ.get("HYPERDOWN_B64_VARIANT", "rawurl")
SIGN_SEP = os.environ.get("HYPERDOWN_SIGN_SEP", "nul")


def _peer_pub() -> bytes:
    return bytes.fromhex(
        os.environ.get("HYPERDOWN_SECURE_PEER_PUB")
        or os.environ.get("HYPERDOWN_SECURE_MASTER_KEY")
        or _PEER_PUB_HEX
    )


def _b64(data: bytes) -> str:
    if B64_VARIANT == "rawurl":
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
    if B64_VARIANT == "std":
        return base64.standard_b64encode(data).decode()
    if B64_VARIANT == "rawstd":
        return base64.standard_b64encode(data).rstrip(b"=").decode()
    raise ValueError(B64_VARIANT)


def _norm(path: str) -> str:
    path = (path or "").split("?", 1)[0]
    if not path:
        return "/"
    if not path.startswith("/"):
        path = "/" + path
    return path


def _is_sensitive(method: str, path: str) -> bool:
    if method.upper() != "POST":
        return False
    return _norm(path) in {
        "/api/v1/me/checkins",
        "/api/v1/redemptions/redeem",
        "/api/v1/shares/parse",
        "/api/v1/shares/downloads/resolve",
        "/api/v1/downloads/resolve",
        "/api/code/redeem",
    }


def _aad(method: str, path: str, ts: int, request_id: str) -> bytes:
    return f"{method.upper()}\n{_norm(path)}\n{request_id}\n{ts}".encode()


def _ecdh_shared() -> tuple[bytes, str]:
    eph = x25519.X25519PrivateKey.generate()
    eph_priv = eph.private_bytes_raw()
    eph_pub = eph.public_key().public_bytes_raw()
    shared = crypto_scalarmult(eph_priv, _peer_pub())
    return shared, eph_pub.hex()


def _derive_key(ikm: bytes, method: str, path: str, ts: int, request_id: str) -> bytes:
    method_u = method.upper()
    path_n = _norm(path)
    v = KDF_VARIANT
    if v in ("ecdh_re_primary", "re_primary"):
        material = f"{request_id}:{ts}".encode()
        salt = hashlib.sha256(material).digest()
        info = SALT_PREFIX + f"{method_u}:{path_n}".encode()
        return HKDF(hashes.SHA256(), 32, salt, info).derive(ikm)
    if v == "ecdh_raw":
        return ikm if len(ikm) == 32 else hashlib.sha256(ikm).digest()
    if v == "ecdh_sha256":
        return hashlib.sha256(ikm).digest()
    if v == "ecdh_ts_first":
        material = f"{ts}:{request_id}".encode()
        salt = hashlib.sha256(material).digest()
        info = SALT_PREFIX + f"{method_u}:{path_n}".encode()
        return HKDF(hashes.SHA256(), 32, salt, info).derive(ikm)
    raise ValueError(v)


def _sep() -> bytes:
    return b"\x00" if SIGN_SEP == "nul" else b"\n"


def _sign_msg(method, path, ts, request_id, nonce_field, pub,
              ciphertext, access_token="") -> bytes:
    method_u = method.upper()
    path_n = _norm(path)
    sep = _sep()
    v = SIGN_VARIANT

    def join(parts):
        return sep.join(p.encode() for p in parts)

    if v == "v3_token_nul":
        return join(["v1", method_u, path_n, request_id, str(ts),
                     nonce_field, pub, ciphertext, access_token or ""])
    if v == "v3_token_bearer":
        return join(["v1", method_u, path_n, request_id, str(ts),
                     nonce_field, pub, ciphertext,
                     f"Bearer {access_token}" if access_token else ""])
    if v == "v3_token_early":
        return join(["v1", method_u, path_n, access_token or "",
                     request_id, str(ts), nonce_field, pub, ciphertext])
    if v == "v2_nul_full":
        return join(["v1", method_u, path_n, request_id, str(ts),
                     nonce_field, pub, ciphertext])
    raise ValueError(v)


def seal_json(method: str, path: str, body=None, *, ts=None,
              access_token: str = "") -> tuple[dict, dict]:
    if body is None:
        plaintext = b"{}"
    elif isinstance(body, (dict, list)):
        plaintext = json.dumps(body, separators=(",", ":"),
                               ensure_ascii=False).encode()
    elif isinstance(body, str):
        plaintext = body.encode()
    else:
        plaintext = body
    if not plaintext:
        plaintext = b"{}"

    ts = int(time.time()) if ts is None else int(ts)
    request_id = secrets.token_hex(16)
    aead_nonce = secrets.token_bytes(24)

    method_u = method.upper()
    path_n = _norm(path)

    shared, pub_hex = _ecdh_shared()
    key = _derive_key(shared, method_u, path_n, ts, request_id)
    aad = _aad(method_u, path_n, ts, request_id)
    sealed = crypto_aead_xchacha20poly1305_ietf_encrypt(
        plaintext, aad, aead_nonce, key)

    nonce_field = _b64(aead_nonce)
    ct_field = _b64(sealed)
    msg = _sign_msg(method_u, path_n, ts, request_id, nonce_field,
                    pub_hex, ct_field, access_token=access_token)
    sig = _b64(hmac.new(key, msg, hashlib.sha256).digest())

    envelope = {
        "v": "v1", "request_id": request_id, "ts": ts,
        "nonce": nonce_field, "pub": pub_hex,
        "ciphertext": ct_field, "sign": sig,
    }
    return envelope, {"X-Hyperdown-Secure": SECURE_HEADER}


# ── HTTP Client ─────────────────────────────────────────────────────────

DEFAULT_UA = "Go-http-client/1.1"
DEFAULT_BASE = "https://hyperdown.net/api/v1"


class _APIError(Exception):
    def __init__(self, code: str, message: str,
                 status: int | None = None, raw: Any = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status = status
        self.raw = raw


def _request(method: str, path: str, *, base_url: str = DEFAULT_BASE,
             ua: str = DEFAULT_UA, proxy: str = "",
             access_token: str = "", body=None, auth: bool = True,
             secure: bool | None = None, timeout: float = 30.0) -> Any:
    method = method.upper()
    path = path if path.startswith("/") else "/" + path
    url = base_url.rstrip("/") + path

    headers = {
        "User-Agent": ua,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if auth and access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    full_path = path if path.startswith("/api/") else "/api/v1" + (
        path if path.startswith("/") else "/" + path)
    use_secure = (_is_sensitive(method, full_path) if secure is None
                  else secure)

    raw_body: bytes | None = None
    if use_secure:
        token = access_token if auth else ""
        envelope, extra = seal_json(method, full_path, body,
                                    access_token=token or "")
        headers.update(extra)
        raw_body = json.dumps(envelope, separators=(",", ":")).encode()
    elif body is not None:
        if isinstance(body, (bytes, bytearray)):
            raw_body = bytes(body)
        else:
            raw_body = json.dumps(body, separators=(",", ":")).encode()

    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler(
            {"http": proxy, "https": proxy}))
    handlers.append(urllib.request.HTTPSHandler(
        context=ssl.create_default_context()))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, data=raw_body, method=method,
                                 headers=headers)
    try:
        with opener.open(req, timeout=timeout) as resp:
            text = resp.read().decode()
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")
        status = e.code
    except urllib.error.URLError as e:
        raise _APIError("network_error", str(e.reason or e), None) from e

    try:
        payload = json.loads(text) if text else {}
    except json.JSONDecodeError as e:
        raise _APIError("invalid_json", text[:200], status) from e

    if isinstance(payload, dict) and payload.get("ok") is False:
        err = payload.get("error") or {}
        raise _APIError(str(err.get("code") or "error"),
                        str(err.get("message") or text), status, payload)
    if status >= 400:
        raise _APIError("http_error", text[:200], status, payload)

    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def _absorb_tokens(data: Any) -> tuple[str, str]:
    """从登录响应提取 (access_token, refresh_token)。"""
    if not isinstance(data, dict):
        return "", ""
    for key in ("tokens", "token", "auth"):
        nested = data.get(key)
        if isinstance(nested, dict) and (nested.get("access_token")
                                         or nested.get("refresh_token")):
            return (str(nested.get("access_token") or ""),
                    str(nested.get("refresh_token") or ""))
    return (str(data.get("access_token") or ""),
            str(data.get("refresh_token") or ""))


def _fmt_bytes(n) -> str:
    if n is None:
        return "?"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    return f"{n:.2f} {units[i]}"


# ── Signer ──────────────────────────────────────────────────────────────

class HyperdownSigner(BaseSigner):
    engine_name = "hyperdown"

    def _login(self, account: str, password: str) -> str:
        """邮箱密码登录，返回 access_token（框架视为 cookie）。

        account 在 Hyperdown 场景下是邮箱。
        """
        cfg = self.task_cfg
        base = self._api_base(cfg)
        ua = cfg.get("user_agent") or DEFAULT_UA
        try:
            data = _request(
                "POST", "/auth/login",
                base_url=base, ua=ua, proxy=self.proxy,
                body={"email": account, "password": password},
                auth=False, secure=False,
            )
        except _APIError as e:
            raise LoginError(f"登录失败: [{e.code}] {e.message}") from e
        except Exception as e:
            raise LoginError(f"登录异常: {e}") from e
        access, _refresh = _absorb_tokens(data)
        if not access:
            raise LoginError("登录响应未返回 access_token")
        return access

    def _run_one(self, cookie: str) -> SignResult:
        """cookie 即 access_token。查询 is_check_in，未签则签到。"""
        cfg = self.task_cfg
        base = self._api_base(cfg)
        ua = cfg.get("user_agent") or DEFAULT_UA
        token = cookie.strip()

        # 1) 查询用户信息，判断今日是否已签
        try:
            data = _request("GET", "/me/", base_url=base, ua=ua,
                            proxy=self.proxy, access_token=token,
                            auth=True, secure=False)
            user = (data.get("user") if isinstance(data, dict)
                    and isinstance(data.get("user"), dict) else data) or {}
        except _APIError as e:
            return SignResult(self.platform, self.task_name, False,
                              f"查询用户信息失败: [{e.code}] {e.message}")
        except Exception as e:
            return SignResult(self.platform, self.task_name, False,
                              f"查询用户信息异常: {e}")

        if user.get("is_check_in"):
            bal = _fmt_bytes(user.get("traffic_bytes"))
            total = _fmt_bytes(user.get("total_traffic_check_in_bytes"))
            return SignResult(self.platform, self.task_name, True,
                              f"今日已签到。流量余额 {bal}，累计签到流量 {total}",
                              already=True)

        # 2) 未签到 → 调用签到接口（SealJSON 自动加密）
        try:
            result = _request("POST", "/me/checkins", base_url=base,
                              ua=ua, proxy=self.proxy,
                              access_token=token, auth=True, secure=True,
                              body={})
        except _APIError as e:
            if e.code == "network_error":
                return SignResult(self.platform, self.task_name, False,
                                  f"网络错误: {e.message}")
            if e.code in ("already_checked_in", "already_check_in",
                          "checked_in"):
                return SignResult(self.platform, self.task_name, True,
                                  f"服务端确认今日已签到: {e.message}",
                                  already=True)
            if e.code in ("secure_request_invalid", "secure_request_required",
                          "secure_request_expired", "secure_request_replayed"):
                return SignResult(self.platform, self.task_name, False,
                                  "安全封包未通过服务端校验，"
                                  "请检查 secure_api 版本与服务器时间/NTP")
            return SignResult(self.platform, self.task_name, False,
                              f"签到失败: [{e.code}] {e.message}")
        except Exception as e:
            return SignResult(self.platform, self.task_name, False,
                              f"签到异常: {e}")

        # 3) 签到成功
        result = result if isinstance(result, dict) else {}
        reward = result.get("traffic_bytes") or result.get("reward_bytes") or 0
        u2 = result.get("user") if isinstance(result.get("user"), dict) else {}
        bal = u2.get("traffic_bytes", user.get("traffic_bytes"))
        return SignResult(self.platform, self.task_name, True,
                          f"签到成功！本次奖励 {_fmt_bytes(reward)}，"
                          f"余额 {_fmt_bytes(bal)}")

    @staticmethod
    def _api_base(cfg: dict) -> str:
        base = cfg.get("api_base_url") or DEFAULT_BASE
        # 自动补全到 /api/v1
        base = base.rstrip("/")
        if base.endswith("/api/v1"):
            return base
        if base.endswith("/api"):
            return base + "/v1"
        if "://" in base and "/api/" not in base:
            return base + "/api/v1"
        return base
