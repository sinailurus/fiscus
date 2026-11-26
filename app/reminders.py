# -*- coding: utf-8 -*-
"""提醒快照：卡片、账单、年费、权益的当前状态一次算清。

页内概览条、卡面徽章、日历视图、邮件提醒共用这一份计算，
保证任何入口看到的倒计时完全一致。
"""
import datetime
import sqlite3

from .db import get_setting
from .schedule import add_years, next_monthly, parse, roll_next, today

URGENT_DAYS_DEFAULT = 3      # 橙色临期阈值（天）
FEE_LEAD_DEFAULT = 30        # 年费提前提醒（天）
BENEFIT_LEAD_DEFAULT = 14    # 权益清零提前提醒（天）

CARD_FIELDS = (
    "id", "name", "bank", "color", "card_image", "bill_day",
    "repay_day", "lead_days", "limit_amount", "notes", "sort_order",
)


def _urgent_days(conn: sqlite3.Connection) -> int:
    try:
        return int(get_setting(conn, "notify_urgent_days", str(URGENT_DAYS_DEFAULT)) or URGENT_DAYS_DEFAULT)
    except ValueError:
        return URGENT_DAYS_DEFAULT


def card_state(conn: sqlite3.Connection, row: sqlite3.Row, base: datetime.date | None = None) -> dict:
    """单张卡的展示状态（下次还款、金额、年费、权益）。"""
    base = base or today()
    card = {k: row[k] for k in CARD_FIELDS}

    # ---- 还款：周期给日期，账单表给金额与已还状态 ----
    next_due = next_monthly(row["repay_day"], base)
    period = next_due.isoformat()[:7]                       # 该还款日所属账单期 YYYY-MM
    bill = conn.execute(
        "SELECT * FROM bills WHERE card_id=? AND period=?", (row["id"], period)
    ).fetchone()
    due_date = parse(bill["due_date"]) if bill and bill["due_date"] else next_due
    days = (due_date - base).days
    card["next_due"] = due_date.isoformat()
    card["next_due_days"] = days
    card["next_period"] = period
    card["bill_amount"] = bill["amount"] if bill else None   # None=未录入金额
    card["bill_paid"] = bool(bill["paid"]) if bill else False
    card["bill_id"] = bill["id"] if bill else None
    card["image_url"] = f"/api/cards/image/{row['card_image']}" if row["card_image"] else ""

    # ---- 年费 ----
    fee = conn.execute("SELECT * FROM fees WHERE card_id=?", (row["id"],)).fetchone()
    fee_state = None
    if fee and (fee["amount"] > 0 or fee["target_count"] > 0) and fee["next_date"]:
        nd = parse(roll_next(fee["next_date"], "yearly"))    # 年费日按年滚动（写库动作由保存接口负责）
        fee_days = (nd - base).days
        need = fee["target_count"] - fee["done_count"]
        fee_state = {
            "amount": fee["amount"],
            "next_date": nd.isoformat(),
            "days": fee_days,
            "rule_note": fee["rule_note"],
            "target_count": fee["target_count"],
            "done_count": fee["done_count"],
            "remaining": max(0, need),
            "waived_possible": fee["target_count"] > 0,
            "alert": fee_days <= FEE_LEAD_DEFAULT and (need > 0 or fee["target_count"] == 0),
        }
    card["fee"] = fee_state

    # ---- 权益 ----
    benefits = []
    for b in conn.execute(
        "SELECT * FROM benefits WHERE card_id=? ORDER BY id", (row["id"],)
    ).fetchall():
        remaining = max(0, b["total"] - b["used"])
        exp = b["expire_date"] if b["expire_type"] == "date" else roll_next(b["next_reset"], b["cycle"])
        exp_d = parse(exp)
        exp_days = (exp_d - base).days if exp_d else None
        benefits.append({
            "id": b["id"], "name": b["name"], "total": b["total"], "used": b["used"],
            "remaining": remaining,
            "expire_type": b["expire_type"], "expire_date": exp,
            "days": exp_days,
            "alert": remaining > 0 and exp_days is not None and exp_days <= BENEFIT_LEAD_DEFAULT,
        })
    card["benefits"] = benefits
    card["benefit_alert"] = any(b["alert"] for b in benefits)
    return card


