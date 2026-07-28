"""签到基类与统一结果。

BaseSigner 负责：多账号拆分、随机延迟、结果汇总（可复用）。
子类只需实现 _run_one(单账号 cookie) —— 这是各引擎/平台差异所在。
所有任务最终都返回统一的 SignResult，便于 run_all 汇总通知。

凭证优先级（按用户要求，Cookie 优先）：
  1. 优先使用 Cookie（CT_<平台>_COOKIE 或 CT_<平台>_AUTH 行里的 cookie 段）。
  2. 若 Cookie 签到失败，且该行配置了账号密码，则登录获取新 Cookie 来签到，
     并把新 Cookie 写回（青龙环境变量 / 本地 .cache），实现自动续期。

变量约定（每平台最多 2 个变量名）：
  · CT_<平台>_COOKIE   仅 Cookie，多个用 & 或换行分隔（最简单）。
  · CT_<平台>_AUTH    一体化：每行 `cookie||账号||密码`，三段用 || 分隔，
                       任意段留空即跳过；支持换行或 & 分隔多账号。
                       刷新后的 Cookie 会写回 CT_<平台>_AUTH 对应行（或 COOKIE 变量）。
"""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path

from .client import DEFAULT_TIMEOUT
from .config import get_env
from .log import logger
from .login import LoginError, discuz_login
from . import qlapi
from .utils import split_accounts, random_sleep

ACCOUNT_SEP_DEFAULT = "&"


class SignResult:
    def __init__(self, platform, task, success, message,
                 already=False, details=None):
        self.platform = platform
        self.task = task
        self.success = success
        self.message = message
        self.already = already
        self.details = details or []

    def __str__(self):
        tag = "已签" if self.already else ("成功" if self.success else "失败")
        return f"[{tag}] {self.platform} · {self.task}：{self.message}"


