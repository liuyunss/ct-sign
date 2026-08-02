# CT-Sign（尘签）

把多个平台的每日签到集中到青龙（QingLong）定时任务里，省去手动操作。
采用 **单仓库 + 通用引擎 + 模板驱动** 结构：通用能力抽离到 `common/`，每个平台只放一份 `config.yml`，新增平台基本只改配置、零代码。

## 特性

- **多类别引擎**：`forum`（Discuz! 表单流）、`api`（JSON 接口流，预留）——同一套框架覆盖论坛 / 电商 / 网盘 / 社交。
- **多任务类型**：一个平台可挂多个任务（签到 / 抽奖 / 做任务…），`config.yml` 的 `tasks` 列表声明即可。
- **模板驱动**：论坛签到复制 `templates/forum_sign.yml` 改几处即用，无需写代码。
- **多账号**：单变量放多个账号（`&` 或换行分隔），自动逐个跑。
- **凭证两种写法**：`CT_<平台>_COOKIE`（纯 Cookie）或 `CT_<平台>_AUTH`（一体化 `cookie||账号||密码`，任意段留空即跳过）。Cookie 优先，失效时自动用账号密码登录刷新并写回，实现续期。
- **密钥分离**：Cookie 只存青龙环境变量，代码与仓库不含任何凭证。
- **通知**：每个平台签到结束都会推送结果。**优先调用青龙自带 `send_notify`**（复用你在青龙面板配好的通道，和"仓库变动"通知走同一条线，无需再单独配）；非青龙环境（本地调试）才走脚本内直推（Server酱/Pushplus/Bark/企业微信/钉钉，需自备变量）兜底。设置 `CT_DISABLE_NOTIFY=1` 可只打印不推送。**彩蛋**：每次推送末尾会自动附一句随机「一言」（拉取 `hitokoto.cn`，失败用本地兜底文案）；设 `CT_DISABLE_QUOTE=1` 可关闭。
- **聚合推送（可选）**：设青龙环境变量 `CT_AGGREGATE_NOTIFY=1`，本仓库会在 `init.sh` 时 hook 青龙全局 `send_notify`，把**本仓库及青龙里其他仓库**的推送全部攒进缓存，由 `sign_flush.py` 任务（cron 设在所有签到之后）合并成**一天一条**统一发出。**不改任何别人脚本**——别人的脚本照样 `from notify import send_notify`，只是调用被接管进缓存。不设置该变量则完全不生效，各任务各自推送。
- **免 key 自动建任务**：`init.sh` 被青龙 `ql repo` 订阅时调用，容器内自动建好所有定时任务。

## 目录结构

```
ct-sign/
├─ common/            # 通用层（引擎 + 基础设施），所有平台共用
│  ├─ base.py         # 签到基类 + 统一结果 + 多账号/延迟
│  ├─ client.py       # HTTP 客户端
│  ├─ config.py       # 环境变量 / 全局配置读取
│  ├─ notify.py       # 通知
│  ├─ log.py          # 日志
│  ├─ loader.py       # 读取平台 config.yml → 构造 Signer
│  ├─ qlapi.py        # 青龙 OpenAPI（容器内免 key 建任务）
│  └─ engines/        # 引擎实现
│     ├─ forum.py      # Discuz! 表单流
│     └─ api.py        # JSON 接口流（预留）
├─ platforms/         # 个性化：每个平台一个目录，只放 config.yml
│  ├─ _template/      # 示例（不直接运行）
│  ├─ fuliba/
│  ├─ 55188/
│  └─ hyperdown/
├─ signs/             # 各平台签到入口脚本（sign_*.py 本体）
│  ├─ sign_fuliba.py
│  ├─ sign_pcbeta.py
│  ├─ sign_55188.py
│  ├─ sign_hyperdown.py
│  └─ ...（每个平台一个，约定只一行 main("平台key")）
├─ scripts/           # 内部通用脚本（不被 ql repo 白名单匹配，不会建成任务）
│  ├─ run_all.py      # 一键跑全部（sign_all.py 转发到这里）
│  ├─ run_platform.py # 单平台：python scripts/run_platform.py fuliba
│  ├─ init.sh         # ql repo 初始化命令：装依赖（任务由白名单 sign_ 自动建）
│  └─ init.py         # 手动兜底工具：仅清理野任务（python3 scripts/init.py --dry-run）
├─ templates/         # 主模板 forum_sign.yml（复制即用）
├─ config/            # 全局配置模板
├─ requirements.txt
├─ README.md
├─ LICENSE
└─ docs/              # 架构 / 配置 / 模板 / 加平台
```

