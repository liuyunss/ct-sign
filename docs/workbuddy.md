# WorkBuddy（Buddy 加油站）签到

签到引擎：`workbuddy` ｜ 入口脚本：`signs/sign_workbuddy.py`（`ql repo` 白名单 `sign_` 会自动建任务）

与一般论坛最大的区别：**凭证不是浏览器 cookie，是桌面客户端的登录态 token**；
且官方没有公开签到接口，需要把真实请求 URL 填进配置。

---

## 一、青龙要配哪些变量

在青龙「环境变量」面板新增（每平台最多 2~3 个变量位，取其一即可，优先级从高到低）：

| 变量名 | 填什么 | 适用 |
|--------|--------|------|
| `CT_WORKBUDDY_COOKIE` | 明文 token（就是 refreshToken，约 700 字符 JWT） | 推荐，项目标准变量 |
| `CT_WORKBUDDY_AUTH` | 一体化格式 `token||账号||密码`；无账号密码时写 `token||` | 想沿用 AUTH 惯例时用 |
| `CT_WORKBUDDY_TOKEN` | 同上，只是别名 | 想一次塞一串 token 进来的快捷位 |

同名变量在本地调试则写仓库根 `.env`（已 gitignore，自动加载，格式 `KEY=VALUE`），模板见 `.env.example`。

> 引擎找不到上面任何变量时，会回退读本机客户端登录态目录
> （`~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/*.info`）。
> 该能力只在本地开发有效，**青龙容器里没有这个文件**，线上必须显式配变量。

### 手动落盘（可选）

```bash
# 写进 .env，自动备份（--print 只预览不落盘，--stdin 支持 pbpaste | 管道）
python3 scripts/set_token.py workbuddy "<token>"
python3 scripts/set_token.py workbuddy --var CT_WORKBUDDY_AUTH "<token>||"
```

---

## 二、token 是什么、从哪来

token 就是那篇文章说的客户端**登录态 refreshToken**，不是浏览器 cookie：

- 在客户端「设置 → 账号/登录」或 `~/.codebuddy` 相关配置里能找到一串约 700 字符的 JWT；
- 客户端从服务端「Buddy 加油站 / 每日签到」页面登录后，登录态会以明文或信封加密形式
  落到 `Data/Public/auth/*.info` 文件里，文章那套提示词读的就是它。

⚠️ **版本坑**：客户端 v5.7.6+ 把 `auth.refreshToken` 改成了信封加密
（`{$wbEncrypted:1, envelope:{suite,keyId,nonce,authTag,ciphertext}}`），
解密密钥只在客户端进程内，外部（含本脚本）读不出明文。此时必须**手工给一个旧版明文 token**
填进上面三个变量之一，否则会报：

```
本机客户端已把 refreshToken 改成信封加密（suite/keyId/ciphertext），外部无法解密。
```

拿不到明文 token 时的替代路径：客户端设置里「导出/复制登录态」类按钮，或从客户端备份文件
（`workbuddy-desktop.<时间戳>.info`，历史备份里存的是明文）里取同账号的明文值。

---

## 三、签到端点：留空会自动探测

官方没公开签到接口，客户端渲染层又是加密的，所以配置里 `tasks[0].url` 先留空：
引擎会按 `sign_candidates` 逐个试（后端对不存在路由固定返回 `404 Route Not Found`，
是可靠信号），命中就签到，日志形如：

```
[INFO] https://www.workbuddy.cn/api/v1/buddy/sign 非签到端点（404），跳过
```

**探测到真实端点后**，把 URL 填进 `platforms/workbuddy/config.yml` 的 `tasks[0].url`，
日常就只请求一次，不再逐个 404。

相关开关（环境变量，默认按 config 的 `auto_probe: true`）：

| 变量 | 作用 |
|------|------|
| `CT_WORKBUDDY_DISCOVER=0` | 关掉探测，只请求已配置的 `url` |
| `CT_WORKBUDDY_DISCOVER=1` | 强制探测（即使 `auto_probe: false`） |
| `CT_WORKBUDDY_DEBUG=1` | 打印签到请求响应片段，便于补判定关键词 |

判定规则（`config.yml` 内可调）：
- `already_keywords` → 命中视为**今日已签到**（结果 `[已签]`，不算失败）
- `fail_keywords` → 判定失败
- `success_keywords` / `code_field` + `success_codes` → 判定成功

---

## 四、token 轮换会自动续期

若签到响应里带回新的 `refreshToken`，引擎会自动写回**来源变量**：

- 青龙环境 → 走 `ql api` 更新同名环境变量（日志提示"已写回青龙变量 XXX"）
- 非青龙 → 落到 `.cache/tokens.json`（权限 600），并提示手动更新

所以 token 没过期前，每天签到都能顺手续上下一份，不必每月换一次。

---

## 五、本地跑一次

```bash
python3 signs/sign_workbuddy.py          # 单平台
python3 signs/sign_all.py                # 全平台
CT_WORKBUDDY_DEBUG=1 python3 signs/sign_workbuddy.py   # 带响应片段
```

正常输出（端点还没填时）：

```
[INFO] WorkBuddy: 已获取凭证（来源 CT_WORKBUDDY_COOKIE，长度 700）
[INFO] https://www.workbuddy.cn/api/v1/buddy/sign 非签到端点（404），跳过
...
[失败] WorkBuddy · Buddy 加油站：未找到签到端点：所有候选都返回 404。
       请在客户端抓一个真实签到请求，把 URL 填到 platforms/workbuddy/config.yml 的 tasks[0].url
```

---

## 六、排错速查

| 现象 | 原因 / 处理 |
|------|------------|
| 「未找到 refreshToken：请配置 CT_WORKBUDDY_COOKIE…」 | 三个变量都没配，或 token 为空 |
| 「已把 refreshToken 改成信封加密」 | 当前客户端版本加密了登录态，需手工提供明文 token |
| 所有候选 404 | 端点没摸到：客户端点一次签到 → F12 Network 复制请求 URL → 填 `tasks[0].url` |
| 「无法判定，响应: …」 | 端点对了但关键词没对上：开 `CT_WORKBUDDY_DEBUG=1` 看响应内容，补 `success_keywords` |
| 青龙里报缺凭证 | 青龙容器没有本机登录态文件，必须显式配 `CT_WORKBUDDY_COOKIE` 等变量 |
