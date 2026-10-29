"""WorkBuddy（Buddy 加油站）签到引擎。

比一般论坛特殊在三件事：

1. 凭证是**桌面客户端的登录态**（refreshToken，约 700 字符的 JWT），不是普通
   cookie。文章那套「让 agent 读客户端 auth 文件提 refreshToken」正是为此。
   本引擎按下面的优先级找凭证：

     a) 环境变量 CT_WORKBUDDY_COOKIE   （项目标准变量，纯 token）
     b) 环境变量 CT_WORKBUDDY_AUTH      （项目标准变量，一体化 `token||账号||密码`，
                                          workbuddy 无账号密码时写 `token||` 即可）
     c) 环境变量 CT_WORKBUDDY_TOKEN     （别名，方便直接粘一串 token 进来）
     d) 本机客户端登录态文件             （仅本地开发有效；青龙容器没有该文件）

2. refreshToken 不一定需要先换 access_token，很多接口直接当 Bearer 用。
   故 token_url 为空时直接用 refreshToken；配了 token_url 才走换取。

3. 签到端点未公开、客户端渲染层是加密的，无法从程序包里静态提取。
   故 config 的 url 可留空：此时引擎按 sign_candidates 逐个试（后端对不存在的
   路径固定返回 404 Route Not Found，是可靠的探测信号），命中即签到。探测默认
   开启，可用 config 的 auto_probe: false 或 CT_WORKBUDDY_DISCOVER=0 关掉。

另外是一个持续性设计：若签到响应里轮换出了新的 refreshToken，引擎会把它写回
来源变量（青龙环境变量优先，非青龙环境写 .cache/tokens.json），token 过期前能
自动续期，不必每次手工换。

config.yml 示例：
  engine: workbuddy
  base_url: "https://www.workbuddy.cn"
  cookie_env: CT_WORKBUDDY_COOKIE
  token_url: ""                 # 留空 = refreshToken 直接当 Bearer
  auto_probe: true              # url 留空时自动试 sign_candidates
  tasks:
    - name: Buddy 加油站
      url: ""                   # 摸到真实端点后填这里，探测仅作兜底
      method: post
      code_field: code
      success_codes: [0]
      already_keywords: ["已签到", "已领取"]
      success_keywords: ["签到成功", "成功"]
"""

from __future__ import annotations

import glob
import json
import os

from ..base import BaseSigner, SignResult
from ..client import HttpClient
from ..config import get_env
from ..log import logger

# 客户端登录态目录（macOS / Windows 两处）
_AUTH_DIRS = [
    os.path.expanduser("~/Library/Application Support/CodeBuddyExtension/Data/Public/auth"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "CodeBuddyExtension",
                 "Data", "Public", "auth"),
]

# 后端对不存在路由的固定响应，用来识别探测命中的真实端点
_NOT_FOUND_MARKERS = ("Route Not Found", "404 Route")

# 凭证兜底位：base 只把 cookie_env（CT_WORKBUDDY_COOKIE）传进来，其余两个变量
# 需引擎自己读。顺序：COOKIE(由 base 传) → AUTH → TOKEN → 本机登录态文件。
_TOKEN_ALIAS_ENVS = ("CT_WORKBUDDY_AUTH", "CT_WORKBUDDY_TOKEN",
                     "CT_WORKBUDDY_REFRESH_TOKEN")

# 轮换出的新 token 字段（不同接口命名可能不同）
_RENEW_FIELDS = ("refresh_token", "refreshToken", "refresh")

# 本引擎缓存目录：仓库根 .cache（已被 .gitignore 忽略）
_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".cache")


