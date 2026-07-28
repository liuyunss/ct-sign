"""HTTP 客户端封装：会话复用、重试、超时、UA、Cookie 注入、代理、编码纠正。"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from requests.cookies import cookiejar_from_dict
from urllib3.util.retry import Retry

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 15


def _cookie_dict_from_string(cookie: str) -> dict:
    """把 "k1=v1; k2=v2" 解析成 dict（值可含 =，按首个 = 拆分）。"""
    d = {}
    for part in (cookie or "").split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            d[k.strip()] = v
    return d


class HttpClient:
    """对 requests.Session 的轻量封装，所有引擎共用。"""

    def __init__(self, base_url="", cookie="", timeout=DEFAULT_TIMEOUT,
                 encoding="utf-8", extra_headers=None, verify_ssl=True, proxy=""):
        self.base_url = (base_url or "").rstrip("/")
        self.encoding = encoding
        self.timeout = timeout

        self.session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "POST"),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        headers = {
            "User-Agent": DEFAULT_UA,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if cookie:
            # 优先把 Cookie 注入会话 jar（而非裸 Cookie 头）：
            # 能正确处理 WordPress 等含 %7C 等特殊字符的 cookie 值，
            # 裸头字符串发送时部分站点（gopojie）会拒收导致“未登录”。
            try:
                self.session.cookies = cookiejar_from_dict(
                    _cookie_dict_from_string(cookie))
            except Exception:
                headers["Cookie"] = cookie  # 兜底：仍用裸头
        if extra_headers:
            headers.update(extra_headers)
        self.session.headers.update(headers)

        if proxy:
            self.session.proxies.update({"http": proxy, "https": proxy})
        else:
            # 关闭系统/环境代理（HTTP_PROXY/HTTPS_PROXY 等）。否则 requests 会自动
            # 走本机代理（如 127.0.0.1 抓包代理），被拦截并返回非站点响应
            # （例如 3G壁纸 的 "An error occurred"）。显式置 None 禁用该 scheme 的 env 代理。
            self.session.proxies.update({"http": None, "https": None})
        self.verify_ssl = verify_ssl

    def _url(self, path):
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def get(self, path, **kw):
        resp = self.session.get(
            self._url(path), timeout=self.timeout,
            verify=self.verify_ssl, **kw,
        )
        resp.encoding = self.encoding or resp.apparent_encoding
        return resp

    def post(self, path, data=None, json=None, **kw):
        resp = self.session.post(
            self._url(path), data=data, json=json,
            timeout=self.timeout, verify=self.verify_ssl, **kw,
        )
        resp.encoding = self.encoding or resp.apparent_encoding
        return resp
