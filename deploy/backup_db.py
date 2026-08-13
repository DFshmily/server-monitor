#!/usr/bin/env python3
"""SQLite 轻量备份：只备份关键数据表（账号/规则/审计等），不含可再生的监控原始数据。

监控原始数据(metrics_raw/metrics_agg)每天自动清理且可再生，无需备份；
真正值钱的是 users / 邀请码 / 告警规则 / 探活规则 / 审计等小表。
备份文件从 1GB 缩小到几百 KB，保留最近 1 份，自动删除更早的。

备份成功后向心跳 URL 报平安（配合面板"心跳监控"：任务挂了会告警）：
    HEARTBEAT_URL=https://dashboard.dfshmily.icu/api/heartbeat/<slug> python3 backup_db.py

用法（systemd timer 每天调用）:
    python3 /home/ubuntu/server-monitor/deploy/backup_db.py
"""
import glob
import os
import sqlite3
import sys
import time
import urllib.request

SRC = os.environ.get("MONITOR_DB", "/var/lib/server-monitor/data.db")
BACKUP_DIR = "/var/lib/server-monitor/backups"
KEEP = 1  # 只保留最近 1 份，更早的自动删除
HEARTBEAT_URL = os.environ.get("HEARTBEAT_URL", "")  # 备份成功后的心跳通知

# 关键表：账号、邀请码、规则、审计、探活配置/结果、别名
KEY_TABLES = [
    "users", "invites", "email_codes", "login_attempts",
    "alert_rules", "alert_events",
    "probe_rules", "probe_results",
    "maintenance_windows", "audit_logs", "server_meta",
]


def backup() -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    # 毫秒级时间戳：避免同一秒内连续执行时文件名冲突
    stamp = time.strftime("%Y%m%d_%H%M%S") + f"{int(time.time() * 1000) % 1000:03d}"
    dst = os.path.join(BACKUP_DIR, f"config_{stamp}.db")
    if os.path.exists(dst):
        os.remove(dst)

    src_conn = sqlite3.connect(SRC)
    try:
        dst_conn = sqlite3.connect(dst)
        try:
            with src_conn:  # 读快照事务
                for table in KEY_TABLES:
                    row = src_conn.execute(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
                    ).fetchone()
                    if not row or not row[0] or row[0].startswith("CREATE VIRTUAL"):
                        continue
                    dst_conn.execute(row[0])  # 建表（含 UNIQUE 等约束）
                    cols = [c[1] for c in src_conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
                    if not cols:
                        continue
                    col_sql = ", ".join(f'"{c}"' for c in cols)
                    placeholders = ", ".join("?" * len(cols))
                    data = src_conn.execute(f'SELECT {col_sql} FROM "{table}"').fetchall()
                    if data:
                        dst_conn.executemany(
                            f'INSERT INTO "{table}" ({col_sql}) VALUES ({placeholders})', data
                        )
            dst_conn.commit()
        finally:
            dst_conn.close()
    finally:
        src_conn.close()

    # 删除旧备份，只保留最近 KEEP 份（兼容旧版 data_*.db 整库备份一并清理）
    # 注意：必须按 mtime 排序，不能按文件名（config_/data_ 前缀混排会误删新备份）
    backups = sorted(
        glob.glob(os.path.join(BACKUP_DIR, "config_*.db")) +
        glob.glob(os.path.join(BACKUP_DIR, "data_*.db")),
        key=os.path.getmtime,
    )
    removed = []
    for old in backups[:-KEEP]:
        os.remove(old)
        removed.append(os.path.basename(old))

    size_kb = round(os.path.getsize(dst) / 1024, 1)
    msg = f"轻量备份完成: {os.path.basename(dst)} ({size_kb} KB)，当前共 {min(len(backups), KEEP)} 份" + \
          (f"，已删除旧备份 {len(removed)} 份" if removed else "")

    # 心跳报平安（失败不影响备份本身）
    if HEARTBEAT_URL:
        try:
            with urllib.request.urlopen(HEARTBEAT_URL, timeout=10) as resp:
                if resp.status != 200:
                    print(f"心跳上报失败: HTTP {resp.status}", file=sys.stderr)
        except Exception as e:
            print(f"心跳上报失败: {e}", file=sys.stderr)
    return msg


if __name__ == "__main__":
    try:
        print(backup())
    except Exception as e:
        print(f"备份失败: {e}", file=sys.stderr)
        sys.exit(1)
