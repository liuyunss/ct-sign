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
- **通知**：默认打印摘要，青龙自带通知（Server酱 / Pushplus /  Bark / 企业微信 / 钉钉）自动推送；另含脚本内直推兜底。
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
│  └─ fuelba/
├─ templates/         # 主模板 forum_sign.yml（复制即用）
├─ config/            # 全局配置模板
├─ run_all.py         # 一键跑全部
├─ run_platform.py    # 单平台：python run_platform.py fuelba
├─ init.sh / init.py  # 装依赖 + 自动建任务
├─ requirements.txt
├─ README.md
├─ LICENSE
└─ docs/              # 架构 / 配置 / 模板 / 加平台
```

## 快速开始（青龙里）

> 以下命令在青龙容器终端执行（面板左侧「终端」，或 `docker exec -it ql bash`）。

### 1. 订阅仓库（自动装依赖 + 建好所有定时任务）

```bash
ql repo https://github.com/liuyunss/ct-sign.git "" "common/.*|init\.py" "init.sh" "master"
```

参数顺序：仓库URL | 白名单(留空) | 黑名单 `common/.*|init\.py` | 初始化命令 `init.sh` | 分支 `master`。
黑名单让 `ql repo` 不要把项目内部库文件（`common/`）和初始化脚本 `init.py` 误建成定时任务。

执行后自动 `pip install -r requirements.txt`，并通过青龙 API 建好**每个平台 + 全部签到**的定时任务，任务名形如 `CT-Sign 福利吧 签到`、`CT-Sign 全部签到`（中文平台名，一眼能分清）。`init.py` 还会顺手删除订阅时误建的「文件名式」野任务（如 `run_all.py`、`init.py`）。
（若 `init.sh` 未自动执行，在面板「订阅管理」把该订阅的初始化命令设为 `init.sh` 再运行一次；任务建好后想重排，直接重跑 `python3 init.py` 即可，已存在的不会重复创建。）

### 2. 添加环境变量（值换成你自己的；多账号用 `&` 或换行分隔）

```bash
# 福利吧（已实测，可只给账号密码自动续期）
ql env add 'CT_FUELBA_COOKIE=粘贴的cookie'
ql env add 'CT_FUELBA_AUTH=||yourname@example.com||你的密码'

# 狗破解 / 科学刀（均可自动登录续期）
ql env add 'CT_GOPOJIE_AUTH=||yourname@example.com||你的密码'
ql env add 'CT_KXDAO_AUTH=||yourname@example.com||你的密码'

# 幼教库 / 经管之家（登录有滑块/极验验证码，必须手动给 cookie）
ql env add 'CT_YOUJIAOKU_COOKIE=粘贴的cookie'
ql env add 'CT_PINGGU_COOKIE=粘贴的cookie'

# 3G壁纸（待青龙验证）
ql env add 'CT_3GBIZHI_AUTH=||账号||密码'
```

取 cookie 方法见 `docs/config-guide.md`。

### 3. 立即跑一次验证（也可等每天 00:01 自动触发）

```bash
task run_all.py                 # 全部平台一起签
task run_platform.py youjiaoku  # 只签某个平台
```

### 4.（可选）随机延迟错峰

默认固定 00:01 触发。想让各账号在触发后随机错峰，加两个环境变量：

```bash
ql env add 'CT_RANDOM_DELAY=300'
ql env add 'CT_RANDOM_DELAY_MIN=60'
```


## 支持的平台（v1）

| 平台名字 | 网址 | 所需变量 | 状态 |
|----------|------|----------|------|
| 福利吧 | https://www.wnflb2023.com | `CT_FUELBA_AUTH`（支持账号密码自动续期；也可只用 `CT_FUELBA_COOKIE`） | ✅ 已实测（Discuz，forum 引擎） |
| 科学刀 KXDAO | https://www.kxdao.net | `CT_KXDAO_AUTH`（支持账号密码自动续期；也可只用 `CT_KXDAO_COOKIE`） | ✅ 已实测（Discuz，forum 引擎） |
| 狗破解 GoPoJie | https://www.gopojie.com | `CT_GOPOJIE_AUTH`（支持账号密码自动续期；也可只用 `CT_GOPOJIE_COOKIE`） | ✅ 已实测（WordPress，api 引擎） |
| 3G壁纸 | https://www.3gbizhi.com | `CT_3GBIZHI_AUTH`（支持账号密码自动续期；也可只用 `CT_3GBIZHI_COOKIE`） | ⏳ 待青龙验证（ThinkPHP，api 引擎） |
| 幼教库 YouJiaoKu | https://www.youjiaoku.com | `CT_YOUJIAOKU_COOKIE`（登录有滑块验证码，不支持账号密码，需手动提供 cookie） | ⚠️ 需手动提供 cookie（WordPress，api 引擎） |
| 经管之家 PingGu | https://bbs.pinggu.org | `CT_PINGGU_COOKIE`（登录为自建 passport+极验滑块，不支持账号密码，需手动提供 cookie） | ⚠️ 需手动提供 cookie（Discuz+dsu_paulsign，forum 引擎） |

> 变量规则：**支持账号密码自动续期**的平台用 `CT_<平台>_AUTH`（一体化 `cookie||账号||密码`，也可只用 `CT_<平台>_COOKIE`）；**不支持**（有验证码无法自动登录）的平台只用 `CT_<平台>_COOKIE`。

平台涵盖 Discuz / WordPress / ThinkPHP 三类，分别走 `forum` / `api` 引擎；加新平台见 `docs/add-platform.md`。

## 文档

- [架构设计](docs/architecture.md)
- [配置与取 Cookie 指南](docs/config-guide.md)
- [模板填写指南](docs/template-guide.md)
- [如何新增一个平台](docs/add-platform.md)
