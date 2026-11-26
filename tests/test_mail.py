# -*- coding: utf-8 -*-
"""邮件正文模板单测（无服务依赖，内存库直跑）。

覆盖草图定稿（2026-11-26）的三条规则：
1. 普通条目带卡面图（有图 CID 内嵌 / 无图首字色块）；
2. 过长卡名截断省略；
3. 信报合一：同银行多卡归组，组头银行 logo（自传）或首字色块。
"""
import datetime
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="fiscus_mailtest_")

from app import db as app_db          # noqa: E402  DATA_DIR 须先于 import 设置
from app.mailer import build_html     # noqa: E402
from app.reminders import notify_entries  # noqa: E402

results = []


def check(name, ok, extra=""):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {extra}")


def iso(days_from_now: int) -> str:
    d = datetime.date.today() + datetime.timedelta(days=days_from_now)
    return d.isoformat()


def add_card(conn, name, bank, repay_day, combined=0, color="#4F6EF7", image="", logo=""):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO cards (name, bank, color, card_image, bank_logo, repay_day,"
        " report_combined, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (name, bank, color, image, logo, repay_day, combined, now, now))
    card_id = cur.lastrowid
    from app.schedule import next_monthly
    next_due = next_monthly(repay_day, datetime.date.today())
    period = next_due.isoformat()[:7]
    conn.execute(
        "INSERT INTO bills (card_id, period, amount, due_date, paid, created_at, updated_at)"
        " VALUES (?,?,?,?,0,?,?)", (card_id, period, 1200.0, next_due.isoformat(), now, now))
    return card_id


app_db.init_db()
conn = sqlite3.connect(os.path.join(os.environ["DATA_DIR"], "fiscus.db"))
conn.row_factory = sqlite3.Row

long_name = "招商银行自由人生系列白金信用卡尊享典藏版"
add_card(conn, long_name, "招商银行", repay_day=max(1, (datetime.date.today() + datetime.timedelta(days=2)).day),
         combined=1, color="#ef5350")
add_card(conn, "招行青年卡", "招商银行", repay_day=max(1, (datetime.date.today() + datetime.timedelta(days=2)).day),
         combined=0, color="#26a69a")
add_card(conn, "农行商务卡", "农业银行", repay_day=max(1, (datetime.date.today() + datetime.timedelta(days=3)).day),
         combined=0, color="#5c9dff")

entries = notify_entries(conn, 5)
cids, images = {}, {}
html = build_html("Fiscus", entries, 5, cids, images)

repay_entries = [e for e in entries if e["kind"] == "repay"]
check("还款条目齐全", len(repay_entries) == 3, f"got={len(repay_entries)}")
check("过长卡名截断省略", "…" in html and long_name not in html)
check("无图卡用首字色块", "bgcolor" in html and ">招<" in html)
check("全部按银行分组", html.count('font-weight:600;color:#1A2029;') == 2
      and html.count("padding:6px 0;font-size:13px") == 3,
      f"组头={html.count('font-weight:600;color:#1A2029;')} 子行={html.count('padding:6px 0;font-size:13px')}")
check("三栏表头齐全", "信用卡" in html and "账单日" in html and "还款日" in html)
check("副标题文案", "张信用卡待还款" in html and "未来" in html)
check("还款日完整日期", iso(2) in html and iso(3) in html)
check("无图时无 CID 引用", "cid:" not in html)

# 自传图场景（伪造磁盘文件走 CID 注册）
media = os.path.join(os.environ["DATA_DIR"], "media", "cards")
os.makedirs(media, exist_ok=True)
from PIL import Image
Image.new("RGB", (120, 76), (79, 110, 247)).save(os.path.join(media, "card_1.png"))
Image.new("RGB", (48, 48), (19, 122, 95)).save(os.path.join(media, "banklogo_1.png"))
conn.execute("UPDATE cards SET card_image='card_1.png' WHERE name='农行商务卡'")
conn.execute("UPDATE cards SET bank_logo='banklogo_1.png' WHERE name LIKE '招商银行自由%'")
entries2 = notify_entries(conn, 5)
cids2, images2 = {}, {}
html2 = build_html("Fiscus", entries2, 5, cids2, images2)
check("卡面图走 CID 内嵌", 'src="cid:' in html2 and len(images2) >= 1)
check("银行 logo 走 CID 内嵌", len(images2) >= 2, f"附件数={len(images2)}")

fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)}/{len(results)} 通过")
if __name__ == "__main__":
    sys.exit(1 if fails else 0)
