"""Discuz! 账号密码登录助手。

通用登录流：取登录页 formhash+loginhash → POST 登录 → 返回可注入 HttpClient 的 Cookie 头。
成功判定：登录态 cookie（以 _auth 结尾）已种下，且返回消息不含失败/验证码特征。
失败时抛 LoginError，由调用方决定是否回退到 cookie。

注意：若论坛开启了登录验证码(seccode)，本助手无法自动通过——需人工或第三方打码，超出范围。
"""

from __future__ import annotations

import re
import urllib.parse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .client import DEFAULT_UA, DEFAULT_TIMEOUT

LOGIN_ERR = "登录失败"


class LoginError(Exception):
    pass


# 登录失败的特征词（命中即认为登录未成功，用于给出可读错误）
LOGIN_FAIL_KEYWORDS = [
    "密码错误", "密码不正确", "登录失败", "用户名不存在", "账号不存在",
    "验证码错误", "请填写验证码", "安全提问错误", "回答错误",
]

# 验证码拦截特征词（即使服务端种下了部分 cookie，也视为未真正登录）
CAPTCHA_KEYWORDS = [
    "请输入验证码", "验证码错误", "验证码不正确", "请填写验证码", "seccode",
]


def _new_session(proxy: str, verify_ssl: bool, timeout: int) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=2, backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
    )
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({
        "User-Agent": DEFAULT_UA,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    if proxy:
        s.proxies.update({"http": proxy, "https": proxy})
    else:
        # 关闭系统/环境代理（HTTP_PROXY/HTTPS_PROXY 等）。否则本机会把请求
        # 路由到本地代理（如 127.0.0.1 抓包代理），被拦截并返回非站点响应
        # （例如 3G壁纸 的 "An error occurred"）。显式置 None 可禁用该 scheme 的 env 代理。
        s.proxies.update({"http": None, "https": None})
    s.verify = verify_ssl
    return s


def _cookie_header(session: requests.Session) -> str:
    return "; ".join(f"{c.name}={c.value}" for c in session.cookies)


def _has_fail(body: str) -> bool:
    return any(k in body for k in LOGIN_FAIL_KEYWORDS)


def _has_captcha(body: str) -> bool:
    return any(k in body for k in CAPTCHA_KEYWORDS)


def _extract_message(html: str) -> str:
    # 优先取 Discuz 消息容器，避免抓到页面导航栏的 <p>
    for pat in (r'id="messagetext"[^>]*>(.*?)</div>',
                r'class="alert_[^"]*"[^>]*>(.*?)</div>',
                r'<div class="c"[^>]*>(.*?)</div>',
                r"<p[^>]*>(.*?)</p>"):
        m = re.search(pat, html, re.S)
        if m:
            txt = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            if txt:
                return txt[:120]
    return ""


def discuz_login(
    base_url: str,
    account: str,
    password: str,
    login_page: str = "member.php?mod=logging&action=login",
    loginfield: str = "auto",
    extra_fields: dict | None = None,
    proxy: str = "",
    verify_ssl: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
    encoding: str = "utf-8",
    extra_headers: dict | None = None,
) -> str:
    """返回形如 "name1=val1; name2=val2" 的 Cookie 头字符串；失败抛 LoginError。"""
    base = (base_url or "").rstrip("/")
    if not base:
        raise LoginError("login 缺少 base_url")
    if not account or not password:
        raise LoginError("账号或密码为空")

    s = _new_session(proxy, verify_ssl, timeout)

    # 1) 登录页取 formhash + loginhash
    try:
        r = s.get(f"{base}/{login_page.lstrip('/')}", timeout=timeout)
    except Exception as e:
        raise LoginError(f"访问登录页异常: {e}")
    r.encoding = encoding or r.apparent_encoding
    m = re.search(r'name="formhash" value="([^"]+)"', r.text)
    if not m:
        raise LoginError("登录页未提取到 formhash")
    formhash = m.group(1)
    mh = re.search(r"loginhash=([^\"&]+)", r.text)
    loginhash = mh.group(1) if mh else ""

    fields_order = (["email", "username"] if loginfield == "auto"
                    else [loginfield])
    last_err = ""
    for lf in fields_order:
        data = {
            "formhash": formhash,
            "referer": base + "/",
            "loginfield": lf,
            "username": account,
            "password": password,
            "questionid": "0",
            "answer": "",
            "cookietime": "2592000",
        }
        if extra_fields:
            data.update(extra_fields)
        url = (f"{base}/member.php?mod=logging&action=login"
               f"&loginsubmit=yes&loginhash={loginhash}")
        try:
            r2 = s.post(url, data=data, timeout=timeout, allow_redirects=False,
                        headers=extra_headers if extra_headers else None)
        except Exception as e:
            last_err = f"登录请求异常: {e}"
            continue
        r2.encoding = encoding or r2.apparent_encoding
        body = r2.text
        # 验证码拦截：即使服务端种下了部分 cookie，也视为未真正登录。
        # 换 loginfield 重试无意义，直接结束循环。
        if _has_captcha(body):
            raise LoginError("需要验证码，无法自动登录（请改用 Cookie，或人工过码后更新 Cookie）")
        has_auth = any(c.name.endswith("_auth") for c in s.cookies)
        if has_auth and not _has_fail(body):
            return _cookie_header(s)
        # 失败原因：优先用命中的失败关键词，其次从页面抠提示文案
        reason = ""
        for kw in LOGIN_FAIL_KEYWORDS:
            if kw in body:
                reason = kw
                break
        if not reason:
            reason = _extract_message(body) or "登录未返回登录态 cookie"
        last_err = reason

    raise LoginError(last_err or LOGIN_ERR)


# ThinkPHP 登录失败的特征词（命中即认为未成功，用于给出可读错误）
TP_FAIL_KEYWORDS = [
    "用户名或密码不正确", "密码错误", "账号不存在", "用户名不存在",
    "密码不正确", "登录失败", "验证码", "已被锁定", "尝试次数",
]

# 登录成功的特征词（非 JSON 时的兜底判定）
TP_OK_KEYWORDS = ["登录成功", "签到成功", "成功"]


def _dig(d, path):
    """按点路径从字典取值，如 'data.userinfo.user_id'。取不到返回 None。"""
    cur = d
    for part in (path or "").split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _inject_tp_cookies(session, jdata, fields, base_url):
    """登录成功后，从响应 JSON 按 cookie_fields 提取字段写入 Cookie。

    参考：3G壁纸 登录接口仅返回 JSON（不设 Set-Cookie），需手动把
    data.userinfo.user_id -> uid、data.userinfo.token -> token 注入 Cookie，
    后续签到接口才能识别登录态。
    """
    try:
        host = urllib.parse.urlparse(base_url).netloc
    except Exception:
        host = ""
    for cname, jpath in (fields or {}).items():
        val = _dig(jdata, jpath)
        if val is None:
            continue
        try:
            session.cookies.set(cname, str(val),
                                domain=host or None, path="/")
        except Exception:
            pass


def thinkphp_login(
    base_url: str,
    account: str,
    password: str,
    login_page: str = "user/login.html",
    login_api: str = "api/user/login",
    token_field: str = "__token__",
    account_field: str = "account",
    password_field: str = "password",
    success_code: int = 1,
    extra_fields: dict | None = None,
    cookie_fields: dict | None = None,
    proxy: str = "",
    verify_ssl: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
    encoding: str = "utf-8",
    extra_headers: dict | None = None,
) -> str:
    """ThinkPHP 类站点的账号密码登录助手（如 3G壁纸）。

    通用登录流：GET 登录页抠 CSRF token(__token__) → POST 登录接口
    （ThinkPHP 习惯把 token 放在隐藏域，且登录页请求不能带 X-Requested-With，
    否则页面不含 token）→ 返回可注入 HttpClient 的 Cookie 头。

    成功判定：登录接口返回 JSON 的 code == success_code（默认 1），或（非 JSON 时）
    响应命中成功特征词且未命中失败特征词。失败时抛 LoginError。
    """
    base = (base_url or "").rstrip("/")
    if not base:
        raise LoginError("login 缺少 base_url")
    if not account or not password:
        raise LoginError("账号或密码为空")

    s = _new_session(proxy, verify_ssl, timeout)

    # 1) 取登录页，抠 CSRF token
    #   注意：ThinkPHP 登录页若带 X-Requested-With 可能返回无 token 的页面，
    #        故此处用普通页面请求（不带该头）。
    page_url = f"{base}/{login_page.lstrip('/')}"
    try:
        r = s.get(page_url, timeout=timeout)
    except Exception as e:
        raise LoginError(f"访问登录页异常: {e}")
    r.encoding = encoding or r.apparent_encoding
    if r.status_code >= 400:
        raise LoginError(
            f"登录页返回 {r.status_code}（可能被 WAF 拦截，换网络或稍后重试）")
    m = re.search(r'name="' + re.escape(token_field) + r'"\s+value="([^"]+)"',
                  r.text)
    if not m:  # 兜底：从内联 JS/JSON 里抠
        m = re.search(re.escape(token_field) +
                      r'["\']?\s*[:=]\s*["\']([^"\']+)', r.text)
    if not m:
        raise LoginError(f"登录页未提取到 {token_field}")
    token = m.group(1)

    # 2) POST 登录接口
    api_url = f"{base}/{login_api.lstrip('/')}"
    data = {token_field: token,
            account_field: account,
            password_field: password}
    if extra_fields:
        data.update(extra_fields)
    headers = {"X-Requested-With": "XMLHttpRequest",
               "Referer": page_url}
    if extra_headers:
        headers.update(extra_headers)
    try:
        r2 = s.post(api_url, data=data, headers=headers, timeout=timeout)
    except Exception as e:
        raise LoginError(f"登录请求异常: {e}")
    r2.encoding = encoding or r2.apparent_encoding
    body = r2.text

    # 优先按 JSON 判定（ThinkPHP 接口通常返回 JSON）
    try:
        j = r2.json()
        code = j.get("code")
        msg = str(j.get("msg") or j.get("message") or "")
        if code == success_code:
            if cookie_fields:
                _inject_tp_cookies(s, j, cookie_fields, base)
            return _cookie_header(s)
        if msg:
            raise LoginError(msg)
        raise LoginError("登录返回非成功 code")
    except LoginError:
        raise
    except Exception:
        pass  # 非 JSON，走下方关键词兜底

    # 关键词兜底（接口未返回 JSON 时）
    if any(k in body for k in TP_FAIL_KEYWORDS):
        reason = next((k for k in TP_FAIL_KEYWORDS if k in body), "")
        raise LoginError(reason or "登录失败")
    if any(k in body for k in TP_OK_KEYWORDS):
        return _cookie_header(s)
    raise LoginError(f"登录未返回成功（响应前 120 字: {body[:120]}）")


# WordPress(admin-ajax) 登录失败特征词
WP_FAIL_KEYWORDS = [
    "密码错误", "密码不正确", "用户名不存在", "账号不存在",
    "登录失败", "验证码", "用户名或密码", "非法请求", "未登录",
]

# 登录成功的特征词（非 JSON 时的兜底判定）
WP_OK_KEYWORDS = ["登录成功", "成功"]


def wordpress_login(
    base_url: str,
    account: str,
    password: str,
    login_action: str = "zb_user_login",
    user_field: str = "user_name",
    password_field: str = "user_password",
    nonce_page: str = "/login",
    nonce_regex: str = r'ajax_nonce["\']?\s*:\s*["\']([a-zA-Z0-9]+)',
    success_status: int = 1,
    remember: bool = True,
    extra_fields: dict | None = None,
    proxy: str = "",
    verify_ssl: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
    encoding: str = "utf-8",
    extra_headers: dict | None = None,
) -> str:
    """WordPress(admin-ajax.php) 类站点的账号密码登录助手（如 狗破解 gopojie）。

    通用登录流：GET nonce_page 抠 ajax_nonce → POST wp-admin/admin-ajax.php
    （action=login_action，带账号/密码/nonce）→ 返回可注入 HttpClient 的 Cookie 头。

    成功判定：登录接口返回 JSON 的 status == success_status（默认 1，
    亦兼容 code 字段）。失败时抛 LoginError（带服务端 msg）。

    注意：部分主题登录页带图片验证码（虽无输入框也可能在提交时校验），
    此时会返回“验证码/非法请求”类错误，需人工过码后改用 Cookie。
    """
    base = (base_url or "").rstrip("/")
    if not base:
        raise LoginError("login 缺少 base_url")
    if not account or not password:
        raise LoginError("账号或密码为空")

    s = _new_session(proxy, verify_ssl, timeout)

    # 1) 取 nonce_page，抠 ajax_nonce
    page_url = f"{base}/{nonce_page.lstrip('/')}"
    try:
        r = s.get(page_url, timeout=timeout)
    except Exception as e:
        raise LoginError(f"访问登录页异常: {e}")
    r.encoding = encoding or r.apparent_encoding
    if r.status_code >= 400:
        raise LoginError(
            f"登录页返回 {r.status_code}（可能被 WAF 拦截，换网络或稍后重试）")
    m = re.search(nonce_regex, r.text)
    if not m:
        raise LoginError("登录页未提取到 nonce(ajax_nonce)")
    nonce = m.group(1)

    # 2) POST 登录
    api_url = f"{base}/wp-admin/admin-ajax.php"
    data = {
        "action": login_action,
        user_field: account,
        password_field: password,
        "remember": "1" if remember else "0",
        "nonce": nonce,
    }
    if extra_fields:
        data.update(extra_fields)
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": page_url,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    if extra_headers:
        headers.update(extra_headers)
    try:
        r2 = s.post(api_url, data=data, headers=headers, timeout=timeout)
    except Exception as e:
        raise LoginError(f"登录请求异常: {e}")
    r2.encoding = encoding or r2.apparent_encoding
    body = r2.text

    # 优先按 JSON 判定
    try:
        j = r2.json()
        status = j.get("status")
        if status is None:
            status = j.get("code")
        msg = str(j.get("msg") or j.get("message") or "")
        if status == success_status:
            return _cookie_header(s)
        if msg:
            raise LoginError(msg)
        raise LoginError("登录返回非成功 status")
    except LoginError:
        raise
    except Exception:
        pass

    # 关键词兜底
    if any(k in body for k in WP_FAIL_KEYWORDS):
        reason = next((k for k in WP_FAIL_KEYWORDS if k in body), "")
        raise LoginError(reason or "登录失败")
    if any(k in body for k in WP_OK_KEYWORDS):
        return _cookie_header(s)
    raise LoginError(f"登录未返回成功（响应前 120 字: {body[:120]}）")
