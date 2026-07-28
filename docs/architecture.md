# 架构设计

## 设计原则

- **单仓库**：所有脚本在一个 git 仓库，便于版本管理与 `ql repo` 同步。
- **通用分层**：`common/` 放引擎与基础设施，平台差异只在 `platforms/<名>/config.yml`。
- **模板驱动**：论坛签到复制模板改配置即可，零代码加平台。
- **密钥分离**：Cookie/Token 只存青龙环境变量，代码与仓库不含凭证。
- **可扩展**：多类别引擎（forum/api）+ 多任务类型（tasks 列表），未来加平台/加任务类型只改配置。

## 分层与数据流

```
青龙「脚本管理」(ql repo 拉入)
   └─ 定时任务 task sign_all.py / sign_<平台>.py（根目录符号链接 → scripts/run_all.py / scripts/run_platform.py <平台>）
        └─ common/loader.py 读取 platforms/<名>/config.yml
             └─ 按 engine 名映射出 Signer（ForumSigner / ApiSigner）
                  └─ BaseSigner.run()：拆分多账号 → 逐个 _run_one()
                       ├─ HttpClient GET 签到页 → 抠 formhash
                       ├─ HttpClient POST 签到（替换 {formhash}）
                       └─ 按 success/already/fail 关键词判定 → SignResult
             └─ 汇总所有任务结果 → notify() 打印 → 青龙推送日志
```

## 组件职责

| 文件 | 职责 |
|------|------|
| `common/base.py` | `BaseSigner`（多账号拆分/延迟/汇总）+ `SignResult`（统一结果） |
| `common/client.py` | `HttpClient`：会话复用、重试、UA、Cookie、代理、编码 |
| `common/config.py` | 环境变量 / 全局 `config.yml` 读取，本地 `.env` 支持 |
| `common/notify.py` | 打印摘要 + 可选直推 Server酱/Pushplus/Bark/企微/钉钉 |
| `common/log.py` | 统一日志格式（输出 stdout，青龙抓取推送） |
| `common/loader.py` | 发现平台、读 `config.yml`、构造 Signer 列表 |
| `common/engines/forum.py` | Discuz! 表单流：GET→formhash→POST→关键词 |
| `common/engines/api.py` | JSON 接口流（预留）：POST/GET→JSON code 判定→回退关键词 |
| `common/qlapi.py` | 青龙 OpenAPI：容器内免 key / 容器外凭据建任务 |

## 为什么能“通用”

- **引擎通用**：所有 Discuz 论坛共用 `ForumSigner`；JSON 接口类共用 `ApiSigner`。
- **仅配置不同**：同一引擎下不同论坛的差异（URL、字段、关键词）全部在 `config.yml`，
  引擎代码一行不动。
- **多任务类型**：平台的 `tasks` 列表可挂多个任务（签到/抽奖/做任务），每个任务只是
  引擎的一次参数化调用，无需新写逻辑。

## 调度方式

- **每平台独立任务**：`task sign_<平台>.py`（→ scripts/run_platform.py <平台>），失败隔离、可单独补签。
- **一键任务**：`task sign_all.py`（→ scripts/run_all.py），自动发现并跑全部。
- **自动建任务**：`scripts/init.sh`（被 `ql repo` 初始化命令调用）读取所有平台，在青龙内自动建任务，免 key。

## 扩展路线（已预留接口）

- 新论坛：复制模板 → 填 `config.yml` → 配 Cookie。零代码。
- 新类别（电商/网盘/社交）：在 `common/engines/` 加一个引擎类，注册进 `ENGINE_MAP`，写对应 `config.yml`。
- 新任务类型（抽奖/做任务/领券）：在平台 `tasks` 列表加一项，引擎不变。
