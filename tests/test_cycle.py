# -*- coding: utf-8 -*-
"""还款闭环专项验证（2026-11-26 TA 点名的重要功能）：

勾选已还 → 本账单周期邮件不再提醒 → 下个账单周期自动恢复提醒。
时间穿越用 monkeypatch today() 实现，不动系统时间。
"""
import datetime
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="fiscus_cycletest_")

import app.reminders as R          # noqa: E402
from app import db as app_db       # noqa: E402

results = []


def check(name, ok, extra=""):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {extra}")


app_db.init_db()
conn = sqlite3.connect(os.path.join(os.environ["DATA_DIR"], "fiscus.db"))
conn.row_factory = sqlite3.Row

today = datetime.date.today()
repay_day = min(28, today.day + 2) or 28      # 两天后还款，必然落在提醒窗口
now = datetime.datetime.now().isoformat(timespec="seconds")
cur = conn.execute(
    "INSERT INTO cards (name, bank, repay_day, lead_days, created_at, updated_at)"
    " VALUES ('招行白金卡','招商银行',?,0,?,?)", (repay_day, now, now))
card_id = cur.lastrowid

from app.schedule import next_monthly
nd = next_monthly(repay_day, today)
period = nd.isoformat()[:7]

# ---- 第 1 步：勾选前，还款提醒命中 ----
e1 = [x for x in R.notify_entries(conn, 5) if x["kind"] == "repay" and x["card"] == "招行白金卡"]
check("勾选前：还款提醒命中", len(e1) == 1, f"entries={len(e1)}")

# ---- 第 2 步：勾选已还（等效待办页 ✓ / 详情页「标记已还」） ----
conn.execute(
    "INSERT INTO bills (card_id, period, amount, due_date, paid, created_at, updated_at)"
    " VALUES (?,?,?,?,1,?,?)", (card_id, period, 2400.0, nd.isoformat(), now, now))
e2 = [x for x in R.notify_entries(conn, 5) if x["kind"] == "repay" and x["card"] == "招行白金卡"]
check("勾选后：本周期不再提醒", len(e2) == 0, f"entries={len(e2)}")

# 快照口径同步确认：列表/待办页显示「已还清」
snap = R.snapshot(conn)
c = next(x for x in snap["cards"] if x["id"] == card_id)
check("界面口径：已还清且退出待办", c["bill_paid"] is True)

# ---- 第 3 步：时间穿越到下个账单周期（下期还款日前 2 天，落在提醒窗口内） ----
next_due_next = next_monthly(repay_day, nd + datetime.timedelta(days=1))
next_period_start = next_due_next - datetime.timedelta(days=2)
R.today = lambda: next_period_start          # 模块级 today() 全部生效
e3 = [x for x in R.notify_entries(conn, 5) if x["kind"] == "repay" and x["card"] == "招行白金卡"]
check("下周期：提醒自动恢复", len(e3) == 1,
      f"entries={len(e3)}, 新还款日={e3[0]['date'] if e3 else '-'}")
R.today = lambda: today

fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)}/{len(results)} 通过")
if __name__ == "__main__":
    sys.exit(1 if fails else 0)
