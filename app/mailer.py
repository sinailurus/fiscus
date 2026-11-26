# -*- coding: utf-8 -*-
"""邮箱提醒（v1.1.0）：SMTP 发信 + 每日三类扫描调度。

邮件正文（2026-11-26 草图定稿）：
- 每条待办带卡面缩略图（未上传卡面图时用卡色 + 卡名首字色块兜底）；
- 过长卡名后端截断省略；
- 「信报合一」的银行：同银行多卡在还款段合并为一组，组头为银行 logo
  （未上传时用银行名首字色块，规避官方素材版权风险），子项为各卡与日期；
- 卡面图 / 银行 logo 以 CID 内嵌附件发送，收件无需登录鉴权。

零依赖：全部使用 Python 标准库（smtplib / email / threading）。
邮件 Subject / 发件人显示名 / 正文落款均跟随设置中的应用名称。
"""
import os
import smtplib
import ssl
import threading
import time
import traceback
from email.header import Header
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate

from .db import MEDIA_DIR, get_setting, set_setting
from .reminders import notify_entries

SMTP_TIMEOUT = 15

KIND_LABEL = {"repay": "还款", "fee": "年费", "benefit": "权益清零"}

PALETTE = ["#ef5350", "#ab63f6", "#5c9dff", "#26a69a", "#66bb6a",
           "#ffa726", "#ff7043", "#ec407a", "#8d6e63", "#78909c"]

# 卡面图 / 银行 logo 的磁盘目录（文件名由 main.py 上传接口写入 DB）
MEDIA_CARDS_DIR = os.path.join(MEDIA_DIR, "cards")


def _block_initial(text: str, color: str, size: int) -> str:
    """首字色块（邮件客户端安全的 table 实现）。"""
    return (
        f'<table cellpadding="0" cellspacing="0" style="display:inline-block;vertical-align:middle;">'
        f'<tr><td bgcolor="{color}" width="{size}" height="{size}" align="center" '
        f'style="width:{size}px;height:{size}px;border-radius:6px;color:#ffffff;'
        f'font-size:{size // 2}px;font-weight:600;text-align:center;">{text}</td></tr></table>'
    )


def _card_thumb(entry: dict, cids: dict, images: dict) -> str:
    """卡面缩略：自传图优先，否则卡色首字。"""
    url = entry.get("image_url") or ""
    if url:
        cid = _pic_cid(url, cids, images)
        if cid:
            return f'<img src="cid:{cid}" width="44" height="28" alt="" style="border-radius:5px;vertical-align:middle;">'
    return _block_initial((entry["card"] or "?").strip()[:1].upper(), entry.get("color") or "#4F6EF7", 28)


def _bank_badge(bank: str, entry: dict, cids: dict, images: dict) -> str:
    """银行组头标识：自传 logo 优先，否则首字色块（按银行名取色）。"""
    url = entry.get("bank_logo_url") or ""
    if url:
        cid = _pic_cid(url, cids, images)
        if cid:
            return f'<img src="cid:{cid}" width="24" height="24" alt="" style="border-radius:5px;vertical-align:middle;">'
    color = PALETTE[sum(map(ord, bank or "?")) % len(PALETTE)]
    return _block_initial((bank or "?").strip()[:1], color, 24)


def _pic_cid(url: str, cids: dict, images: dict) -> str:
    """把 API 图片路径注册为 CID 内嵌附件；同一文件复用同一 CID。"""
    if url in cids:
        return cids[url]
    filename = url.rsplit("/", 1)[-1]
    path = os.path.join(MEDIA_CARDS_DIR, filename)
    if not os.path.isfile(path):
        return ""
    with open(path, "rb") as f:
        data = f.read()
    cid = f"pic{len(images) + 1}@fiscus"
    ext = filename.rsplit(".", 1)[-1]
    img = MIMEImage(data, _subtype={"png": "png", "jpg": "jpeg", "webp": "webp"}.get(ext, "png"))
    img.add_header("Content-ID", f"<{cid}>")
    img.add_header("Content-Disposition", "inline", filename=filename)
    images[cid] = img
    cids[url] = cid
    return cid


# ---------------------------------------------------------------- SMTP 配置

