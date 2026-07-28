# 如何新增一个平台（论坛签到）

照做 5 步，约 5 分钟。以「示例论坛 example」为例。新增后 `sign_all.py`（scripts/run_all.py）会自动包含它。

## 1. 建目录 + 复制模板

```bash
mkdir -p platforms/example
cp templates/forum_sign.yml platforms/example/config.yml
```

## 2. 改 config.yml

至少改这几处（详见 [模板指南](template-guide.md)）：

```yaml
platform: 示例论坛
engine: forum
base_url: "https://bbs.example.com"
cookie_env: CT_EXAMPLE_COOKIE
tasks:
  - name: 每日签到
    sign_url: "plugin.php?id=dsu_paulsign:sign"
    action_url: "plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1"
    # ...其余沿用模板
```

## 3. 配环境变量

在青龙「环境变量」按下面二选一（完整可复制示例见 [配置与凭证指南](config-guide.md) 的「0、照着填」章节）：

- 只有 Cookie（最简单）：`CT_EXAMPLE_COOKIE`，值为该论坛登录 Cookie（多账号用 `&` 或换行分隔）。
- 推荐（Cookie + 账号密码自动续期）：`CT_EXAMPLE_AUTH`，值为一体化格式 `cookie||账号||密码`——
  每段用 `||` 分隔，任意段留空即跳过；多账号用换行或 `&` 隔开。

```bash
# 例：Cookie 优先，失效时自动用账号密码登录刷新并写回该变量
CT_EXAMPLE_AUTH=你的cookie||你的账号||你的密码
```

> `config.yml` 里模板自带的 `login:` 段已经指向 `CT_EXAMPLE_AUTH`，无需改动即可用账号密码续期。
> 若论坛开启登录验证码(seccode)，账号密码无法自动通过，需回退有效 Cookie。

## 4. 手动核对

```bash
python scripts/run_platform.py example
# 或等价地用根目录符号链接：
python sign_example.py
```

看输出是否「签到成功」。若命中失败词或“无法判定”，按实际页面文案调整
`sign_url` / `action_url` / `payload` / `*_keywords`。

## 5. 建定时任务 / 交给 init

- 手动：青龙「定时任务」新建，命令 `task sign_example.py`（根目录符号链接 → scripts/run_platform.py example），计划每天 00:01。
- 自动：若用 `ql repo` 订阅，已包含的 `scripts/init.sh` 会自动把这个平台任务建好，无需手动。

> 不同论坛的签到插件与返回文案不同，第一次务必手动跑一遍核对。
> 若不是 Discuz 论坛（如走 JSON 接口），改 `engine: api` 并按 `common/engines/api.py` 注释填 `url/json/code_field`。

## 6. 非 Discuz 站点的登录类型（login_type）

框架内置三种登录后端，由 `login:` 段的 `login_type` 选择，**无需改代码**：

- `login_type: discuz`（默认）：Discuz! 表单流，自动取 formhash 登录（福利吧、科学刀等）。
- `login_type: thinkphp`：ThinkPHP 类站点（如 3G壁纸）。自动 GET 登录页抠 `__token__` →
  POST 登录接口 → 返回登录态 Cookie。需配合填写 `login_page` / `login_api` /
  `token_field` / `account_field` / `password_field` / `success_code`，完整示例见
  `platforms/3gbizhi/config.yml`。
- `login_type: wordpress`：WordPress(admin-ajax) 类站点（如 狗破解 gopojie）。自动 GET
  页面抠 `ajax_nonce` → POST `wp-admin/admin-ajax.php`（action=登录 action）→ 返回登录态
  Cookie。需配合 `login_action` / `user_field` / `password_field` / `nonce_page` /
  `success_status`，完整示例见 `platforms/gopojie/config.yml`。

> 另：`api` 引擎本身支持 `tasks[].nonce` 预取（先 GET 某页面取 CSRF nonce，再注入到
> `data` 的 `{nonce}` 占位发送），用于签到接口强制要求 nonce 的站点（如 gopojie）。

> 选错 `login_type` 会导致自动登录失败；不确定站点类型时，优先用 Cookie 模式（只配
> `CT_<平台>_COOKIE`，不写 `login:` 段），登录态失效后手动更新 Cookie 即可。