class BaseSigner(ABC):
    """所有签到任务的基类。子类实现 _run_one。"""

    engine_name = "base"

    def __init__(self, platform: str, task_cfg: dict, cookie_env: str,
                 account_separator: str = ACCOUNT_SEP_DEFAULT,
                 proxy: str = "", random_delay: int = 0, random_delay_min: int = 0):
        self.platform = platform
        self.task_cfg = task_cfg
        self.task_name = task_cfg.get("name", "任务")
        self.cookie_env = cookie_env
        self.account_separator = account_separator
        self.proxy = proxy
        self.random_delay = random_delay
        self.random_delay_min = random_delay_min

    def run(self) -> SignResult:
        items, source_var, source_is_auth = self._resolve_items()
        if not items:
            login_cfg = self.task_cfg.get("login") or {}
            hints = []
            if login_cfg.get("auth_env"):
                hints.append(login_cfg["auth_env"])
            if self.cookie_env:
                hints.append(self.cookie_env)
            missing = " / ".join(hints) or "账号密码或 Cookie 环境变量"
            return SignResult(self.platform, self.task_name, False,
                              f"未配置任何凭证环境变量（需 {missing}）")

        refreshed = False
        sub = []
        for idx, it in enumerate(items):
            # 每个账号签到前随机延迟，模拟用户随机触发；
            # 对第一个账号也生效，使固定定时点表现为不规律访问。
            if self.random_delay > 0:
                random_sleep(self.random_delay, self.random_delay_min,
                             reason=f"签到前随机延迟(账号{idx + 1}/{len(items)})")

            cookie = it["cookie"]
            account, password = it["account"], it["password"]

            # —— 1) 优先走 Cookie ——
            if cookie:
                result = self._run_one(cookie)
                if result.success:
                    sub.append(result)
                    continue
                # Cookie 签到失败：若配了账号密码，则登录刷新后重试
                if account and password:
                    logger.info("Cookie 签到失败（%s），改用账号密码登录刷新: %s",
                                result.message, self._mask(account))
                    try:
                        fresh = self._login(account, password)
                    except LoginError as e:
                        logger.warning("账号 %s 登录也失败(%s)，保留原失败结果",
                                       self._mask(account), e)
                        sub.append(result)
                        continue
                    retry = self._run_one(fresh)
                    if retry.success or retry.already:
                        it["cookie"] = fresh
                        refreshed = True
                        msg = retry.message + "（已用账号密码刷新 Cookie）"
                        sub.append(SignResult(self.platform, self.task_name,
                                              retry.success, msg, already=retry.already))
                    else:
                        logger.warning("账号 %s 登录后重试仍失败: %s",
                                       self._mask(account), retry.message)
                        sub.append(result)
                    continue
                # 无账号密码可刷新，保留 Cookie 失败结果
                sub.append(result)
                continue

            # —— 2) 无 Cookie：用账号密码登录 ——
            if account and password:
                try:
                    fresh = self._login(account, password)
                except LoginError as e:
                    sub.append(SignResult(
                        self.platform, self.task_name, False,
                        f"账号 {account} 登录失败: {e}"))
                    continue
                result = self._run_one(fresh)
                if result.success or result.already:
                    it["cookie"] = fresh
                    refreshed = True
                sub.append(result)
                continue

            # —— 3) 两者皆无 ——
            sub.append(SignResult(self.platform, self.task_name, False,
                                  "无可用凭证（Cookie 与账号密码均缺失）"))

        # 有刷新则写回，下次直接走 Cookie
        if refreshed:
            self._persist_cookies(items, source_var, source_is_auth)

        ok = sum(1 for r in sub if r.success and not r.already)
        already = sum(1 for r in sub if r.already)
        msgs = [f"账号{i + 1}:{r.message}" for i, r in enumerate(sub)]
        joined = "；".join(msgs)
        if ok + already == len(sub) and len(sub) > 0:
            return SignResult(self.platform, self.task_name, True, joined,
                              already=already > 0, details=msgs)
        return SignResult(self.platform, self.task_name, False, joined, details=msgs)

    def _resolve_items(self):
        """解析凭证来源，按账号序号对齐。

        返回 (items, source_var, source_is_auth)：
        - items: 每项 {"cookie","account","password","auth_entry"}；cookie 优先，
          同时保留该序号对应的账号密码（用于刷新）。
        - source_var: 写回目标变量名（AUTH 或 COOKIE）。
        - source_is_auth: 是否为 AUTH 一体化格式（决定写回时的重建方式）。

        优先级：若配置了 CT_<平台>_AUTH（一体化），以它为准（每行自带 cookie+账号+密码）；
                否则仅用 CT_<平台>_COOKIE（纯 cookie，无刷新能力）。
        """
        login_cfg = self.task_cfg.get("login") or {}

        auth_env = login_cfg.get("auth_env")
        auth_raw = (get_env(auth_env) or "").strip() if auth_env else ""
        if auth_raw:
            entries = self._read_auth(auth_raw)
            items = []
            for e in entries:
                c, a, p = e["cookie"], e["account"], e["password"]
                if not c and not (a and p):
                    continue
                items.append({"cookie": c, "account": a, "password": p,
                              "auth_entry": e})
            return items, auth_env, True

        # 纯 Cookie 模式（COOKIE 变量）
        cookies_raw = (get_env(self.cookie_env) or "").strip()
        slots = (split_accounts(cookies_raw, self.account_separator)
                 if cookies_raw else [])
        items = []
        for c in slots:
            if not c:
                continue
            items.append({"cookie": c, "account": "", "password": "",
                          "auth_entry": None})
        return items, self.cookie_env, False

    def _read_auth(self, raw: str):
        """解析一体化 AUTH 变量。

        每行（或 & 分隔）一个账号，格式 `cookie||账号||密码`，三段用 || 分隔，
        任意段可留空；无 || 的整行视为纯 cookie。
        """
        entries = []
        for line in re.split(r"[\n&]", raw):
            line = line.strip()
            if not line:
                continue
            if "||" in line:
                parts = line.split("||")
                while len(parts) < 3:
                    parts.append("")
                cookie, account, password = (parts[0].strip(),
                                             parts[1].strip(),
                                             parts[2].strip())
            else:
                cookie, account, password = line, "", ""
            entries.append({"cookie": cookie, "account": account,
                            "password": password})
        return entries

    def _login(self, account: str, password: str) -> str:
        login_cfg = self.task_cfg.get("login") or {}
        login_type = (login_cfg.get("login_type") or "discuz").lower()
        base_url = self.task_cfg.get("base_url", "")
        verify_ssl = not self.task_cfg.get("insecure", False)
        encoding = self.task_cfg.get("encoding", "utf-8")

        if login_type == "thinkphp":
            from .login import thinkphp_login
            return thinkphp_login(
                base_url=base_url,
                account=account,
                password=password,
                login_page=login_cfg.get("login_page", "user/login.html"),
                login_api=login_cfg.get("login_api", "api/user/login"),
                token_field=login_cfg.get("token_field", "__token__"),
                account_field=login_cfg.get("account_field", "account"),
                password_field=login_cfg.get("password_field", "password"),
                success_code=int(login_cfg.get("success_code", 1)),
                extra_fields=login_cfg.get("extra_fields"),
                proxy=self.proxy,
                verify_ssl=verify_ssl,
                timeout=DEFAULT_TIMEOUT,
                encoding=encoding,
            )

        if login_type == "wordpress":
            from .login import wordpress_login
            return wordpress_login(
                base_url=base_url,
                account=account,
                password=password,
                login_action=login_cfg.get("login_action", "zb_user_login"),
                user_field=login_cfg.get("user_field", "user_name"),
                password_field=login_cfg.get("password_field", "user_password"),
                nonce_page=login_cfg.get("nonce_page", "/login"),
                nonce_regex=login_cfg.get(
                    "nonce_regex",
                    r'ajax_nonce["\']?\s*:\s*["\']([a-zA-Z0-9]+)'),
                success_status=int(login_cfg.get("success_status", 1)),
                extra_fields=login_cfg.get("extra_fields"),
                proxy=self.proxy,
                verify_ssl=verify_ssl,
                timeout=DEFAULT_TIMEOUT,
                encoding=encoding,
            )

        # 默认：Discuz! 表单流
        return discuz_login(
            base_url=base_url,
            account=account,
            password=password,
            login_page=login_cfg.get("login_page",
                                    "member.php?mod=logging&action=login"),
            loginfield=login_cfg.get("loginfield", "auto"),
            extra_fields=login_cfg.get("extra_fields"),
            proxy=self.proxy,
            verify_ssl=verify_ssl,
            timeout=DEFAULT_TIMEOUT,
            encoding=encoding,
        )

    def _mask(self, account: str) -> str:
        """日志中脱敏账号，避免泄露明文邮箱/用户名。"""
        if not account:
            return "?"
        if "@" in account:
            local, _, domain = account.partition("@")
            head = local[:3] if len(local) > 3 else local
            return f"{head}***@{domain}"
        return account[:2] + "***"

    def _persist_cookies(self, items, source_var, source_is_auth):
        """把刷新后的 Cookie 写回：优先青龙环境变量，否则本地 .cache（git 忽略）。"""
        if source_is_auth:
            # 重建 AUTH：保持每行 `cookie||账号||密码`，仅更新 cookie 段
            lines = []
            for it in items:
                e = it["auth_entry"] or {}
                lines.append(f"{it['cookie']}||{e.get('account', '')}||{e.get('password', '')}")
            new_val = "\n".join(lines)
        else:
            new_val = self.account_separator.join(it["cookie"] for it in items)

        try:
            ok, msg = qlapi.update_env_value(source_var, new_val)
        except Exception as e:  # pragma: no cover
            ok, msg = False, f"qlapi 异常: {e}"
        if ok:
            logger.info("已将刷新后的 Cookie 写回青龙环境变量 %s", source_var)
            return
        # 非青龙环境：写 gitignored 本地缓存，供手动更新参考
        try:
            self._write_local_cache(source_var, new_val)
            logger.warning(
                "未检测到青龙环境，刷新后的 Cookie 已写入 .cache/cookies.json"
                "（请手动更新青龙变量 %s）；qlapi: %s",
                source_var, msg)
        except Exception as e:
            logger.warning("无法持久化刷新后的 Cookie(%s)；请手动更新 %s",
                           e, source_var)

    def _write_local_cache(self, var_name: str, value: str):
        cache_dir = Path(__file__).resolve().parent.parent / ".cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "cookies.json"
        data = {}
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8") or "{}")
            except Exception:
                data = {}
        data[var_name] = value
        cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    @abstractmethod
    def _run_one(self, cookie: str) -> SignResult:
        """单个账号的执行逻辑，由子类实现。"""
        raise NotImplementedError