> **目录布局说明**：`sign_*.py` 入口统一收进 `signs/`（青龙 `ql repo` 的白名单 `sign_` 会扫描整个仓库，直接命中 `signs/` 下的入口，无需在根目录放符号链接）；`run_all.py` / `run_platform.py` / `init.py` / `init.sh` 这类内部脚本收进 `scripts/`，文件名不匹配白名单，不会建成任务。这样仓库根目录保持干净，且 `ql repo` 能正确建出每个平台一行任务，也不会因根目录与 `signs/` 同时存在 `sign_*` 而重复建任务。

## 快速开始（青龙里）

> 以下命令在青龙容器终端执行（面板左侧「终端」，或 `docker exec -it ql bash`）。

### 1. 订阅仓库（自动装依赖 + 建好所有定时任务）

```bash
ql repo https://github.com/liuyunss/ct-sign.git "sign_" "" "init.sh" "master"
```

参数顺序：仓库URL | 白名单 `sign_` | 黑名单(留空) | 初始化命令 `init.sh` | 分支 `master`。

**白名单 `sign_` 是关键**：它让 `ql repo` 只把仓库里 `sign_*.py` 这些「每个平台一个」的入口脚本建成定时任务——也就是一行一个任务、青龙原生日志，和常见脚本库（如 smzdm_script）一样。内部库文件 `common/`、通用入口 `run_platform.py` / `run_all.py`、初始化 `init.py` 都不匹配白名单，自然不会被建成任务，因此**不会有野任务，也不依赖青龙 API 令牌**（彻底免去令牌获取失败的坑）。

执行后自动 `pip install -r requirements.txt`，并直接得到下列定时任务（每个平台一行，青龙原生日志，默认每天 00:01）：

| 任务（文件名即任务名） | 对应平台 |
|---|---|
| `sign_fuliba.py` | 福利吧 |
| `sign_gopojie.py` | 狗破解 |
| `sign_kxdao.py` | 科学刀 |
| `sign_youjiaoku.py` | 幼教库 |
| `sign_pinggu.py` | 经管之家 |
| `sign_3gbizhi.py` | 3G壁纸 |
| `sign_pcbeta.py` | 远景论坛 |
| `sign_55188.py` | 55188 理想论坛 |
| `sign_hyperdown.py` | Hyperdown |
| `sign_all.py` | 全部签到（一次性全平台） |
| `sign_flush.py` | 聚合推送（仅 `CT_AGGREGATE_NOTIFY=1` 时启用，设在所有签到之后） |

> **之前用旧命令订阅、定时任务里残留 `xxx.py` / `__init__.py` 野任务？**
> 在青龙「订阅管理」把本仓库订阅命令改为上面的**白名单 `sign_`** 版本，保存后点「重新拉取」即可：青龙会删除该订阅之前建的任务、再只按白名单建出 `sign_*` 任务，野任务随之消失。
>
> 若重新拉取后仍残留野任务，可在青龙「终端」手动兜底清理（只删本仓库内的野任务，不碰其它任务）：
> ```bash
> cd /ql/data/repo/liuyunss_ct-sign_master   # 目录名以实际为准
> python3 scripts/init.py --dry-run   # 先预览会清理哪些
> python3 scripts/init.py             # 确认无误后再执行清理
> ```
> 注：`init.py` 现在位于 `scripts/` 下，只做**野任务清理**，不再建任务（建任务由 `ql repo` 白名单 `sign_*` 负责），正常用 ql repo 订阅不需要它。

### 2. 添加环境变量（值换成你自己的；多账号用 `&` 或换行分隔）

> **在哪加**（两种方式任选，效果一样）：
> - **面板 UI（推荐，不用敲命令）**：左侧菜单「环境变量」→ 右上角「新建」，逐条填「名称」和「值」即可。
> - **命令行**：在青龙容器终端（面板左侧「终端」，或 `docker exec -it ql bash`）执行下方 `ql env add '名称=值'`。
>
> 规则：**能账号密码自动续期的平台只填一个 `CT_<平台>_AUTH`**（一体化 `cookie||账号||密码`，cookie 段留空也行，首次登录后自动写回）；
> **有验证码无法自动登录的平台**（幼教库 / 经管之家）只能手动填 `CT_<平台>_COOKIE`。

