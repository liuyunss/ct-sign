"""JSON 接口流引擎。

适用于京东 / B站 / 网盘 / WordPress(admin-ajax) 等走 HTTP JSON 接口的平台：
POST/GET 接口 → 解析 JSON 的 code/status 字段判定；解析失败则回退关键词判定。

config.yml 示例：
  engine: api
  base_url: "https://api.example.com"
  tasks:
    - name: 每日签到
      url: "/sign"
      method: post
      json: { token: "{cookie}" }      # 也可放 data / headers
      code_field: code                  # 默认 code（WordPress 常用 status）
      success_codes: [0, 200]           # 视为成功的 code 值
      success_keywords: ["success"]
      # 可选：带 CSRF nonce 的站点（如 WordPress admin-ajax），先取 nonce 再发请求
      nonce:
        url: "/user"                    # GET 此页面取 nonce（需已登录态）
        regex: 'ajax_nonce["\']?\\s*:\\s*["\']([a-zA-Z0-9]+)'
        # 取出后注入到下方 data 的 {nonce} 占位
"""

from __future__ import annotations

import re

from ..base import BaseSigner, SignResult
from ..client import HttpClient


class ApiSigner(BaseSigner):
    engine_name = "api"

    def _run_one(self, cookie: str) -> SignResult:
        cfg = self.task_cfg
        base_url = cfg.get("base_url", "")
        url = cfg.get("url", "")
        method = str(cfg.get("method", "post")).lower()
        encoding = cfg.get("encoding", "utf-8")

        client = HttpClient(
            base_url=base_url, cookie=cookie, proxy=self.proxy,
            encoding=encoding, verify_ssl=not cfg.get("insecure", False),
        )

        # 可选：先取 CSRF nonce（如 WordPress admin-ajax 类站点），供下方占位注入
        nonce_val = ""
        nonce_cfg = cfg.get("nonce")
        if nonce_cfg:
            try:
                r0 = client.get(nonce_cfg.get("url", ""))
                m = re.search(
                    nonce_cfg.get(
                        "regex",
                        r'ajax_nonce["\']?\s*:\s*["\']([a-zA-Z0-9]+)'),
                    r0.text)
                if not m:
                    return SignResult(
                        self.platform, self.task_name, False,
                        f"未能从 {nonce_cfg.get('url')} 提取 nonce")
                nonce_val = m.group(1)
            except Exception as e:
                return SignResult(self.platform, self.task_name, False,
                                  f"获取 nonce 失败: {e}")

        # 把 {cookie} / {nonce} 占位替换成真实值
        def _fill(v):
            if isinstance(v, str):
                return (v.replace("{cookie}", cookie)
                         .replace("{nonce}", nonce_val))
            if isinstance(v, dict):
                return {k: _fill(x) for k, x in v.items()}
            if isinstance(v, list):
                return [_fill(x) for x in v]
            return v

        json_body = _fill(cfg.get("json"))
        data = _fill(cfg.get("data"))
        headers = _fill(cfg.get("headers")) or {}

        try:
            if method == "get":
                resp = client.get(url, params=data, headers=headers)
            else:
                resp = client.post(url, data=data, json=json_body, headers=headers)
            text = resp.text
        except Exception as e:
            return SignResult(self.platform, self.task_name, False, f"请求失败: {e}")

        # 优先按 JSON code 判定（成功码直接判成功；非成功码不直接判失败，
        # 交给下方关键词兜底，以区分“今日已签到”与真正失败）
        try:
            j = resp.json()
            code = j.get(cfg.get("code_field", "code"))
            success_codes = cfg.get("success_codes", [0, 200])
            if code in success_codes:
                return SignResult(self.platform, self.task_name, True,
                                  str(j.get("message") or j.get("msg") or "成功"))
        except Exception:
            pass

        # 回退：关键词判定
        # 注意：部分站点 JSON 体里中文被转义成 \uXXXX，resp.text 原样保留，
        # 故同时把 JSON 的 msg/message（已解码）并入可匹配文本。
        search_text = text
        try:
            j = resp.json()
            search_text = text + " " + str(j.get("msg") or j.get("message") or "")
        except Exception:
            pass
        already_kw = cfg.get("already_keywords") or []
        fail_kw = cfg.get("fail_keywords") or []
        ok_kw = cfg.get("success_keywords") or []
        for kw in already_kw:
            if kw and kw in search_text:
                return SignResult(self.platform, self.task_name, True,
                                  "今日已签到", already=True)
        for kw in fail_kw:
            if kw and kw in search_text:
                return SignResult(self.platform, self.task_name, False,
                                  f"未成功（命中: {kw}）")
        for kw in ok_kw:
            if kw and kw in search_text:
                return SignResult(self.platform, self.task_name, True, "签到成功")

        snippet = search_text[:160].replace("\n", " ")
        return SignResult(self.platform, self.task_name, False,
                          f"无法判定结果，响应片段: {snippet}")
