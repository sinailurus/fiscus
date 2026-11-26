# -*- coding: utf-8 -*-
"""SQLite 数据层：建表、连接、设置 KV。全部使用标准库，无第三方 ORM。

四张业务表（零预置规则、零推算，全部为用户手动录入的数据）：
- cards    卡片：卡名 / 银行 / 卡面色 / 卡面图 / 账单日 / 还款日 / 提前提醒天数
- bills    账单期：某月应还金额（手填）+ 还款截止日 + 已还状态
- fees     年费：金额 / 下次年费日 / 免年费条件描述 / 目标笔数 / 已刷笔数（手动计数）
- benefits 权益：名称 / 总量 / 已用 / 固定到期日或周期刷新
"""
import os
import sqlite3
from contextlib import contextmanager

# 数据目录：容器内默认 /data（volume 挂载点），本地调试回退到 ./data
DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)
MEDIA_DIR = os.path.join(DATA_DIR, "media")   # 品牌资产与卡面图：bg / icon / cards

SCHEMA_VERSION = 1


def init_db() -> None:
    """初始化数据库与目录结构（幂等，可重复执行）。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(MEDIA_DIR, exist_ok=True)
    os.makedirs(os.path.join(MEDIA_DIR, "cards"), exist_ok=True)
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cards (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL,
                bank         TEXT NOT NULL DEFAULT '',
                color        TEXT NOT NULL DEFAULT '#4F6EF7',
                card_image   TEXT NOT NULL DEFAULT '',
                bill_day     INTEGER NOT NULL DEFAULT 0,
                repay_day    INTEGER NOT NULL DEFAULT 5,
                lead_days    INTEGER NOT NULL DEFAULT 0,
                limit_amount REAL NOT NULL DEFAULT 0,
                notes        TEXT NOT NULL DEFAULT '',
                sort_order   INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bills (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id    INTEGER NOT NULL,
                period     TEXT NOT NULL,
                amount     REAL NOT NULL DEFAULT 0,
                due_date   TEXT NOT NULL,
                paid       INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(card_id, period),
                FOREIGN KEY(card_id) REFERENCES cards(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS fees (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id      INTEGER NOT NULL UNIQUE,
                amount       REAL NOT NULL DEFAULT 0,
                next_date    TEXT NOT NULL DEFAULT '',
                rule_note    TEXT NOT NULL DEFAULT '',
                target_count INTEGER NOT NULL DEFAULT 0,
                done_count   INTEGER NOT NULL DEFAULT 0,
                updated_at   TEXT NOT NULL,
                FOREIGN KEY(card_id) REFERENCES cards(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS benefits (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id    INTEGER NOT NULL,
                name       TEXT NOT NULL,
                total      INTEGER NOT NULL DEFAULT 0,
                used       INTEGER NOT NULL DEFAULT 0,
                expire_type TEXT NOT NULL DEFAULT 'date',
                expire_date TEXT NOT NULL DEFAULT '',
                cycle      TEXT NOT NULL DEFAULT 'yearly',
                next_reset TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(card_id) REFERENCES cards(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_bills_card ON bills(card_id, period);
            CREATE INDEX IF NOT EXISTS idx_benefits_card ON benefits(card_id);
            """
        )


@contextmanager
def db():
    """按请求开启连接；WAL 模式提升并发读性能。"""
    conn = sqlite3.connect(os.path.join(DATA_DIR, "fiscus.db"), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
