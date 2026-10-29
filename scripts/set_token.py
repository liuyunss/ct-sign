#!/usr/bin/env python3
"""给某个平台写入 token / cookie 凭据（本地 .env）。

比手工编辑 .env 安全：自动备份原文件、按行替换、保持其它变量不动。

用法：
    # 写到该平台 config.yml 里 cookie_env 指定的变量（默认）
    python3 scripts/set_token.py workbuddy "<token...>"

    # 显式指定变量位（如一体化 AUTH，可带 || 三段）
    python3 scripts/set_token.py workbuddy "<token>||" --var CT_WORKBUDDY_AUTH

    # 从 stdin 读（例如粘一长串 token 时避免 shell 转义问题）
    pbpaste | python3 scripts/set_token.py workbuddy --stdin

    # 只预览要写什么，不落盘
    python3 scripts/set_token.py workbuddy "<token>" --print

平台目录不存在、或该平台 config.yml 没写 cookie_env 时，需显式 --var。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def load_cookie_env(platform: str):
    """读 platforms/<platform>/config.yml 的 cookie_env（顶层字段）。"""
    cfg_path = REPO_ROOT / "platforms" / platform / "config.yml"
    if not cfg_path.exists():
        return None
    try:
        import yaml
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        print(f"! 解析 {cfg_path.name} 失败: {e}")
        return None
    return (data.get("cookie_env") or "").strip() or None


def write_env(var: str, value: str, env_file: Path, backup: bool = True):
    """把 var=value 写进 .env：已存在则替换该行，否则追加。"""
    lines = []
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()
    if backup and env_file.exists():
        shutil.copy2(env_file, env_file.with_suffix(".env.bak"))

    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    new_line = f'{var}="{escaped}"'
    replaced = False
    out = []
    for line in lines:
        if line.strip().startswith(var + "="):
            out.append(new_line)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(new_line)

    env_file.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.chmod(env_file, 0o600)          # 含凭据，收紧权限
    return replaced


def main():
    ap = argparse.ArgumentParser(description="把 token/cookie 写入本地 .env")
    ap.add_argument("platform", help="平台目录名，如 workbuddy")
    ap.add_argument("value", nargs="?", help="要写入的值（可省略，配合 --stdin）")
    ap.add_argument("--var", help="变量名；省略则取平台 config.yml 的 cookie_env")
    ap.add_argument("--stdin", action="store_true", help="从标准输入读值")
    ap.add_argument("--print", dest="do_print", action="store_true",
                    help="只打印预览，不写文件")
    args = ap.parse_args()

    value = args.value
    if args.stdin:
        value = sys.stdin.read().strip()
    if not value:
        ap.error("缺少值：直接传参或用 --stdin")

    var = args.var
    if not var:
        var = load_cookie_env(args.platform)
        if not var:
            ap.error(f"未能从 platforms/{args.platform}/config.yml 取到 cookie_env，"
                     f"请用 --var 显式指定变量名")
        print(f"使用变量位：{var}")

    masked = value if len(value) <= 24 else f"{value[:16]}...({len(value)} 字符)"
    if args.do_print:
        print(f"[预览] {var}={masked}")
        return

    env_file = REPO_ROOT / ".env"
    replaced = write_env(var, value, env_file)
    action = "已替换" if replaced else "已新增"
    print(f"{action} → {env_file.name} 里的 {var}")
    print(f"   值：{masked}")
    print("提示：线上请到青龙环境变量面板填同名变量（{}）".format(var))
    print("注意：get_env 只在进程启动时加载一次，改完 .env 需重跑脚本。")


if __name__ == "__main__":
    main()
