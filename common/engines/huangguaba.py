"""黄瓜吧 自研站点引擎（签到 + 评论 + 点赞 遍历型任务）。

站点：https://www.huangguaba.com  自研 PHP + /api/*.php JSON 接口（非 Discuz）
登录：仅「cookie/token 优先」—— 登录页 /login.php 含算术验证码，不自动登录。
      凭证走 CT_HUANGGUABA_COOKIE（网页版登录后复制的完整 Cookie）。

接口（均返回 {"success":bool,"message":"..."}）：
  · 签到   POST /api/score.php        action=signin                  + csrf_token
  · 评论   POST /api/comment.php      post_id + content              + csrf_token
  · 点赞   POST /api/comment_vote.php comment_id（对评论点赞）        + csrf_token

所有写操作都需从页面取 CSRF_TOKEN（session 内固定，全站通用）。
评论/点赞为「先抓列表再逐个请求」的遍历型任务，故用独立引擎实现，
参数（count / content / per_post / skip_post_ids）全部在 config.yml 配置。
"""
from __future__ import annotations

import re

from ..base import BaseSigner, SignResult
from ..client import HttpClient

POST_ID_RE = re.compile(r'detail\.php\?id=(\d+)')
# 评论点赞按钮标记：<button class="inline-cmt-vote" data-cid="5160" ...>
# （评论由 /api/comments_inline.php 异步返回，detail 静态页不存在该标记）
COMMENT_ID_RE = re.compile(r'data-cid="(\d+)"')
# 已知公告/置顶帖（id=5066），评论点赞无意义，默认跳过；可用 config 的 skip_post_ids 追加
DEFAULT_SKIP_POST_IDS = {"5066"}


