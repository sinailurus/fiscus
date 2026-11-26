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
    """银行组头标识：自传 logo 显示正方形图；未上传渲染同宽占位，保证组头名称对齐。"""
    url = entry.get("bank_logo_url") or ""
    if url:
        cid = _pic_cid(url, cids, images)
        if cid:
            return f'<img src="cid:{cid}" width="24" height="24" alt="" style="border-radius:5px;vertical-align:middle;">'
    return '<span style="display:inline-block;width:24px;"></span>'


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

def _bank_map(conn) -> dict:
    """设置页「银行显示名」映射（原名 → 简称），邮件组头用简称显示。"""
    import json as _json
    raw = get_setting(conn, "bank_names", "")
    if not raw:
        return {}
    try:
        parsed = _json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        return {}


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


def _row(entries: list[dict], cids: dict, images: dict, bank_map: dict | None = None) -> str:
    """按银行分组渲染（统一信报合一版式）：组头 logo + 子行（卡图 卡名 账单日 还款日）。"""
    bank_map = bank_map or {}
    html = []
    banks: dict[str, list[dict]] = {}
    for e in entries:
        banks.setdefault((e.get("bank") or "").strip() or "其他", []).append(e)

    head_tpl = (
        '<tr><td colspan="3" style="padding:10px 0 6px;font-size:13px;font-weight:600;color:#1A2029;">'
        '{badge}　{bank}</td></tr>'
    )
    card_tpl = (
        '<tr><td style="padding:6px 0 6px 36px;font-size:13px;color:#333;overflow:hidden;">'
        '{thumb} <span style="font-weight:600;white-space:nowrap;">{card}</span></td>'
        '<td align="center" style="font-size:13px;color:#556;">{bill_day}</td>'
        '<td align="right" style="font-size:13px;color:{color};font-weight:600;white-space:nowrap;">{date}</td></tr>'
    )
    rows = []
    for bank, items in banks.items():
        rows.append(head_tpl.format(bank=bank_map.get(bank, bank),
                                    badge=_bank_badge(bank, items[0], cids, images)))
        for e in items:
            bill_day = f"每月 {e['bill_day']} 号" if e.get("bill_day") else "—"
            rows.append(card_tpl.format(
                thumb=_card_thumb(e, cids, images), card=_short(e["card"], 14),
                bill_day=bill_day, date=e["date"], color=_color(e["days"])))
    return (
        '<table cellpadding="0" cellspacing="0" width="100%" '
        'style="table-layout:fixed;border-collapse:collapse;margin-top:4px;">'
        '<colgroup><col style="width:54%"><col style="width:20%"><col style="width:26%"></colgroup>'
        '<tr><td align="left" style="padding:0 0 6px 36px;font-size:12px;color:#889;">信用卡</td>'
        '<td align="center" style="padding:0 0 6px;font-size:12px;color:#889;">账单日</td>'
        '<td align="right" style="padding:0 0 6px;font-size:12px;color:#889;">还款日</td></tr>'
        + "".join(rows) + "</table>"
    )


def build_html(app_name: str, entries: list[dict], lead: int,
               cids: dict | None = None, images: dict | None = None,
               bank_map: dict | None = None) -> str:
    """汇总邮件（2026-11-26 双节点定稿）：仿 SubDeck 到期提醒版式。

    两段：本期账单已出（账单日当天）→ 还款日提醒（还款日前 N 天及当天）。
    段内三栏表格：信用卡（卡图+名称，占宽栏） | 账单日 | 还款日。
    所有卡片统一按银行分组（组头银行 logo，未上传则留空）。
    bank_map 为设置页「银行显示名」映射（原名 → 显示简称）。
    年费与权益不在表格内，落款小字提示条数。
    免责声明按信用卡风险等级强化（逾期影响征信）。
    """
    cids = cids if cids is not None else {}
    images = images if images is not None else {}
    statement = [e for e in entries if e["kind"] == "statement"]
    repay = [e for e in entries if e["kind"] == "repay"]
    extra = [e for e in entries if e["kind"] not in ("repay", "statement")]

    sections = ""
    if statement:
        sections += (
            '<p style="font-size:13px;color:#1A2029;font-weight:600;margin:0 0 2px;">'
            f'本期账单已出（{len(statement)} 张）</p>'
            + _row(statement, cids, images, bank_map)
        )
    if repay:
        if statement:
            sections += '<div style="height:20px;"></div>'
        sections += (
            '<p style="font-size:13px;color:#1A2029;font-weight:600;margin:0 0 2px;">'
            f'还款日临近（{len(repay)} 张）</p>'
            + _row(repay, cids, images, bank_map)
        )

    extra_note = ""
    if extra:
        names = "、".join(f"{e['card']}（{KIND_LABEL[e['kind']]}，{e['date'][5:]}）" for e in extra[:5])
        extra_note = (
            f'<p style="font-size:12px;color:#667;margin:12px 0 0;">'
            f'另有 {len(extra)} 项年费 / 权益提醒：{names}{"等" if len(extra) > 5 else ""}。</p>'
        )

    if not entries:
        sections = '<p style="font-size:13px;color:#667;">暂无待办。</p>'

    return (
        f'<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;'
        f'max-width:560px;margin:0 auto;padding:24px 16px;">'
        f'<h2 style="font-size:18px;color:#1A2029;margin:0 0 4px;">{app_name} · 还款提醒</h2>'
        f'<p style="font-size:13px;color:#667;margin:0 0 12px;">'
        f'未来 <span style="color:#1A2029;font-weight:600;">{lead} 天内</span>'
        f'共有 <span style="color:#1A2029;font-weight:600;">{len(repay)}</span> 张信用卡待还款：</p>'
        f'{sections}'
        f'{extra_note}'
        f'<p style="font-size:12px;color:#99A;margin-top:24px;">'
        f'本邮件仅为参考提醒，不构成任何还款依据。账单金额、最后还款日、宽限期与最低还款额'
        f'一律以发卡行账单及官方 App 为准；信用卡逾期将产生利息与违约金，并可能影响个人征信，'
        f'请务必在银行官方渠道核实后按时足额还款。</p>'
        f'<p style="font-size:12px;color:#99A;margin-top:8px;">'
        f'本邮件由 {app_name} 自动发送。</p></div>'
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
                repay_n = len([e for e in entries if e["kind"] == "repay"])
                stmt_n = len([e for e in entries if e["kind"] == "statement"])
                if repay_n:
                    subject = f"{app_name} · 未来 {lead} 天有 {repay_n} 张信用卡待还款"
                else:
                    subject = f"{app_name} · 本期账单已出（{stmt_n} 张）"
                cids: dict = {}
                images: dict = {}
                html = build_html(app_name, entries, lead, cids, images,
                                  bank_map=_bank_map(conn))
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
    html = build_html(app_name, entries, lead, cids, images, bank_map=_bank_map(conn)) if entries else (
        f'<div style="font-family:sans-serif;padding:16px;font-size:14px;">'
        f'{app_name} 邮箱提醒配置成功。当前没有待提醒事项。</div>'
    )
    try:
        send_mail(cfg, subject, html, images)
        return True, "测试邮件已发送，请查收"
    except Exception as e:
        return False, f"发送失败：{e}"