def snapshot(conn: sqlite3.Connection) -> dict:
    """全局快照：卡列表状态 + 概览汇总 + 未来事件流。"""
    base = today()
    urgent = _urgent_days(conn)
    cards = []
    for row in conn.execute("SELECT * FROM cards ORDER BY sort_order, id"):
        cards.append(card_state(conn, row, base))

    # 概览：未还卡金额合计 + 最近一个临期事件
    total_due = 0.0
    has_unpaid = False
    nearest = None                      # (days, 文案, card_id)
    events = []                         # 未来 60 天事件流（日历/时间线共用）
    for c in cards:
        if not c["bill_paid"]:
            has_unpaid = True
            if c["bill_amount"] is not None:
                total_due += c["bill_amount"]
        label = f"{c['name']} · {c['next_due'][5:]} 到期"
        if c["bill_paid"]:
            label = f"{c['name']} · 本期已还"
        cand = (c["next_due_days"], label, c["id"])
        if not c["bill_paid"] and (nearest is None or cand[0] < nearest[0]):
            nearest = cand
        events.append({
            "date": c["next_due"], "days": c["next_due_days"], "kind": "repay",
            "card_id": c["id"], "card_name": c["name"], "title": "还款日",
            "amount": c["bill_amount"], "paid": c["bill_paid"],
        })
        f = c["fee"]
        if f and f["alert"]:
            events.append({
                "date": f["next_date"], "days": f["days"], "kind": "fee",
                "card_id": c["id"], "card_name": c["name"], "title": "年费",
                "remaining": f["remaining"], "amount": f["amount"],
            })
        for b in c["benefits"]:
            if b["alert"]:
                events.append({
                    "date": b["expire_date"], "days": b["days"], "kind": "benefit",
                    "card_id": c["id"], "card_name": c["name"], "title": f"{b['name']}清零",
                    "remaining": b["remaining"],
                })
    events.sort(key=lambda e: (e["date"], e["kind"]))

    return {
        "today": base.isoformat(),
        "urgent_days": urgent,
        "cards": cards,
        "summary": {
            "total_due": round(total_due, 2),
            "has_unpaid": has_unpaid,
            "nearest": {"days": nearest[0], "text": nearest[1], "card_id": nearest[2]} if nearest else None,
        },
        "events": events,
    }


def notify_entries(conn: sqlite3.Connection, lead_days: int) -> list[dict]:
    """邮件扫描：未来 lead_days 天内需要提醒的条目（已还的不提醒）。"""
    base = today()
    out = []
    snap = snapshot(conn)
    for c in snap["cards"]:
        if not c["bill_paid"] and c["next_due_days"] <= lead_days:
            amount = "未录入金额" if c["bill_amount"] is None else f"{c['bill_amount']:g} 元"
            out.append({
                "kind": "repay", "card": c["name"], "title": "还款提醒",
                "date": c["next_due"], "days": c["next_due_days"],
                "detail": f"应还 {amount}；宽限以银行 App 显示为准",
            })
        f = c["fee"]
        if f and f["alert"] and f["days"] <= lead_days:
            extra = f"，还差 {f['remaining']} 笔免年费" if f["waived_possible"] and f["remaining"] > 0 else ""
            out.append({
                "kind": "fee", "card": c["name"], "title": "年费提醒",
                "date": f["next_date"], "days": f["days"],
                "detail": f"年费 {f['amount']:g} 元{extra or '，即将收取'}",
            })
        for b in c["benefits"]:
            if b["alert"] and b["days"] <= lead_days:
                out.append({
                    "kind": "benefit", "card": c["name"], "title": f"{b['name']}即将清零",
                    "date": b["expire_date"], "days": b["days"],
                    "detail": f"剩 {b['remaining']} 次，{b['expire_date'][5:]} 失效",
                })
    return out