class WorkBuddySigner(BaseSigner):
    engine_name = "workbuddy"

    # ---------- 凭据 ----------

    def _resolve_credential(self, cookie: str):
        """返回 (token, 来源变量/描述)；来源用于轮换写回定位。"""
        token = (cookie or "").strip()
        if token:
            # 兼容 AUTH 一体化整段被当作 cookie 传进来的情况
            token = token.split("||")[0].strip()
            return token, self.cookie_env or "CT_WORKBUDDY_COOKIE"

        for env_name in _TOKEN_ALIAS_ENVS:
            val = (get_env(env_name) or "").strip()
            if not val:
                continue
            # AUTH 一体化：只有 token 段非空才算有效（"token||" 可以，""|| 不行）
            if env_name == "CT_WORKBUDDY_AUTH":
                if not val.split("||")[0].strip():
                    continue
                self._cred_raw = val          # 轮换写回时按原格式重建
            return val, env_name

        fallback = self._refresh_token_from_local()
        if fallback:
            return fallback, "本机客户端登录态文件"
        return "", ""

    def _local_auth_files(self):
        """本机客户端登录态文件，按修改时间倒序（最新的排最前）。"""
        files, seen = [], set()
        for d in _AUTH_DIRS:
            if not d or not os.path.isdir(d):
                continue
            for p in glob.glob(os.path.join(d, "*.info")):
                p = os.path.abspath(p)
                if p not in seen:
                    seen.add(p)
                    files.append(p)
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return files

    def _refresh_token_from_local(self):
        """回退读取本机客户端登录态，返回明文字节串；全为加密版则抛可读错误。"""
        files = self._local_auth_files()
        for path in files:
            logger.info("WorkBuddy: 尝试客户端登录态文件 %s", os.path.basename(path))
            try:
                data = json.loads(open(path, encoding="utf-8").read())
            except Exception:
                continue
            rt = ((data.get("auth") or {}).get("refreshToken"))
            if isinstance(rt, str) and rt.strip():
                return rt.strip()             # 旧版明文，直接用

        if files:
            raise RuntimeError(
                "本机客户端已把 refreshToken 改成信封加密（suite/keyId/ciphertext），"
                "外部无法解密。请在青龙配置明文 CT_WORKBUDDY_COOKIE（或 "
                "CT_WORKBUDDY_TOKEN / CT_WORKBUDDY_AUTH），或换用客户端备份里的"
                "历史明文文件。"
            )
        return ""

    # ---------- 主流程 ----------

    def _run_one(self, cookie: str) -> SignResult:
        cfg = self.task_cfg
        base_url = cfg.get("base_url", "") or self.cfg.get("base_url", "") or ""

        token, source = self._resolve_credential(cookie)
        if not token:
            return SignResult(
                self.platform, self.task_name, False,
                "未找到 refreshToken：请配置 CT_WORKBUDDY_COOKIE（或 "
                "CT_WORKBUDDY_AUTH / CT_WORKBUDDY_TOKEN）")
        logger.info("WorkBuddy: 已获取凭证（来源 %s，长度 %d）", source, len(token))

        new_token = self._do_sign(base_url, token, cfg)
        if new_token and new_token != token:
            self._persist_token(source, new_token)
        return self._last

    # ---------- token 轮换写回 ----------

    def _persist_token(self, source: str, token: str):
        """写回新 token：青龙环境变量优先，非青龙环境落 .cache/tokens.json。

        AUTH 变量的整行是 `token||账号||密码`，轮换只替换 token 段，账号密码原样保留。
        """
        value = token
        if source == "CT_WORKBUDDY_AUTH" and getattr(self, "_cred_raw", ""):
            parts = self._cred_raw.split("||")
            parts[0] = token
            value = "||".join(parts)

        ok = False
        try:
            from .. import qlapi
            ok, _msg = qlapi.update_env_value(source, value)
        except Exception as e:                 # 非青龙环境 / 无令牌
            logger.debug("WorkBuddy: qlapi 不可用（%s），改存本地缓存", e)

        if ok:
            logger.info("WorkBuddy: 服务端轮换出新的 token，已写回青龙变量 %s", source)
            return

        try:
            self._write_token_cache(source, token)
            logger.warning(
                "WorkBuddy: 未检测到青龙环境，新 token 已写入 .cache/tokens.json"
                "（请手动更新 %s）", source)
        except Exception as e:
            logger.warning("WorkBuddy: 新 token 持久化失败(%s)，请手动更新 %s", e, source)

    def _write_token_cache(self, var_name: str, value: str):
        os.makedirs(_CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(_CACHE_DIR, "tokens.json")
        data = {}
        if os.path.exists(cache_file):
            try:
                data = json.loads(open(cache_file, encoding="utf-8").read() or "{}")
            except Exception:
                data = {}
        data[var_name] = value
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        try:
            os.chmod(cache_file, 0o600)          # token 文件，收紧权限
        except OSError:
            pass

    # ---------- token 换取 ----------

    def _resolve_token(self, base_url, refresh, cfg):
        """有 token_url 就换 access_token，否则直接拿 refreshToken 当 Bearer。"""
        token_url = str(cfg.get("token_url") or "").strip()
        if not token_url:
            return refresh

        client = HttpClient(base_url=base_url, cookie=refresh, proxy=self.proxy,
                            encoding="utf-8")
        payload = self._fill((cfg.get("token_json")
                              or {"grant_type": "refresh_token",
                                  "refresh_token": "{refresh}"}), refresh)
        try:
            r = client.post(token_url, json=payload or {})
            j = r.json()
        except Exception as e:
            logger.warning("WorkBuddy: 换取 access_token 失败: %s", e)
            return ""
        for pk in ("access_token", "accessToken", "token"):
            v = j.get(pk)
            if v:
                return v
        return ""

    # ---------- 签到 ----------

    def _do_sign(self, base_url, token, cfg):
        """返回轮换出的新 token（无则空串），结果写进 self._last。"""
        self._last = None
        self._new_token = ""

        urls, probing = self._build_urls(cfg)
        already_kw = cfg.get("already_keywords") or []
        fail_kw = cfg.get("fail_keywords") or []
        ok_kw = cfg.get("success_keywords") or []
        code_field = cfg.get("code_field", "code")
        success_codes = cfg.get("success_codes", [0, 200])
        method = str(cfg.get("method", "post")).lower()
        debug = self._flag("CT_WORKBUDDY_DEBUG")

        for url in urls:
            client = HttpClient(base_url=base_url, cookie=token, proxy=self.proxy,
                                encoding="utf-8")
            path = self._fill(url, token)
            params = self._fill(cfg.get("params") or {}, token)
            body = self._fill(cfg.get("json") or {}, token)
            headers = self._fill(cfg.get("headers") or {}, token) or None
            full = (path if path.lower().startswith("http")
                    else f"{base_url.rstrip('/')}/{path.lstrip('/')}")
            try:
                r = client.get(full, params=params, headers=headers) if method == "get" \
                    else client.post(full, json=body, headers=headers)
                text = r.text
            except Exception as e:
                self._last = SignResult(self.platform, self.task_name, False,
                                        f"{full} 请求失败: {e}")
                continue

            if any(m in text for m in _NOT_FOUND_MARKERS):
                logger.info("WorkBuddy: %s 非签到端点（404），跳过", full)
                continue

            j = {}
            try:
                j = r.json()
            except Exception:
                pass

            # 轮换 token：响应里带了新 refreshToken 就记下来
            for pk in _RENEW_FIELDS:
                v = j.get(pk)
                if isinstance(v, str) and v.strip() and v != token:
                    self._new_token = v.strip()
                    break

            # JSON code 判定优先
            if j.get(code_field) in success_codes:
                self._last = SignResult(
                    self.platform, self.task_name, True,
                    str(j.get("message") or j.get("msg") or "签到成功"))
                return self._new_token

            search_text = text
            if j:
                search_text += " " + str(j.get("msg") or j.get("message") or "")

            hit = None
            for kw in already_kw:
                if kw and kw in search_text:
                    hit = ("already", "今日已签到")
                    break
            if not hit:
                for kw in fail_kw:
                    if kw and kw in search_text:
                        hit = ("failed", f"未成功（命中: {kw}）")
                        break
            if not hit:
                for kw in ok_kw:
                    if kw and kw in search_text:
                        hit = ("ok", "签到成功")
                        break
            if hit:
                kind, msg = hit
                self._last = SignResult(self.platform, self.task_name,
                                        kind != "failed", msg,
                                        already=(kind == "already"))
                return self._new_token

            if debug:
                logger.info("WorkBuddy: 响应片段 -> %s",
                            search_text[:300].replace("\n", " "))
            self._last = SignResult(
                self.platform, self.task_name, False,
                f"{full} 无法判定，响应: {search_text[:120]}".replace("\n", " "))

        if probing:
            self._last = SignResult(
                self.platform, self.task_name, False,
                "未找到签到端点：所有候选都返回 404。请在客户端抓一个真实签到请求，"
                "把 URL 填到 platforms/workbuddy/config.yml 的 tasks[0].url")
        elif not urls:
            self._last = SignResult(self.platform, self.task_name, False,
                                    "未配置签到地址（tasks[0].url）")
        return self._new_token

    def _build_urls(self, cfg):
        """构造待试端点。返回 (urls, 是否处于探测模式)。"""
        primary = str(cfg.get("url") or cfg.get("sign_url") or "").strip()
        candidates = [str(c).strip() for c in (cfg.get("sign_candidates") or [])
                      if str(c).strip()]

        if primary:
            return [primary], False
        if not candidates or not self._want_discover():
            return [], False
        return candidates, True

    def _want_discover(self):
        """探测开关：CT_WORKBUDDY_DISCOVER 显式置 0 则关，否则看 config.auto_probe。"""
        env = self._flag("CT_WORKBUDDY_DISCOVER")
        if env is False:
            return False
        return bool(self.task_cfg.get("auto_probe", True))

    def _flag(self, name):
        """读三态布尔环境变量：True / False / None(未设置)。"""
        raw = (get_env(name) or "").strip().lower()
        if raw in ("1", "true", "yes", "on"):
            return True
        if raw in ("0", "false", "no", "off"):
            return False
        return None

    @staticmethod
    def _fill(value, token):
        """替换 {token} / {refresh} / {cookie} 占位。"""
        if isinstance(value, str):
            return (value.replace("{token}", token)
                         .replace("{refresh}", token)
                         .replace("{cookie}", token))
        if isinstance(value, dict):
            return {k: WorkBuddySigner._fill(v, token) for k, v in value.items()}
        if isinstance(value, list):
            return [WorkBuddySigner._fill(v, token) for v in value]
        return value
