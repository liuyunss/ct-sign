"""论坛签到引擎（Discuz! 类表单流）。

通用流程：GET 签到页 → 正则抠 formhash → POST 表单 → 按关键词判定。
所有 Discuz 论坛共用本引擎，差异只在 config.yml（URL/字段/关键词）。
"""

from __future__ import annotations

import re

from ..base import BaseSigner, SignResult
from ..client import HttpClient


class ForumSigner(BaseSigner):
    engine_name = "forum"

    def _run_one(self, cookie: str) -> SignResult:
        cfg = self.task_cfg
        base_url = cfg.get("base_url", "")
        sign_url = cfg.get("sign_url", "")
        action_url = cfg.get("action_url") or sign_url
        method = str(cfg.get("method", "post")).lower()
        formhash_re = cfg.get("formhash_re")
        payload = cfg.get("payload") or {}
        encoding = cfg.get("encoding", "utf-8")
        extra_fields = cfg.get("extra_fields") or {}
        extra_headers = cfg.get("extra_headers") or {}

        client = HttpClient(
            base_url=base_url, cookie=cookie, proxy=self.proxy,
            encoding=encoding, verify_ssl=not cfg.get("insecure", False),
            extra_headers=extra_headers,
        )

        login_markers = [
            "loginsubmit", "member.php?mod=logging",
            "请先登录", "您还未登录", "立即登录", "登录入口",
            "登录后方可", "需要登录", "登录后操作",
        ]

        # 1) 取签到页，抠 formhash 与其他隐藏字段（如 CSRF nonce）
        subs = {}
        page_text = ""
        if sign_url:
            try:
                page = client.get(sign_url)
                page_text = page.text
            except Exception as e:
                return SignResult(self.platform, self.task_name, False,
                                  f"访问签到页失败: {e}")
            if formhash_re:
                m = re.search(formhash_re, page_text)
                if m:
                    subs["formhash"] = m.group(1)
                else:
                    # 区分「Cookie 失效（被重定向到登录页）」与「formhash_re 正则写错」：
                    # 若页面出现登录相关特征，多半是 Cookie 过期/失效，而非正则问题。
                    if any(k in page_text for k in login_markers):
                        return SignResult(
                            self.platform, self.task_name, False,
                            "未提取到 formhash：页面疑似跳转到登录页"
                            "（Cookie 可能已失效，请重新获取 Cookie 后更新变量）")
                    return SignResult(
                        self.platform, self.task_name, False,
                        "未从签到页提取到 formhash（请检查 sign_url/formhash_re 是否正确）")
            # 提取额外隐藏字段（如 Discuz 签到插件的 sign_nonce）
            for name, regex in extra_fields.items():
                fm = re.search(regex, page_text)
                subs[name] = fm.group(1) if fm else None

        # 2) 组装提交数据，替换 {占位符}（formhash / 任意 extra_fields）
        data = {}
        for k, v in payload.items():
            if isinstance(v, str):
                for key, val in subs.items():
                    if val is not None and "{" + key + "}" in v:
                        v = v.replace("{" + key + "}", val)
            data[k] = v

        # 2.5) action_url 里的 {占位符} 也替换（部分插件把 formhash 放在 URL 中，
        #       且可能重复出现，例如 Discuz 的 fx_checkin：formhash={fh}&{fh}）
        if action_url:
            for key, val in subs.items():
                if val is not None and "{" + key + "}" in action_url:
                    action_url = action_url.replace("{" + key + "}", val)

        # 占位符未解析完（如 CSRF nonce 缺失）——通常代表动作已完成或 Cookie 失效。
        # 已签到时很多插件会移除表单隐藏域，故「字段缺失」优先判为「今日已签」。
        if any(("{" in str(v) and "}" in str(v)) for v in list(data.values()) + [action_url or ""]):
            if any(k in page_text for k in login_markers):
                return SignResult(self.platform, self.task_name, False,
                                  "页面未包含所需字段（疑似跳登录页，Cookie 可能已失效）")
            return SignResult(self.platform, self.task_name, True,
                              "所需字段缺失（通常代表今日已完成/已签到）", already=True)

        # 3) 提交
        try:
            if method == "get":
                resp = client.get(action_url, params=data)
            else:
                resp = client.post(action_url, data=data)
            text = resp.text
        except Exception as e:
            return SignResult(self.platform, self.task_name, False, f"提交签到失败: {e}")

        # 4) 判定
        already_kw = cfg.get("already_keywords") or []
        fail_kw = cfg.get("fail_keywords") or []
        ok_kw = cfg.get("success_keywords") or []

        for kw in already_kw:
            if kw and kw in text:
                return SignResult(self.platform, self.task_name, True,
                                  "今日已签到", already=True)
        for kw in fail_kw:
            if kw and kw in text:
                return SignResult(self.platform, self.task_name, False,
                                  f"未成功（命中失败特征: {kw}）")
        for kw in ok_kw:
            if kw and kw in text:
                return SignResult(self.platform, self.task_name, True, "签到成功")

        snippet = text[:160].replace("\n", " ")
        return SignResult(self.platform, self.task_name, False,
                          f"无法判定结果，响应片段: {snippet}")
