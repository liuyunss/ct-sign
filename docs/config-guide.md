# 配置与凭证指南

## 0、照着填：福利吧环境变量怎么配（30 秒上手）

在青龙「环境变量」里，按你的情况**选一种**填（都以前缀 `CT_` 开头）：

### 方案 A：只有 Cookie（最简单，推荐新手）
- 名称：`CT_FUELBA_COOKIE`
- 值：浏览器复制的完整 Cookie 字符串（多账号用 `&` 或换行连）
```
CT_FUELBA_COOKIE=htVC_2132_...; ...
```
> Cookie 会过期，失效后在青龙里更新该值即可；或改用方案 B/C 自动续期。

### 方案 B：只有账号密码（自动登录，Cookie 失效也无所谓）
- 名称：`CT_FUELBA_AUTH`
- 值（每行一个账号，三段 `||` 分隔，**没有的部分留空**）：
```
||yourname@example.com||你的密码
```
> 注意：论坛若开启登录验证码则自动登录会失败，需回退方案 A 的 Cookie。福利吧目前不弹验证码。

### 方案 C：Cookie + 账号密码（推荐，优先用 cookie，失效自动登录刷新并写回）
- 名称：`CT_FUELBA_AUTH`
- 值：
```
你现在的cookie||yourname@example.com||你的密码
```
> 框架先用 cookie 签到；cookie 失效时自动用账号密码登录拿到新 cookie 并**写回这个变量**，实现自动续期。

### AUTH 格式速记
```
cookie||账号||密码      # 三段都有
||账号||密码            # 只有账号密码（没有 cookie）
cookie||                # 只有 cookie（也可只写 cookie，不带 ||）
```
- 多账号：用**换行**或 `&` 隔开多个“账号行”。
- 分隔符用 `||`：密码里几乎不会出现这两个字符，避免和内容撞车。

> 下面「一、环境变量命名」给完整变量表；「二、Cookie 优先 + 自动刷新」小节讲续期机制。

## 一、环境变量命名（前缀统一 `CT_`）

| 变量 | 作用 | 示例 |
|------|------|------|
| `CT_FUELBA_COOKIE` | 福利吧登录 Cookie（**优先使用**；失效时自动刷新并写回） | 完整 Cookie 字符串 |
| `CT_<平台>_COOKIE` | 任意新平台的 Cookie（**优先使用**；失效时自动刷新）。多个用 `&` 或换行分隔 | —— |
| `CT_FUELBA_AUTH` | **一体化变量（推荐）**：每行 `cookie||账号||密码`，三段用 `||` 分隔，任意段留空即跳过；支持换行或 `&` 分隔多账号 | 见下文 |
| `CT_<平台>_AUTH` | 任意新平台的一体化变量 | 见下文 |
| `CT_PROXY` | 全局代理（覆盖全局配置） | `http://127.0.0.1:7890` |
| `CT_RANDOM_DELAY` | 随机延迟上限（秒）：每个账号签到前随机休眠，模拟用户随机触发，防固定节奏被识别（**默认 0=关闭**，需手动设 >0 才生效） | `5` |
| `CT_RANDOM_DELAY_MIN` | 随机延迟下限（秒）；上限<下限时自动取等于上限（**默认 0**） | `2` |
| `CT_CRON` | 自动建任务的 cron（默认 `1 0 * * *`） | `30 7 * * *` |

> 每平台**最多 2 个变量名**：`CT_<平台>_COOKIE`（纯 cookie）和 `CT_<平台>_AUTH`（一体化）。只用 cookie 就配 COOKIE；想自动续期就配 AUTH（或两者都配，AUTH 优先）。

## 二、Cookie 优先 + 账号密码自动刷新（推荐）

不少论坛的 Cookie 隔一阵就失效。框架采用 **Cookie 优先、账号密码自动续期** 策略：

1. **优先用 Cookie 签到**（来自 `CT_<平台>_COOKIE` 或 `CT_<平台>_AUTH` 行里的 cookie 段）。
2. 若 Cookie 签到失败（过期/失效），且该行配了账号密码，则**自动用账号密码登录获取新 Cookie 来签到**。
3. 登录拿到的新 Cookie 会**自动写回**：优先更新青龙环境变量（AUTH 模式更新 `CT_<平台>_AUTH` 对应行；COOKIE 模式更新 `CT_<平台>_COOKIE`）；非青龙环境则写入仓库内 `.cache/cookies.json`（已被 .gitignore 忽略，仅供手动更新参考）。
4. 下次运行直接走新 Cookie，无需每次都登录 —— 实现自动续期。

### `CT_<平台>_AUTH` 一体化格式（推荐）

> 格式速记与完整可复制示例见上方「0、照着填」章节，这里只讲续期机制。

每行一个账号，三段用 `||` 分隔，**任意段可留空 = 跳过该段**：

```
cookie值||账号1||密码1
||账号2||密码2          # 没有 cookie，只有账号密码
cookie值3||             # 只有 cookie（也可直接写 cookie值3，无 || 视为纯 cookie）
```

- Cookie 优先：先用该行 cookie 签到；失败且有账号密码 → 登录刷新，并把新 cookie **写回这一行**。
- 多账号：用换行或 `&` 分隔多行。
- 用 `||` + 换行是因为密码里几乎不可能出现这两个字符，避免 `:`/`&` 这类单字符分隔器和 cookie/密码内容撞车。

平台 `config.yml` 里需有 `login:` 段（模板 `templates/forum_sign.yml` 已含，复制即带）。例：

