# 模板填写指南

论坛签到统一用 `templates/forum_sign.yml` 这一个模板。复制 → 改几处 → 配 Cookie，即可接入。

## 复制模板

```bash
cp templates/forum_sign.yml platforms/<你的平台>/config.yml
```

## 必改的字段（4~5 处）

| 字段 | 填什么 | 说明 |
|------|--------|------|
| `platform` | 显示名 | 出现在通知里，如 `福利吧` |
| `base_url` | 站点域名 | 不含末尾 `/`，如 `https://www.wnflb2023.com` |
| `cookie_env` | 环境变量名 | 前缀 `CT_`，如 `CT_FUELBA_COOKIE` |
| `tasks[].sign_url` | 签到页地址 | 一般 `plugin.php?id=xxx:sign` |
| `tasks[].action_url` | 提交地址 | 同 sign_url 或带 `operation=qiandao` |

## 可能需要微调的字段

- `payload`：提交字段。Discuz 运气签到通常是 `formhash` + `qdxq`(心情) + `qdmode` + `tosign`。
- `formhash_re`：从签到页 HTML 抠 `formhash` 的正则，多数论坛是
  `name="formhash" value="([a-f0-9]+)"`。
- `*_keywords`：成功/已签/失败的判定词，**按站点实际返回文案填**，这是最容易出错的地方。

## 怎么知道该填什么？

1. 浏览器登录论坛，打开签到页，F12 看网络请求：
   - 签到页 HTML 里搜 `formhash`，确认正则能匹配。
   - 点「签到」按钮，看它 POST 到哪个 URL、提交了哪些字段。
2. 把这些信息填进模板。
3. 本地 `python run_platform.py <平台>` 跑一次，看输出：
   - 命中 `fail_keywords` → 调整关键词或 payload。
   - 输出“无法判定”→ 看响应片段，补 `success_keywords` / `already_keywords`。

## 多任务 / 多账号

- 多任务：在 `tasks` 列表再加一项（如抽奖），引擎不变。
- 多账号：`cookie_env` 里放多个 Cookie，用 `&` 或换行分隔，引擎自动逐个跑。
