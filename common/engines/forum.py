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

        client = HttpClient(
            base_url=base_url, cookie=cookie, proxy=self.proxy,
            encoding=encoding, verify_ssl=not cfg.get("insecure", False),
        )

        # 1) 取签到页，抠 formhash
        formhash = None
        if formhash_re and sign_url:
            try:
                page = client.get(sign_url)
                m = re.search(formhash_re, page.text)
                if m:
                    formhash = m.group(1)
                else:
                    # 区分「Cookie 失效（被重定向到登录页）」与「formhash_re 正则写错」：
                    # 若页面出现登录相关特征，多半是 Cookie 过期/失效，而非正则问题。
                    login_markers = [
                        "loginsubmit", "member.php?mod=logging",
                        "请先登录", "您还未登录", "立即登录", "登录入口",
                        "登录后方可", "需要登录", "登录后操作",
                    ]
                    looks_login = any(k in page.text for k in login_markers)
                    if looks_login:
                        return SignResult(
                            self.platform, self.task_name, False,
                            "未提取到 formhash：页面疑似跳转到登录页"
                            "（Cookie 可能已失效，请重新获取 Cookie 后更新变量）")
                    return SignResult(
                        self.platform, self.task_name, False,
                        "未从签到页提取到 formhash（请检查 sign_url/formhash_re 是否正确）")
            except Exception as e:
                return SignResult(self.platform, self.task_name, False,
                                  f"访问签到页失败: {e}")

        # 2) 组装提交数据，替换 {formhash}
        data = {}
        for k, v in payload.items():
            if isinstance(v, str) and "{formhash}" in v and formhash:
                v = v.replace("{formhash}", formhash)
            data[k] = v

        # 2.5) action_url 里的 {formhash} 占位也替换（部分插件把 formhash 放在 URL 中，
        #       且可能重复出现，例如 Discuz 的 fx_checkin：formhash={fh}&{fh}）
        if formhash and action_url and "{formhash}" in action_url:
            action_url = action_url.replace("{formhash}", formhash)

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
