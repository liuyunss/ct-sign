#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""青龙定时任务中文名重命名（订阅拉取后由 init.sh 自动调用，无需手动）。

背景：ql repo 白名单 sign_ 建出的任务名默认是脚本文件名（如 sign_3gbizhi.py），
无法自定义成中文。本脚本把这些任务重命名为中文友好名（如「3G壁纸 签到」），
复用青龙自带 OpenAPI（容器内自动读取 /ql/config/auth.json 令牌）。

安全边界：
  - 只处理「本仓库目录内、命令含 sign_」的任务；
  - 只改任务 name 字段，绝不删任务、不改 command/schedule；
  - 拿不到令牌或任何异常都静默跳过（不影响签到），以 exit 0 结束，
    不会让 init.sh（set -e）中断依赖安装。
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from common.qlapi import list_crons, update_cron


def _platform_map():
    """扫描 platforms/*/config.yml，返回 {目录名: 中文平台名}。"""
    m = {}
    plat_dir = os.path.join(ROOT, "platforms")
    if not os.path.isdir(plat_dir):
        # 容器里脚本在 /ql/data/repo/<同名目录>/scripts，platforms 在上层
        repo_root = "/ql/data/repo"
        if os.path.isdir(repo_root):
            for name in os.listdir(repo_root):
                cand = os.path.join(repo_root, name, "platforms")
                if os.path.isdir(cand):
                    plat_dir = cand
                    break
    try:
        import yaml
    except Exception:
        return m
    if not os.path.isdir(plat_dir):
        return m
    for d in sorted(os.listdir(plat_dir)):
        cfg = os.path.join(plat_dir, d, "config.yml")
        if not os.path.isfile(cfg):
            continue
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            name = data.get("platform") or d
            m[d] = name
        except Exception:
            continue
    return m


def main():
    try:
        crons, err = list_crons()
        if crons is None:
            print(f"[重命名] 跳过：{err}")
            return
        pmap = _platform_map()
        repo_base = os.path.basename(ROOT)  # 如 liuyunss_ct-sign_master
        renamed = 0
        for t in crons:
            cmd = t.get("command", "")
            name = t.get("name", "")
            # 只处理本仓库里、命令含 sign_ 入口的任务
            if "sign_" not in cmd or repo_base not in cmd:
                continue
            m = re.search(r"sign_([A-Za-z0-9_]+)\.py", cmd)
            if not m:
                continue
            key = m.group(1)
            if key == "all":
                new_name = "全部签到"
            else:
                pname = pmap.get(key)
                if not pname:
                    continue
                new_name = f"{pname} 签到"
            if name == new_name:
                continue
            ok, msg = update_cron(
                t.get("id"), new_name, cmd, t.get("schedule", "1 0 * * *"))
            if ok:
                renamed += 1
                print(f"[重命名] {name} -> {new_name}")
            else:
                print(f"[重命名] 失败：{name} ({msg})")
        print(f"[重命名] 完成，共改写 {renamed} 个任务名")
    except Exception as e:
        print(f"[重命名] 异常跳过：{e}")


if __name__ == "__main__":
    main()