def _smtp_cfg(conn, app_name: str):
    port = int(get_setting(conn, "smtp_port", "465") or 465)
    use_ssl = get_setting(conn, "smtp_ssl", "1") == "1"
    return {
        "host": get_setting(conn, "smtp_host", ""),
        "port": port,
        "ssl": use_ssl,
        "user": get_setting(conn, "smtp_user", ""),
        "password": get_setting(conn, "smtp_pass", ""),
        "sender": get_setting(conn, "smtp_user", ""),
        "display_name": app_name,
    }


def send_mail(cfg: dict, subject: str, html: str, images: dict | None = None) -> None:
    """发送一封 HTML 邮件；images 为 {cid: MIMEImage} 内嵌附件（可选）。"""
    msg = MIMEMultipart("related")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header(cfg["display_name"], "utf-8")), cfg["sender"]))
    msg["To"] = cfg.get("to", "")
    msg["Date"] = formatdate(localtime=True)
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(alt)
    for img in (images or {}).values():
        msg.attach(img)

    if cfg["ssl"]:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=SMTP_TIMEOUT, context=ctx) as s:
            s.login(cfg["user"], cfg["password"])
            s.sendmail(cfg["user"], [x.strip() for x in cfg["to"].split(",") if x.strip()], msg.as_string())
    else:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=SMTP_TIMEOUT) as s:
            s.ehlo()
            s.starttls(context=ssl.create_default_context())
            s.login(cfg["user"], cfg["password"])
            s.sendmail(cfg["user"], [x.strip() for x in cfg["to"].split(",") if x.strip()], msg.as_string())


# ---------------------------------------------------------------- 邮件构建

def _short(text: str, limit: int = 18) -> str:
    """过长卡名截断省略。"""
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _when(days: int) -> str:
    if days < 0:
        return f"已过期 {abs(days)} 天"
    if days == 0:
        return "今天"
    return f"{days} 天后"


def _color(days: int) -> str:
    return "#D84315" if days <= 3 else "#1A2029"


def _row(entries: list[dict], cids: dict, images: dict) -> str:
    """一组同类条目：普通行（带卡图），信报合一的银行归组渲染。"""
    html = []
    # 合一组：同银行名下任一卡勾选信报合一 → 该银行所有条目归组
    banks = {}
    singles = []
    for e in entries:
        b = (e.get("bank") or "").strip()
        if b and e.get("combined"):
            banks.setdefault(b, []).append(e)
        elif b and any(x.get("combined") for x in entries if (x.get("bank") or "").strip() == b):
            banks.setdefault(b, []).append(e)
        else:
            singles.append(e)

    group_tpl = (
        '<div style="padding:8px 0;border-top:1px solid #E8EBF1;">'
        '<div style="font-size:13px;font-weight:600;color:#1A2029;">{badge} {bank}</div>{sub}</div>'
    )
    sub_tpl = (
        '<div style="display:flex;justify-content:space-between;gap:12px;'
        'padding:4px 0 0 32px;font-size:12px;color:#556;">'
        '<span>{card}　{detail}</span>'
        '<span style="white-space:nowrap;color:{color};font-weight:600;">{date} · {when}</span></div>'
    )
    item_tpl = (
        '<div style="display:flex;justify-content:space-between;gap:12px;align-items:center;'
        'padding:8px 0;border-top:1px solid #E8EBF1;font-size:13px;color:#333;">'
        '<span>{thumb} <span style="font-weight:600;">{card}</span>　'
        '<span style="color:#889;">{detail}</span></span>'
        '<span style="white-space:nowrap;color:{color};font-weight:600;">{date} · {when}</span></div>'
    )
    for bank, items in banks.items():
        subs = "".join(
            sub_tpl.format(card=_short(e["card"]), detail=e["detail"], when=_when(e["days"]),
                           date=e["date"][5:], color=_color(e["days"]))
            for e in items)
        html.append(group_tpl.format(bank=bank, badge=_bank_badge(bank, items[0], cids, images), sub=subs))
    for e in singles:
        html.append(item_tpl.format(thumb=_card_thumb(e, cids, images), card=_short(e["card"]),
                                    detail=e["detail"], date=e["date"][5:],
                                    when=_when(e["days"]), color=_color(e["days"])))
    return "".join(html)