class HuangguabaSigner(BaseSigner):
    engine_name = "huangguaba"

    # ---------- 内部工具 ----------
    def _client(self, cookie):
        return HttpClient(
            base_url=self.task_cfg.get("base_url", ""),
            cookie=cookie, proxy=self.proxy,
            verify_ssl=not self.task_cfg.get("insecure", False),
        )

    def _csrf(self, client):
        page = client.get("/")
        m = re.search(r"CSRF_TOKEN\s*=\s*'([a-f0-9]{64})'", page.text)
        return m.group(1) if m else ""

    def _home_post_ids(self, client, count):
        skip = {str(x) for x in (self.task_cfg.get("skip_post_ids") or [])}
        skip |= DEFAULT_SKIP_POST_IDS
        html = client.get("/").text
        ids = []
        for m in POST_ID_RE.finditer(html):
            pid = m.group(1)
            if pid in ids or pid in skip:
                continue
            ids.append(pid)
        return ids[:count]

    # ---------- 任务分发 ----------
    def _run_one(self, cookie: str) -> SignResult:
        ttype = (self.task_cfg.get("task_type") or "signin").lower()
        if ttype == "signin":
            return self._do_signin(cookie)
        if ttype == "comment":
            return self._do_comment(cookie)
        if ttype == "like":
            return self._do_like(cookie)
        return SignResult(self.platform, self.task_name, False,
                          f"未知 task_type: {ttype}")

    # ---------- 签到 ----------
    def _do_signin(self, cookie):
        client = self._client(cookie)
        csrf = self._csrf(client)
        if not csrf:
            return SignResult(self.platform, self.task_name, False, "未取到 CSRF_TOKEN")
        try:
            resp = client.post("/api/score.php",
                               data={"action": "signin", "csrf_token": csrf})
            j = resp.json()
        except Exception as e:
            return SignResult(self.platform, self.task_name, False, f"签到请求失败: {e}")
        if j.get("success"):
            if j.get("already_signed"):
                return SignResult(self.platform, self.task_name, True,
                                  "今日已签到", already=True)
            return SignResult(self.platform, self.task_name, True,
                              f"签到成功（连签 {j.get('streak')} 天）")
        return SignResult(self.platform, self.task_name, False,
                          f"签到失败: {j.get('message')}")

    # ---------- 评论（对首页最新 N 帖发评论） ----------
    def _do_comment(self, cookie):
        client = self._client(cookie)
        csrf = self._csrf(client)
        if not csrf:
            return SignResult(self.platform, self.task_name, False, "未取到 CSRF_TOKEN")
        count = int(self.task_cfg.get("count", 3) or 3)
        content = self.task_cfg.get("content", "支持")
        post_ids = self._home_post_ids(client, count)
        if not post_ids:
            return SignResult(self.platform, self.task_name, False, "未取到任何帖子 id")
        logs, ok, fail = [], 0, 0
        for pid in post_ids:
            try:
                resp = client.post("/api/comment.php",
                                   data={"post_id": pid, "content": content,
                                         "csrf_token": csrf})
                j = resp.json()
            except Exception as e:
                fail += 1
                logs.append(f"帖 {pid} 异常: {e}")
                continue
            if j.get("success"):
                ok += 1
                logs.append(f"帖 {pid}: 评论成功")
            else:
                fail += 1
                logs.append(f"帖 {pid}: {j.get('message')}")
        msg = f"评论 {ok} 成功 / {fail} 失败；目标帖 {post_ids}"
        return SignResult(self.platform, self.task_name, ok > 0 and fail == 0,
                          msg, details=logs)

    # ---------- 点赞（对首页最新 N 帖下的前 M 条评论点赞） ----------
    def _do_like(self, cookie):
        client = self._client(cookie)
        csrf = self._csrf(client)
        if not csrf:
            return SignResult(self.platform, self.task_name, False, "未取到 CSRF_TOKEN")
        count = int(self.task_cfg.get("count", 3) or 3)
        per_post = int(self.task_cfg.get("per_post", 5) or 5)
        post_ids = self._home_post_ids(client, count)
        if not post_ids:
            return SignResult(self.platform, self.task_name, False, "未取到任何帖子 id")
        logs, ok, fail = [], 0, 0
        for pid in post_ids:
            try:
                r = client.get(f"/api/comments_inline.php?post_id={pid}")
                j = r.json()
                html = j.get("html", "") or ""
                ccount = j.get("count", 0)
            except Exception as e:
                logs.append(f"帖 {pid} 评论获取失败: {e}")
                continue
            cids = COMMENT_ID_RE.findall(html)[:per_post]
            if not cids:
                # 目标帖暂无评论：先发一条评论制造可点赞目标（评论+点赞闭环），
                # 避免「最新帖都还没人评」导致点赞任务整轮空跑。
                content = self.task_cfg.get("content") or "支持"
                try:
                    cr = client.post("/api/comment.php",
                                     data={"post_id": pid, "content": content,
                                           "csrf_token": csrf})
                    cj = cr.json()
                except Exception as e:
                    fail += 1
                    logs.append(f"帖 {pid} 兜底评论失败: {e}")
                    continue
                if not cj.get("success"):
                    fail += 1
                    logs.append(f"帖 {pid} 兜底评论失败: {cj.get('message')}")
                    continue
                try:
                    r2 = client.get(f"/api/comments_inline.php?post_id={pid}")
                    html2 = r2.json().get("html", "") or ""
                except Exception:
                    html2 = ""
                cids = COMMENT_ID_RE.findall(html2)[:per_post]
                if not cids:
                    logs.append(f"帖 {pid}: 兜底评论后仍无 cid，跳过")
                    continue
                logs.append(f"帖 {pid}: 无评论，已先发评论并点赞")

            for cid in cids:
                try:
                    resp = client.post("/api/comment_vote.php",
                                       data={"comment_id": cid, "csrf_token": csrf})
                    j = resp.json()
                except Exception as e:
                    fail += 1
                    logs.append(f"评论 {cid} 异常: {e}")
                    continue
                if j.get("success"):
                    ok += 1
                else:
                    fail += 1
                    logs.append(f"评论 {cid}: {j.get('message')}")
        msg = f"点赞 {ok} 成功 / {fail} 失败；覆盖帖 {post_ids}"
        return SignResult(self.platform, self.task_name, ok > 0 and fail == 0,
                          msg, details=logs)