```yaml
login:
  login_page: "member.php?mod=logging&action=login"
  loginfield: auto          # email | username | auto（auto 依次尝试 email / 用户名）
  auth_env: CT_EXAMPLE_AUTH  # 一体化变量名（cookie||账号||密码）
```

`login:` 段支持的字段（按站点类型选择）：

| 字段 | 说明 | 默认 |
|------|------|------|
| `login_type` | 登录后端：**`discuz`**（默认，Discuz 表单流）、**`thinkphp`**（ThinkPHP 类站点，如 3G壁纸）、**`wordpress`**（WordPress admin-ajax 类站点，如 狗破解 gopojie） | `discuz` |
| `auth_env` | 一体化变量名（cookie\|\|账号\|\|密码），自动续期写回此变量 | —— |
| `login_page` | 取 CSRF token / formhash 的页面路径 | Discuz: `member.php?mod=logging&action=login`；ThinkPHP: `user/login.html` |
| `login_api` | ThinkPHP 登录接口路径（仅 `login_type: thinkphp`） | `api/user/login` |
| `token_field` | ThinkPHP CSRF 字段名（仅 thinkphp） | `__token__` |
| `account_field` / `password_field` | ThinkPHP 账号/密码字段名（仅 thinkphp） | `account` / `password` |
| `success_code` | ThinkPHP 登录成功时的 code 值（仅 thinkphp） | `1` |
| `login_action` / `user_field` / `password_field` | WordPress 登录参数（仅 `wordpress`）：admin-ajax 的 action 名与账号/密码字段名 | `zb_user_login` / `user_name` / `user_password` |
| `nonce_page` / `nonce_regex` / `success_status` | WordPress 取 CSRF nonce 的页面/正则与登录成功判定的 status 值（仅 wordpress） | `/login` / 取 `ajax_nonce` / `1` |
| `loginfield` | Discuz 登录字段：email / username / auto | `auto` |
| `extra_fields` | 额外固定字段（如 `questionid`/`cookietime`，或有验证码时附加项） | —— |

> 例：`login_type: thinkphp` 见 `platforms/3gbizhi/config.yml`（自定义 ThinkPHP 壁纸站）；`login_type: wordpress` 见 `platforms/gopojie/config.yml`（WordPress 会员站，走 `api` 引擎 + wordpress 登录）。

> ⚠️ 验证码边界：若论坛开启了登录验证码(seccode)，账号密码无法自动通过（需人工或第三方打码，超出范围）。此时登录会清晰报错「需要验证码，无法自动登录」，并保留原 Cookie 失败结果；请改用有效 Cookie。福利吧目前不弹验证码，可正常自动刷新。

> 📌 `api` 引擎支持 **nonce 预取**：部分站点（如 WordPress admin-ajax）签到需先带 CSRF nonce，可在 `tasks[].nonce` 配置 `url`（GET 取 nonce 的页面）与 `regex`（提取正则），引擎会自动把 nonce 注入到 `data` 的 `{nonce}` 占位后发送。例见 `platforms/gopojie/config.yml`。

> 账号密码同样只存青龙环境变量，请勿写入代码或提交到 git。

## 二、如何获取 Cookie（浏览器示例）

1. 电脑浏览器登录目标论坛。
2. 打开开发者工具（F12）→ Network（网络）。
3. 刷新页面，点任意一个本站请求 → 请求头里复制完整 `Cookie` 值。
4. 在青龙「环境变量」新增：名称 `CT_FUELBA_COOKIE`，值 = 刚复制的 Cookie。
5. Cookie 会过期，失效后在青龙里更新该变量即可。

> Cookie 只存青龙环境变量，请勿写入代码或提交到 git。

## 三、全局配置（可选）

复制 `config/config.example.yml` 为 `config/config.yml`，可设代理、随机延迟、跳过平台、通知前缀。
所有项均可不填；同名环境变量（如 `CT_PROXY`、`CT_RANDOM_DELAY`、`CT_RANDOM_DELAY_MIN`）优先级更高。

### 随机延迟（模拟用户随机触发）
- 即便青龙定时任务是固定时刻（如每天 00:01），脚本也会在**每个账号签到前**随机休眠 `[CT_RANDOM_DELAY_MIN, CT_RANDOM_DELAY]` 秒，使访问节奏不规律，更像真人。
- 例：`CT_RANDOM_DELAY=5 CT_RANDOM_DELAY_MIN=2` → 每次延迟 2~5 秒随机值。
- 多账号时同样对每个账号生效；设为 `0` 则关闭（默认）。

## 四、通知渠道

默认：脚本打印摘要，青龙「设置 → 通知」里配好的渠道（Server酱 / Pushplus /  Bark / 企业微信 / 钉钉等）会自动推送任务日志。

如需脚本内额外直推，配置对应环境变量（不配则不推）：
- `PUSH_KEY` / `SERVERCHAN_SCKEY`：Server酱
- `CT_PUSHPLUS_TOKEN`：Pushplus
- `BARK_PUSH`：Bark
- `QYWX_KEY`：企业微信机器人
- `DD_BOT_TOKEN`：钉钉机器人

## 五、本地调试

仓库根目录放 `.env`（不进 git），写入上述变量，`common/config.py` 会自动加载：
```bash
CT_FUELBA_COOKIE="你的cookie"
CT_PROXY="http://127.0.0.1:7890"
```
然后本地运行 `python run_platform.py fuelba` 验证。
