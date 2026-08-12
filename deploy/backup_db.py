#!/usr/bin/env python3
"""SQLite 数据库自动备份：每天备份，保留最近 14 份，自动删除更早的。

用法（systemd timer 每天调用）:
    python3 /home/ubuntu/server-monitor/deploy/backup_db.py

配置: SRC 数据库路径, BACKUP_DIR 备份目录, KEEP 保留份数。
"""
import glob
import os
import shutil
import sqlite3
import sys
import time

SRC = os.environ.get("MONITOR_DB", "/var/lib/server-monitor/data.db")
BACKUP_DIR = "/var/lib/server-monitor/backups"
KEEP = 1  # 只保留最近 1 份，更早的自动删除


def backup() -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(BACKUP_DIR, f"data_{stamp}.db")

    # sqlite3 .backup API：WAL 模式下也安全（在线备份，不影响写入）
    src_conn = sqlite3.connect(SRC)
    try:
        dst_conn = sqlite3.connect(dst)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()

    # 删除旧备份，只保留最近 KEEP 份
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "data_*.db")))
    removed = []
    for old in backups[:-KEEP]:
        os.remove(old)
        removed.append(os.path.basename(old))

    size_mb = round(os.path.getsize(dst) / 1024 / 1024, 2)
    return f"备份完成: {os.path.basename(dst)} ({size_mb} MB)，当前共 {min(len(backups), KEEP)} 份" + \
           (f"，已删除旧备份 {len(removed)} 份" if removed else "")


if __name__ == "__main__":
    try:
        print(backup())
    except Exception as e:
        print(f"备份失败: {e}", file=sys.stderr)
        sys.exit(1)