def build_html(app_name: str, entries: list[dict], lead: int,
               cids: dict | None = None, images: dict | None = None) -> str:
    """汇总邮件：按 还款 / 年费 / 权益清零 三段分组，条目带卡图与日期。

    cids / images 由调用方传入两个空 dict；发送时把 images 作为内嵌附件挂到
    multipart/related，正文里的 cid 引用即可显示。
    """
    cids = cids if cids is not None else {}
    images = images if images is not None else {}
    rows = ""
    groups = {}
    for e in entries:
        groups.setdefault(e["kind"], []).append(e)
    section_tpl = (
        '<div style="margin:0 0 16px;padding:12px 16px;background:#F5F7FB;border-radius:10px;">'
        '<div style="font-size:15px;font-weight:600;color:#1A2029;margin-bottom:8px;">{title}</div>{items}</div>'
    )
    for kind in ("repay", "fee", "benefit"):
        items = groups.get(kind)
        if not items:
            continue
        rows += section_tpl.format(title=f"{KIND_LABEL[kind]}（{len(items)} 项）",
                                   items=_row(items, cids, images))

    repay_n = len(groups.get("repay", []))
    summary = f"未来 {lead} 天有 {len(entries)} 项待办" + (f"，其中 {repay_n} 笔还款" if repay_n else "")
    return (
        f'<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;'
        f'max-width:560px;margin:0 auto;padding:24px 16px;">'
        f'<h2 style="font-size:18px;color:#1A2029;margin:0 0 4px;">{app_name}</h2>'
        f'<p style="font-size:13px;color:#667;margin:0 0 16px;">{summary}</p>'
        f'{rows or "<p style=\'font-size:13px;color:#667;\'>暂无待办。</p>"}'
        f'<p style="font-size:12px;color:#99A;margin-top:24px;">'
        f'日期与金额以发卡行 App 显示为准，本邮件由 {app_name} 自动发送。</p></div>'
    )


# ---------------------------------------------------------------- 每日调度

def _notify_loop() -> None:
    """后台线程：每小时整点检查一次；到达发送时刻当天发一封，次日重置。"""
    while True:
        time.sleep(60)
        try:
            from .db import db
            with db() as conn:
                if get_setting(conn, "notify_enabled", "0") != "1":
                    continue
                hour = int(get_setting(conn, "notify_hour", "8") or 8)
                lead = int(get_setting(conn, "notify_lead_days", "3") or 3)
                now = time.localtime()
                if now.tm_hour != hour:
                    continue
                today_str = time.strftime("%Y-%m-%d")
                if get_setting(conn, "last_notify_date", "") == today_str:
                    continue
                emails = get_setting(conn, "notify_emails", "")
                if not emails:
                    continue
                entries = notify_entries(conn, lead)
                # 当天没有任何待办也记日期，避免空跑
                set_setting(conn, "last_notify_date", today_str)
                if not entries:
                    continue
                app_name = get_setting(conn, "app_name", "Fiscus") or "Fiscus"
                cfg = _smtp_cfg(conn, app_name)
                cfg["to"] = emails
                subject = f"{app_name} · 未来 {lead} 天有 {len(entries)} 项待办"
                cids: dict = {}
                images: dict = {}
                html = build_html(app_name, entries, lead, cids, images)
                send_mail(cfg, subject, html, images)
        except Exception:
            traceback.print_exc()   # 后台任务：打印日志继续轮询


def start_scheduler() -> None:
    t = threading.Thread(target=_notify_loop, daemon=True)
    t.start()


def send_test(conn, app_name: str) -> tuple[bool, str]:
    """设置页「发送测试邮件」。返回 (成功?, 消息)。"""
    emails = get_setting(conn, "notify_emails", "")
    if not emails:
        return False, "请先填写收件邮箱"
    cfg = _smtp_cfg(conn, app_name)
    cfg["to"] = emails
    entries = notify_entries(conn, int(get_setting(conn, "notify_lead_days", "3") or 3))
    lead = int(get_setting(conn, "notify_lead_days", "3") or 3)
    subject = f"{app_name} · 测试邮件"
    cids: dict = {}
    images: dict = {}
    html = build_html(app_name, entries, lead, cids, images) if entries else (
        f'<div style="font-family:sans-serif;padding:16px;font-size:14px;">'
        f'{app_name} 邮箱提醒配置成功。当前没有待提醒事项。</div>'
    )
    try:
        send_mail(cfg, subject, html, images)
        return True, "测试邮件已发送，请查收"
    except Exception as e:
        return False, f"发送失败：{e}"