```bash
# —— 账号密码自动续期（一体化 cookie||账号||密码，cookie 段留空即可）——
ql env add 'CT_FULIBA_AUTH=||yourname@example.com||你的密码'
ql env add 'CT_GOPOJIE_AUTH=||yourname@example.com||你的密码'
ql env add 'CT_KXDAO_AUTH=||yourname@example.com||你的密码'
ql env add 'CT_3GBIZHI_AUTH=||账号||密码'
ql env add 'CT_PCBETA_AUTH=||yourname@example.com||你的密码'
ql env add 'CT_HYPERDOWN_AUTH=||yourname@example.com||你的密码'

# —— 必须手动给 cookie（登录有滑块/极验验证码，无法自动登录）——
ql env add 'CT_YOUJIAOKU_COOKIE=粘贴的cookie'
ql env add 'CT_PINGGU_COOKIE=粘贴的cookie'
ql env add 'CT_55188_COOKIE=粘贴的cookie'
```

取 cookie 方法见 `docs/config-guide.md`。

### 3. 立即跑一次验证（也可等每天 00:01 自动触发）

```bash
task sign_all.py                 # 全部平台一起签（signs/sign_all.py → scripts/run_all.py）
task sign_youjiaoku.py           # 只签某个平台（signs/sign_youjiaoku.py → scripts/run_platform.py youjiaoku）
# 本地调试也可直接：
python scripts/run_all.py
python scripts/run_platform.py youjiaoku
```

### 4.（可选）随机延迟错峰

默认固定 00:01 触发。想让各账号在触发后随机错峰，加两个环境变量：

```bash
ql env add 'CT_RANDOM_DELAY=300'
ql env add 'CT_RANDOM_DELAY_MIN=60'
```


## 支持的平台（v1）

| 平台名字 | 网址 | 所需变量 |
|----------|------|----------|
| 福利吧 | https://www.wnflb2023.com | `CT_FULIBA_AUTH`（支持账号密码自动续期；也可只用 `CT_FULIBA_COOKIE`） |
| 科学刀 KXDAO | https://www.kxdao.net | `CT_KXDAO_AUTH`（支持账号密码自动续期；也可只用 `CT_KXDAO_COOKIE`） |
| 狗破解 GoPoJie | https://www.gopojie.com | `CT_GOPOJIE_AUTH`（支持账号密码自动续期；也可只用 `CT_GOPOJIE_COOKIE`） |
| 3G壁纸 | https://www.3gbizhi.com | `CT_3GBIZHI_AUTH`（支持账号密码自动续期；也可只用 `CT_3GBIZHI_COOKIE`） |
| 远景论坛 PCBETA | https://bbs.pcbeta.com | `CT_PCBETA_AUTH`（支持账号密码自动续期；也可只用 `CT_PCBETA_COOKIE`） |
| 幼教库 YouJiaoKu | https://www.youjiaoku.com | `CT_YOUJIAOKU_COOKIE`（登录有滑块验证码，不支持账号密码，需手动提供 cookie） |
| 经管之家 PingGu | https://bbs.pinggu.org | `CT_PINGGU_COOKIE`（登录为自建 passport+极验滑块，不支持账号密码，需手动提供 cookie） |
| 55188 理想论坛 | https://www.55188.com | `CT_55188_COOKIE`（登录含 passport 校验，不支持账号密码自动登录，需手动提供 cookie） |
| Hyperdown | https://hyperdown.net | `CT_HYPERDOWN_AUTH`（邮箱密码登录，签到经 SealJSON 加密；也可只用 `CT_HYPERDOWN_COOKIE` 手动提供 access_token） |

> 变量规则：**支持账号密码自动续期**的平台用 `CT_<平台>_AUTH`（一体化 `cookie||账号||密码`，也可只用 `CT_<平台>_COOKIE`）；**不支持**（有验证码无法自动登录）的平台只用 `CT_<平台>_COOKIE`。

平台涵盖 Discuz / WordPress / ThinkPHP 三类，分别走 `forum` / `api` 引擎；加新平台见 `docs/add-platform.md`。

## 文档

- [架构设计](docs/architecture.md)
- [配置与取 Cookie 指南](docs/config-guide.md)
- [模板填写指南](docs/template-guide.md)
- [如何新增一个平台](docs/add-platform.md)
