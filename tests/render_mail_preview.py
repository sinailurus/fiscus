# -*- coding: utf-8 -*-
"""邮件正文小样渲染：与 test_mail.py 同款数据，headless 截图供确认。"""
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="fiscus_mailprev_")

from playwright.sync_api import sync_playwright

from app import db as app_db
from app.mailer import build_html
from app.reminders import notify_entries

app_db.init_db()
import sqlite3

conn = sqlite3.connect(os.path.join(os.environ["DATA_DIR"], "fiscus.db"))
conn.row_factory = sqlite3.Row


def add_card(name, bank, repay_day, combined=0, color="#4F6EF7", image="", logo=""):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO cards (name, bank, color, card_image, bank_logo, repay_day,"
        " report_combined, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (name, bank, color, image, logo, repay_day, combined, now, now))
    from app.schedule import next_monthly
    nd = next_monthly(repay_day, datetime.date.today())
    conn.execute(
        "INSERT INTO bills (card_id, period, amount, due_date, paid, created_at, updated_at)"
        " VALUES (?,?,?,?,0,?,?)", (cur.lastrowid, nd.isoformat()[:7], 1200.0, nd.isoformat(), now, now))


today = datetime.date.today()
add_card("招商银行自由人生系列白金信用卡尊享典藏版", "招商银行",
         max(1, (today + datetime.timedelta(days=2)).day), combined=1, color="#ef5350")
add_card("招行青年卡", "招商银行", max(1, (today + datetime.timedelta(days=2)).day),
         combined=1, color="#26a69a")
add_card("农行超然商务白金卡", "农业银行", max(1, (today + datetime.timedelta(days=3)).day),
         color="#5c9dff")

media = os.path.join(os.environ["DATA_DIR"], "media", "cards")
os.makedirs(media, exist_ok=True)
from PIL import Image, ImageDraw

img = Image.new("RGB", (640, 400), (231, 76, 60))
d = ImageDraw.Draw(img)
d.text((40, 40), "CARD FACE SAMPLE", fill=(255, 255, 255))
img.save(os.path.join(media, "card_1.png"))
logo = Image.new("RGB", (96, 96), (19, 122, 95))
ImageDraw.Draw(logo).text((30, 36), "Z", fill=(255, 255, 255))
logo.save(os.path.join(media, "banklogo_1.png"))

conn.execute("UPDATE cards SET card_image='card_1.png' WHERE name LIKE '农行%'")
conn.execute("UPDATE cards SET bank_logo='banklogo_1.png' WHERE name LIKE '招商银行自由%'")

entries = notify_entries(conn, 5)
cids, images = {}, {}
html = build_html("Fiscus", entries, 5, cids, images)

# 内嵌图改为 data URI 供浏览器预览
html_view = html
for cid, m in images.items():
    import base64
    payload = base64.b64encode(m.get_payload(decode=True)).decode()
    html_view = html_view.replace(f"cid:{cid}", f"data:image/png;base64,{payload}")

page_path = os.path.join(os.environ["DATA_DIR"], "preview.html")
with open(page_path, "w", encoding="utf-8") as f:
    f.write(f'<body style="margin:0;background:#e9edf3;">{html_view}</body>')

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 620, "height": 900})
    pg.goto("file://" + page_path)
    pg.wait_for_timeout(400)
    pg.screenshot(path="/home/z/my-project/fiscus/tests/mail_preview.png", full_page=True)
    b.close()
print("preview saved:", len(entries), "entries,", len(images), "embedded images")
