# -*- coding: utf-8 -*-
"""邮箱提醒（v1.0.0）：SMTP 发信 + 每日三类扫描调度（照搬 SubDeck mailer.py 骨架）。

与 SubDeck 的差异：
- 扫描源从「订阅到期」换成 Fiscus 的三类事件（还款 / 年费 / 权益清零）；
- 「标记已还」的卡当期不再进入扫描（已还不催）；
- 邮件正文按三类分段，金额与行动建议（还差几笔免年费）直接给结论。

零依赖：全部使用 Python 标准库（smtplib / email / threading）。
邮件 Subject / 发件人显示名 / 正文落款均跟随设置中的应用名称。
"""
import json
import smtplib
import ssl
import threading
import time
import traceback
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate

from .db import get_setting, set_setting
from .reminders import notify_entries

SMTP_TIMEOUT = 15

KIND_LABEL = {"repay": "还款", "fee": "年费", "benefit": "权益清零"}


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


def send_mail(cfg: dict, subject: str, html: str) -> None:
    """发送一封 HTML 邮件。任何失败都抛异常，由调用方决定重试策略。"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header(cfg["display_name"], "utf-8")), cfg["sender"]))
    msg["To"] = cfg.get("to", "")
    msg["Date"] = formatdate(localtime=True)
    msg.attach(MIMEText(html, "html", "utf-8"))

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

def build_html(app_name: str, entries: list[dict], lead: int) -> str:
    """汇总邮件：按 还款 / 年费 / 权益清零 三段分组。"""
    rows = ""
    groups = {}
    for e in entries:
        groups.setdefault(e["kind"], []).append(e)
    section_tpl = (
        '<div style="margin:0 0 16px;padding:12px 16px;background:#F5F7FB;border-radius:10px;">'
        '<div style="font-size:15px;font-weight:600;color:#1A2029;margin-bottom:8px;">{title}</div>{items}</div>'
    )
    item_tpl = (
        '<div style="display:flex;justify-content:space-between;gap:12px;'
        'padding:8px 0;border-top:1px solid #E8EBF1;font-size:13px;color:#333;">'
        '<span>{card} · {detail}</span>'
        '<span style="white-space:nowrap;color:{color};font-weight:600;">{when}</span></div>'
    )

    def _when(days: int) -> str:
        if days < 0:
            return f"已过期 {abs(days)} 天"
        if days == 0:
            return "今天"
        return f"{days} 天后"

    def _color(days: int) -> str:
        return "#D84315" if days <= 3 else "#1A2029"

    for kind in ("repay", "fee", "benefit"):
        items = groups.get(kind)
        if not items:
            continue
        html_items = "".join(
            item_tpl.format(card=e["card"], detail=e["detail"], when=_when(e["days"]), color=_color(e["days"]))
            for e in items
        )
        label = KIND_LABEL[kind]
        rows += section_tpl.format(title=f"{label}（{len(items)} 项）", items=html_items)

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
                send_mail(cfg, subject, build_html(app_name, entries, lead))
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
    html = build_html(app_name, entries, lead) if entries else (
        f'<div style="font-family:sans-serif;padding:16px;font-size:14px;">'
        f'{app_name} 邮箱提醒配置成功。当前没有待提醒事项。</div>'
    )
    try:
        send_mail(cfg, subject, html)
        return True, "测试邮件已发送，请查收"
    except Exception as e:
        return False, f"发送失败：{e}"
