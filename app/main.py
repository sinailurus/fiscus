# -*- coding: utf-8 -*-
"""Fiscus 自部署信用卡管理（FastAPI 后端入口）。

产品定位：记录和提醒还款是核心；卡面墙、年费、权益围绕其展开。
零预置规则、零推算：所有数据均为用户手动录入，本后端只做
通用日历滚动（每月 X 号 / 每年 X 月 X 日），不做任何银行业务推算。
"""
import calendar
import datetime
import json
import os
import re
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth, mailer, reminders
from .db import MEDIA_DIR, db, get_setting, init_db, set_setting

APP_VERSION = "1.2.1"
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

CARD_IMAGE_RE = re.compile(r"^card_\d+\.(png|jpg|webp)$")
BRAND_RE = re.compile(r"^(bg|icon|loginicon|loginbg)_\d+\.(png|jpg|webp)$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
PALETTE = ["#ef5350", "#ab63f6", "#5c9dff", "#26a69a", "#66bb6a",
           "#ffa726", "#ff7043", "#ec407a", "#8d6e63", "#78909c"]
IMAGE_MAX_BYTES = 4 * 1024 * 1024        # 卡面图 4MB
ALLOWED_BG_PRESETS = {"aurora", "candy", "sunset"}
ALLOWED_SKINS = {"solid", "glass", "glassplus"}
ALLOWED_CYCLES = {"daily", "weekly", "monthly", "quarterly", "yearly"}

app = FastAPI(title="Fiscus", version=APP_VERSION, docs_url=None, redoc_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """基础安全响应头：防 MIME 嗅探 / 点击劫持 / 引用泄露；CSP 收紧到同源。"""
    resp = await call_next(request)
    h = resp.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
        "form-action 'self'",
    )
    return resp


@app.on_event("startup")
def _startup() -> None:
    init_db()
    mailer.start_scheduler()


# ---------------------------------------------------------------- 鉴权工具

def _logged_in(request: Request) -> bool:
    return auth.auth_enabled() and auth.verify_token(request.cookies.get(auth.COOKIE_NAME))


def require_auth(request: Request) -> None:
    if auth.auth_enabled() and not auth.verify_token(request.cookies.get(auth.COOKIE_NAME)):
        raise HTTPException(status_code=401, detail="unauthorized")


def _session_cookie(response: Response) -> None:
    response.set_cookie(
        auth.COOKIE_NAME,
        auth.make_token(),
        max_age=auth.SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
    )


# ---------------------------------------------------------------- 登录限速（防暴力破解）

_LOGIN_FAILS: dict[str, tuple[int, float]] = {}
LOGIN_MAX_FAILS = 5
LOGIN_LOCK_SECONDS = 900


def _client_ip(request: Request) -> str:
    """真实客户端 IP：CF 隧道场景取 CF-Connecting-IP；直连取 socket 对端。"""
    return request.headers.get("cf-connecting-ip") or (
        request.client.host if request.client else "unknown")


@app.post("/api/login")
def login(request: Request, body: dict):
    if not auth.auth_enabled():
        return {"ok": True, "msg": "未启用密码保护"}
    ip = _client_ip(request)
    now = time.time()
    fails, lock_until = _LOGIN_FAILS.get(ip, (0, 0.0))
    if now < lock_until:
        remain = int((lock_until - now) // 60) + 1
        raise HTTPException(status_code=429, detail=f"密码错误次数过多，请约 {remain} 分钟后再试")
    if not isinstance(body.get("password"), str) or not auth.check_password(body["password"]):
        fails += 1
        if fails >= LOGIN_MAX_FAILS:
            _LOGIN_FAILS[ip] = (0, now + LOGIN_LOCK_SECONDS)
            raise HTTPException(status_code=429, detail="密码错误次数过多，已锁定 15 分钟")
        _LOGIN_FAILS[ip] = (fails, 0.0)
        raise HTTPException(status_code=401, detail="密码错误")
    _LOGIN_FAILS.pop(ip, None)
    resp = JSONResponse({"ok": True})
    _session_cookie(resp)
    return resp


@app.post("/api/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE_NAME)
    return resp


# ---------------------------------------------------------------- 基础接口

@app.get("/api/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/api/me")
def me(request: Request):
    return {
        "version": APP_VERSION,
        "auth_required": auth.auth_enabled(),
        "logged_in": _logged_in(request) or not auth.auth_enabled(),
    }


# ---------------------------------------------------------------- 设置

def _settings_payload(conn) -> dict:
    return {
        "app_name": get_setting(conn, "app_name", "Fiscus") or "Fiscus",
        "theme_color": get_setting(conn, "theme_color", ""),
        "bg_image": get_setting(conn, "bg_image", ""),
        "bg_mask": int(get_setting(conn, "bg_mask", "35") or 35),
        "skin": get_setting(conn, "skin", "glass") or "glass",
        "brand_icon": get_setting(conn, "brand_icon", ""),
        "login_title": get_setting(conn, "login_title", ""),
        "login_welcome": get_setting(conn, "login_welcome", ""),
        "login_bg": get_setting(conn, "login_bg", ""),
        "login_bg_mask": int(get_setting(conn, "login_bg_mask", "45") or 45),
        "login_icon": get_setting(conn, "login_icon", ""),
        "urgent_days": int(get_setting(conn, "notify_urgent_days", "3") or 3),
        "show_todo_badge": get_setting(conn, "show_todo_badge", "1") == "1",
        "notify_enabled": get_setting(conn, "notify_enabled", "0") == "1",
        "notify_emails": get_setting(conn, "notify_emails", ""),
        "bank_names": get_setting(conn, "bank_names", ""),
        "notify_lead_days": int(get_setting(conn, "notify_lead_days", "3") or 3),
        "notify_hour": int(get_setting(conn, "notify_hour", "8") or 8),
        "smtp_host": get_setting(conn, "smtp_host", ""),
        "smtp_port": int(get_setting(conn, "smtp_port", "465") or 465),
        "smtp_ssl": get_setting(conn, "smtp_ssl", "1") == "1",
        "smtp_user": get_setting(conn, "smtp_user", ""),
        "smtp_pass": get_setting(conn, "smtp_pass", ""),
    }


@app.get("/api/settings")
def get_settings(request: Request):
    require_auth(request)
    with db() as conn:
        return _settings_payload(conn)


@app.put("/api/settings")
@app.post("/api/settings")
def put_settings(request: Request, body: dict):
    require_auth(request)
    with db() as conn:
        if "app_name" in body:
            name = str(body["app_name"] or "").strip()
            if not name or len(name) > 12:
                raise HTTPException(status_code=400, detail="应用名称需为 1-12 个字")
            set_setting(conn, "app_name", name)
        if "theme_color" in body:
            color = str(body["theme_color"] or "").strip()
            if color and not COLOR_RE.match(color):
                raise HTTPException(status_code=400, detail="主题色格式应为 #RRGGBB")
            set_setting(conn, "theme_color", color)
        if "bg_image" in body:
            v = str(body["bg_image"] or "")
            if v and not (v.startswith("preset:") and v.split(":", 1)[1] in ALLOWED_BG_PRESETS) \
                    and not BRAND_RE.match(v):
                raise HTTPException(status_code=400, detail="非法的背景图值")
            set_setting(conn, "bg_image", v)
        if "bg_mask" in body:
            mask = int(body["bg_mask"])
            if not 0 <= mask <= 85:
                raise HTTPException(status_code=400, detail="遮罩浓度需在 0-85 之间")
            set_setting(conn, "bg_mask", str(mask))
        if "skin" in body:
            if body["skin"] not in ALLOWED_SKINS:
                raise HTTPException(status_code=400, detail="非法的界面风格")
            set_setting(conn, "skin", body["skin"])
        if "show_todo_badge" in body:
            set_setting(conn, "show_todo_badge", "1" if body["show_todo_badge"] else "0")
        if "login_title" in body:
            v = str(body["login_title"] or "").strip()
            if len(v) > 24:
                raise HTTPException(status_code=400, detail="登录页标题不能超过 24 个字")
            set_setting(conn, "login_title", v)
        if "login_welcome" in body:
            v = str(body["login_welcome"] or "").strip()
            if len(v) > 40:
                raise HTTPException(status_code=400, detail="欢迎语不能超过 40 个字")
            set_setting(conn, "login_welcome", v)
        if "login_bg" in body:
            v = str(body["login_bg"] or "")
            is_preset = v.startswith("preset:") and v.split(":", 1)[1] in ALLOWED_BG_PRESETS
            if v not in {"", "none"} and not is_preset and not BRAND_RE.match(v):
                raise HTTPException(status_code=400, detail="非法的登录页背景值")
            set_setting(conn, "login_bg", v)
        if "login_bg_mask" in body:
            mask = int(body["login_bg_mask"])
            if not 0 <= mask <= 80:
                raise HTTPException(status_code=400, detail="遮罩浓度需在 0-80 之间")
            set_setting(conn, "login_bg_mask", str(mask))
        if "urgent_days" in body:
            n = int(body["urgent_days"])
            if not 1 <= n <= 15:
                raise HTTPException(status_code=400, detail="临期阈值需在 1-15 天之间")
            set_setting(conn, "notify_urgent_days", str(n))
        if "notify_enabled" in body:
            set_setting(conn, "notify_enabled", "1" if body["notify_enabled"] else "0")
        if "notify_emails" in body:
            emails = ",".join(x.strip() for x in
                              str(body["notify_emails"]).replace("；", ",").replace("，", ",")
                              .replace(";", ",").replace(" ", ",").split(",")
                              if x.strip())
            if len(emails) > 400 or (emails and any(("@" not in e or len(e) > 100) for e in emails.split(","))):
                raise HTTPException(status_code=400, detail="收件邮箱格式有误")
            set_setting(conn, "notify_emails", emails)
        if "bank_names" in body:
            raw = body.get("bank_names")
            mapping = {}
            if isinstance(raw, dict):
                items = raw.items()
            elif isinstance(raw, str) and raw.strip():
                try:
                    parsed = json.loads(raw)
                except ValueError:
                    raise HTTPException(status_code=400, detail="银行显示名格式有误")
                items = parsed.items() if isinstance(parsed, dict) else []
            else:
                items = []
            for original, display in items:
                original, display = str(original).strip()[:30], str(display).strip()[:30]
                if original:
                    mapping[original] = display
            if len(mapping) > 50:
                raise HTTPException(status_code=400, detail="银行显示名最多 50 条")
            set_setting(conn, "bank_names", json.dumps(mapping, ensure_ascii=False) if mapping else "")
        if "notify_lead_days" in body:
            n = int(body["notify_lead_days"])
            if not 1 <= n <= 30:
                raise HTTPException(status_code=400, detail="提前天数需在 1-30 之间")
            set_setting(conn, "notify_lead_days", str(n))
        if "notify_hour" in body:
            n = int(body["notify_hour"])
            if not 0 <= n <= 23:
                raise HTTPException(status_code=400, detail="发送时间需在 0-23 点之间")
            set_setting(conn, "notify_hour", str(n))
        if "smtp_host" in body:
            set_setting(conn, "smtp_host", str(body["smtp_host"]).strip()[:80])
        if "smtp_port" in body:
            n = int(body["smtp_port"])
            if not 1 <= n <= 65535:
                raise HTTPException(status_code=400, detail="端口不合法")
            set_setting(conn, "smtp_port", str(n))
        if "smtp_ssl" in body:
            set_setting(conn, "smtp_ssl", "1" if body["smtp_ssl"] else "0")
        if "smtp_user" in body:
            set_setting(conn, "smtp_user", str(body["smtp_user"]).strip()[:100])
        if "smtp_pass" in body:
            set_setting(conn, "smtp_pass", str(body["smtp_pass"])[:100])
        return _settings_payload(conn)


@app.post("/api/notify/test")
def notify_test(request: Request, body: dict):
    """用请求体携带的 SMTP 配置立即发送测试邮件（无需先保存）。"""
    require_auth(request)
    with db() as conn:
        app_name = get_setting(conn, "app_name", "Fiscus") or "Fiscus"
        entries = reminders.notify_entries(conn, int(body.get("notify_lead_days") or 3))
    emails = str(body.get("notify_emails") or "").strip()
    if "@" not in emails or not body.get("smtp_host"):
        raise HTTPException(status_code=400, detail="请先填写 SMTP 服务器与收件邮箱")
    cfg = {
        "host": str(body.get("smtp_host") or "").strip(),
        "port": int(body.get("smtp_port") or 465),
        "ssl": bool(body.get("smtp_ssl", True)),
        "user": str(body.get("smtp_user") or "").strip(),
        "password": str(body.get("smtp_pass") or ""),
        "sender": str(body.get("smtp_user") or "").strip(),
        "display_name": app_name,
        "to": emails,
    }
    lead = int(body.get("notify_lead_days") or 3)
    try:
        if entries:
            html = mailer.build_html(app_name, entries, lead)
            subject = f"{app_name} · 测试邮件（含当前待办预览）"
        else:
            html = ('<div style="font-family:sans-serif;padding:16px;font-size:14px;">'
                    f'{app_name} 邮箱通道正常，当前没有待提醒事项。</div>')
            subject = f"{app_name} · 测试邮件"
        mailer.send_mail(cfg, subject, html)
        return {"ok": True, "info": "已发送，请查收收件箱（注意垃圾邮件文件夹）"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"发送失败：{e}")


# ---------------------------------------------------------------- 总览快照

@app.get("/api/overview")
def overview(request: Request):
    require_auth(request)
    with db() as conn:
        return reminders.snapshot(conn)


# ---------------------------------------------------------------- 卡片 CRUD

def _validate_card(body: dict, partial: bool = False) -> dict:
    out = {}
    if not partial or "name" in body:
        name = str(body.get("name") or "").strip()
        if not name or len(name) > 30:
            raise HTTPException(status_code=400, detail="卡名不能为空且不超过 30 字")
        out["name"] = name
    if "bank" in body or not partial:
        out["bank"] = str(body.get("bank") or "").strip()[:30]
    if "color" in body or not partial:
        color = str(body.get("color") or "").strip()
        if color and not COLOR_RE.match(color):
            raise HTTPException(status_code=400, detail="卡片色格式应为 #RRGGBB")
        out["color"] = color or PALETTE[len(str(body.get("name", ""))) % len(PALETTE)]
    if "bill_day" in body or not partial:
        try:
            bd = int(body.get("bill_day") or 0)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="账单日格式不正确")
        if not 0 <= bd <= 31:
            raise HTTPException(status_code=400, detail="账单日需在 0-31 之间（0=未设置）")
        out["bill_day"] = bd
    if not partial or "repay_day" in body:
        try:
            rd = int(body.get("repay_day") or 5)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="还款日格式不正确")
        if not 1 <= rd <= 31:
            raise HTTPException(status_code=400, detail="还款日需在 1-31 之间")
        out["repay_day"] = rd
    if "lead_days" in body or not partial:
        try:
            ld = int(body.get("lead_days") or 0)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="提前提醒天数格式不正确")
        if not 0 <= ld <= 30:
            raise HTTPException(status_code=400, detail="提前提醒天数需在 0-30 之间（0=跟随全局）")
        out["lead_days"] = ld
    if "limit" in body or not partial:
        try:
            limit = round(float(body.get("limit") or 0), 2)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="额度格式不正确")
        if limit < 0:
            raise HTTPException(status_code=400, detail="额度不能为负")
        out["limit"] = limit
    if "notes" in body or not partial:
        out["notes"] = str(body.get("notes") or "")[:500]
    if "network" in body or not partial:
        out["network"] = str(body.get("network") or "")[:20]
    if "level" in body or not partial:
        out["level"] = str(body.get("level") or "")[:20]
    if "report_combined" in body or not partial:
        out["report_combined"] = 1 if body.get("report_combined") else 0
    return out


def _card_payload(conn, card_id: int) -> dict:
    row = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
    if not row:
        return {}
    state = reminders.card_state(conn, row)   # 含 image_url / 账单年费权益状态
    state["bills"] = [
        dict(b) for b in conn.execute(
            "SELECT id, period, amount, due_date, paid, updated_at FROM bills "
            "WHERE card_id=? ORDER BY period DESC LIMIT 24", (card_id,))
    ]
    return state


@app.get("/api/cards/{card_id}")
def get_card(request: Request, card_id: int):
    require_auth(request)
    with db() as conn:
        state = _card_payload(conn, card_id)
        if not state:
            raise HTTPException(status_code=404, detail="卡片不存在")
        return state


@app.post("/api/cards")
def create_card(request: Request, body: dict):
    require_auth(request)
    data = _validate_card(body)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with db() as conn:
        max_sort = conn.execute("SELECT COALESCE(MAX(sort_order),0) m FROM cards").fetchone()["m"]
        cur = conn.execute(
            """INSERT INTO cards (name, bank, color, bill_day, repay_day, lead_days,
               limit_amount, notes, sort_order, report_combined, network, level, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (data["name"], data.get("bank", ""), data.get("color", ""), data.get("bill_day", 0),
             data["repay_day"], data.get("lead_days", 0), data.get("limit", 0),
             data.get("notes", ""), max_sort + 1, data.get("report_combined", 0),
             data.get("network", ""), data.get("level", ""), now, now))
        return _card_payload(conn, cur.lastrowid)


@app.put("/api/cards/{card_id}")
def update_card(request: Request, card_id: int, body: dict):
    require_auth(request)
    data = _validate_card(body, partial=True)
    if "limit" in data:                     # limit 是 SQLite 保留字，落库用真实列名
        data["limit_amount"] = data.pop("limit")
    with db() as conn:
        if not conn.execute("SELECT id FROM cards WHERE id=?", (card_id,)).fetchone():
            raise HTTPException(status_code=404, detail="卡片不存在")
        if data:
            sets = ", ".join(f"{k}=?" for k in data)
            conn.execute(
                f"UPDATE cards SET {sets}, updated_at=? WHERE id=?",
                (*data.values(), datetime.datetime.now().isoformat(timespec="seconds"), card_id))
        return _card_payload(conn, card_id)


@app.delete("/api/cards/{card_id}")
def delete_card(request: Request, card_id: int):
    require_auth(request)
    with db() as conn:
        row = conn.execute("SELECT card_image FROM cards WHERE id=?", (card_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="卡片不存在")
        conn.execute("DELETE FROM cards WHERE id=?", (card_id,))   # bills/fees/benefits 级联
        if row["card_image"]:
            path = os.path.join(MEDIA_DIR, "cards", row["card_image"])
            if os.path.isfile(path):
                os.remove(path)
    return {"ok": True}


@app.post("/api/cards/reorder")
def reorder_cards(request: Request, body: dict):
    """卡包排序：body {"ids": [3, 1, 2]} 按传入顺序重排。"""
    require_auth(request)
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="排序数据格式有误")
    with db() as conn:
        for idx, cid in enumerate(ids):
            conn.execute("UPDATE cards SET sort_order=?, updated_at=? WHERE id=?",
                         (idx + 1, datetime.datetime.now().isoformat(timespec="seconds"), int(cid)))
    return {"ok": True}


# ---------------------------------------------------------------- 卡面图上传

def _sniff_image(head: bytes) -> str | None:
    """魔数嗅探真实图片类型（拒绝伪装文件）。"""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def _save_image(file: UploadFile, prefix: str, max_bytes: int) -> tuple[str, bytes]:
    """通用图片保存：魔数嗅探 + 大小限制，返回 (文件名, 内容)。"""
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status_code=400, detail=f"图片不能超过 {max_bytes // (1024 * 1024)}MB")
    ext = _sniff_image(data[:16])
    if not ext:
        raise HTTPException(status_code=400, detail="仅支持 PNG / JPG / WebP 图片")
    ts = int(datetime.datetime.now().timestamp())
    return f"{prefix}_{ts}.{ext}", data


@app.post("/api/cards/{card_id}/image")
def upload_card_image(request: Request, card_id: int, file: UploadFile = File(...)):
    require_auth(request)
    filename, data = _save_image(file, "card", IMAGE_MAX_BYTES)
    with db() as conn:
        row = conn.execute("SELECT card_image FROM cards WHERE id=?", (card_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="卡片不存在")
        with open(os.path.join(MEDIA_DIR, "cards", filename), "wb") as f:
            f.write(data)
        conn.execute("UPDATE cards SET card_image=?, updated_at=? WHERE id=?",
                     (filename, datetime.datetime.now().isoformat(timespec="seconds"), card_id))
        if row["card_image"]:
            old_path = os.path.join(MEDIA_DIR, "cards", row["card_image"])
            if os.path.isfile(old_path):
                os.remove(old_path)
        return {"ok": True, "image_url": f"/api/cards/image/{filename}"}


@app.delete("/api/cards/{card_id}/image")
def clear_card_image(request: Request, card_id: int):
    """清除卡面图，恢复色块模板。"""
    require_auth(request)
    with db() as conn:
        row = conn.execute("SELECT card_image FROM cards WHERE id=?", (card_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="卡片不存在")
        conn.execute("UPDATE cards SET card_image='', updated_at=? WHERE id=?",
                     (datetime.datetime.now().isoformat(timespec="seconds"), card_id))
        if row["card_image"]:
            path = os.path.join(MEDIA_DIR, "cards", row["card_image"])
            if os.path.isfile(path):
                os.remove(path)
    return {"ok": True}


@app.get("/api/cards/image/{filename}")
def get_card_image(request: Request, filename: str):
    require_auth(request)
    if not CARD_IMAGE_RE.match(filename):
        raise HTTPException(status_code=400, detail="非法文件名")
    path = os.path.join(MEDIA_DIR, "cards", filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    media = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}[filename.rsplit(".", 1)[1]]
    return FileResponse(path, media_type=media,
                        headers={"Cache-Control": "private, max-age=86400"})


# ---- 银行 logo（自传；默认无图时邮件与前端用银行名首字色块兜底） ----

@app.post("/api/cards/{card_id}/bank-logo")
def upload_bank_logo(request: Request, card_id: int, file: UploadFile = File(...)):
    require_auth(request)
    filename, data = _save_image(file, "banklogo", 2 * 1024 * 1024)
    with db() as conn:
        row = conn.execute("SELECT bank_logo FROM cards WHERE id=?", (card_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="卡片不存在")
        with open(os.path.join(MEDIA_DIR, "cards", filename), "wb") as f:
            f.write(data)
        conn.execute("UPDATE cards SET bank_logo=?, updated_at=? WHERE id=?",
                     (filename, datetime.datetime.now().isoformat(timespec="seconds"), card_id))
        if row["bank_logo"]:
            old = os.path.join(MEDIA_DIR, "cards", row["bank_logo"])
            if os.path.isfile(old):
                os.remove(old)
    return {"ok": True, "bank_logo_url": f"/api/cards/bank-logo/{filename}"}


@app.delete("/api/cards/{card_id}/bank-logo")
def clear_bank_logo(request: Request, card_id: int):
    require_auth(request)
    with db() as conn:
        row = conn.execute("SELECT bank_logo FROM cards WHERE id=?", (card_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="卡片不存在")
        conn.execute("UPDATE cards SET bank_logo='', updated_at=? WHERE id=?",
                     (datetime.datetime.now().isoformat(timespec="seconds"), card_id))
        if row["bank_logo"]:
            path = os.path.join(MEDIA_DIR, "cards", row["bank_logo"])
            if os.path.isfile(path):
                os.remove(path)
    return {"ok": True}


@app.get("/api/cards/bank-logo/{filename}")
def get_bank_logo(request: Request, filename: str):
    require_auth(request)
    if not CARD_IMAGE_RE.match(filename.replace("banklogo_", "card_", 1)) or not filename.startswith("banklogo_"):
        raise HTTPException(status_code=400, detail="非法文件名")
    path = os.path.join(MEDIA_DIR, "cards", filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    media = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}[filename.rsplit(".", 1)[1]]
    return FileResponse(path, media_type=media,
                        headers={"Cache-Control": "private, max-age=86400"})


# ---------------------------------------------------------------- 账单（记录和提醒还款，产品核心）

@app.post("/api/cards/{card_id}/bill")
def save_bill(request: Request, card_id: int, body: dict):
    """创建/更新某期账单：录入金额 + 标记已还/撤销已还。

    body: {"period": "YYYY-MM", "amount": 数字可选, "paid": 布尔,
           "due_date": "YYYY-MM-DD" 可选（覆盖该期还款截止日）}
    「标记已还」后当期立即退出提醒扫描（快照以 paid 为准）。
    """
    require_auth(request)
    period = str(body.get("period") or "").strip()
    if not re.match(r"^\d{4}-\d{2}$", period):
        raise HTTPException(status_code=400, detail="账单期格式应为 YYYY-MM")
    paid = 1 if body.get("paid") else 0
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with db() as conn:
        if not conn.execute("SELECT id FROM cards WHERE id=?", (card_id,)).fetchone():
            raise HTTPException(status_code=404, detail="卡片不存在")
        existing = conn.execute(
            "SELECT id FROM bills WHERE card_id=? AND period=?", (card_id, period)).fetchone()

        def _amount() -> float:
            try:
                v = round(float(body.get("amount") or 0), 2)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="金额格式不正确")
            if v < 0:
                raise HTTPException(status_code=400, detail="金额不能为负")
            return v

        due_date = str(body.get("due_date") or "").strip()
        if due_date:
            try:
                datetime.date.fromisoformat(due_date)
            except ValueError:
                raise HTTPException(status_code=400, detail="还款截止日格式不正确")
        if existing:
            sets, vals = [], []
            if "amount" in body:
                sets.append("amount=?")
                vals.append(_amount())
            sets.append("paid=?")
            vals.append(paid)
            if due_date:
                sets.append("due_date=?")
                vals.append(due_date)
            sets.append("updated_at=?")
            vals.append(now)
            conn.execute(f"UPDATE bills SET {', '.join(sets)} WHERE id=?",
                         (*vals, existing["id"]))
        else:
            if not due_date:
                raise HTTPException(status_code=400, detail="缺少还款截止日")
            amount = _amount() if "amount" in body else 0
            conn.execute(
                "INSERT INTO bills (card_id, period, amount, due_date, paid, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (card_id, period, amount, due_date, paid, now, now))
        return _card_payload(conn, card_id)


@app.get("/api/cards/{card_id}/bills")
def list_bills(request: Request, card_id: int):
    """单卡账单历史。"""
    require_auth(request)
    with db() as conn:
        if not conn.execute("SELECT id FROM cards WHERE id=?", (card_id,)).fetchone():
            raise HTTPException(status_code=404, detail="卡片不存在")
        rows = conn.execute(
            "SELECT id, period, amount, due_date, paid, updated_at FROM bills "
            "WHERE card_id=? ORDER BY period DESC", (card_id,)).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------- 账单总览（1.2.0 账单 tab）

def _month_days(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


@app.get("/api/bills")
def bills_month(request: Request, month: str = ""):
    """跨卡月度总账：该账单期每张卡一行（未录金额的卡 has_bill=false）+ 汇总。

    还款日所属自然月即账单期（与 card_state 的 period 口径一致）。
    """
    require_auth(request)
    if not re.match(r"^\d{4}-\d{2}$", month or ""):
        raise HTTPException(status_code=400, detail="月份格式应为 YYYY-MM")
    try:
        year, mon = int(month[:4]), int(month[5:7])
        if not (1 <= mon <= 12):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="月份不合法")
    today = datetime.date.today()
    with db() as conn:
        rows = []
        total = paid_sum = unpaid_sum = 0.0
        paid_count = bill_count = 0
        for row in conn.execute("SELECT * FROM cards ORDER BY sort_order, id"):
            bill = conn.execute(
                "SELECT amount, due_date, paid FROM bills WHERE card_id=? AND period=?",
                (row["id"], month)).fetchone()
            r = {
                "card_id": row["id"], "name": row["name"], "bank": row["bank"],
                "color": row["color"],
                "image_url": f"/api/cards/image/{row['card_image']}" if row["card_image"] else "",
                "has_bill": bool(bill),
                "amount": bill["amount"] if bill else 0,
                "due_date": bill["due_date"] if bill else "",
                "paid": bool(bill["paid"]) if bill else False,
            }
            if bill:
                bill_count += 1
                total += bill["amount"]
                if bill["paid"]:
                    paid_count += 1
                    paid_sum += bill["amount"]
                else:
                    unpaid_sum += bill["amount"]
                    if bill["due_date"] and bill["due_date"] < today.isoformat():
                        r["overdue"] = True
            rows.append(r)
        return {
            "month": month, "today": today.isoformat(),
            "cards": rows,
            "summary": {"total": round(total, 2), "paid": round(paid_sum, 2),
                        "unpaid": round(unpaid_sum, 2),
                        "count": bill_count, "paid_count": paid_count},
        }


@app.get("/api/bills/calendar")
def bills_calendar(request: Request, month: str = ""):
    """月历标记（待办月历视图）：该月每天的还款日 / 账单日事件与状态。

    还款日状态：paid 已还绿 / overdue 逾期红 / urgent 临期橙 / todo 未还蓝；
    无账单记录的过去日期不标（没数据不假装），未来的还款日照常标 todo。
    """
    require_auth(request)
    if not re.match(r"^\d{4}-\d{2}$", month or ""):
        raise HTTPException(status_code=400, detail="月份格式应为 YYYY-MM")
    try:
        year, mon = int(month[:4]), int(month[5:7])
        if not (1 <= mon <= 12):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="月份不合法")
    today = datetime.date.today()
    with db() as conn:
        urgent = reminders._urgent_days(conn)
        days: dict = {}
        for row in conn.execute("SELECT * FROM cards ORDER BY sort_order, id"):
            repay_day = int(row["repay_day"] or 0)
            bill_day = int(row["bill_day"] or 0)
            last = _month_days(year, mon)
            rd = min(repay_day, last) if repay_day else 0
            bd = min(bill_day, last) if bill_day else 0
            face = {"card_id": row["id"], "name": row["name"], "color": row["color"],
                    "image_url": f"/api/cards/image/{row['card_image']}" if row["card_image"] else "",
                    "bank": row["bank"]}
            if rd:
                due = datetime.date(year, mon, rd).isoformat()
                bill = conn.execute(
                    "SELECT amount, due_date, paid FROM bills WHERE card_id=? AND period=?",
                    (row["id"], month)).fetchone()
                if bill:
                    st = "paid" if bill["paid"] else (
                        "overdue" if bill["due_date"] and bill["due_date"] < today.isoformat()
                        else "urgent" if (datetime.date.fromisoformat(bill["due_date"] or due)
                                          - today).days <= urgent
                        else "todo")
                    entry = {**face, "kind": "repay", "state": st, "date": due,
                             "period": month, "amount": bill["amount"],
                             "due_date": bill["due_date"] or due, "paid": bool(bill["paid"])}
                elif datetime.date(year, mon, rd) >= today:
                    entry = {**face, "kind": "repay", "state": "todo", "date": due,
                             "period": month, "amount": 0, "due_date": due, "paid": False}
                else:
                    entry = None
                if entry:
                    days.setdefault(due, []).append(entry)
            if bd:
                bdate = datetime.date(year, mon, bd).isoformat()
                days.setdefault(bdate, []).append({**face, "kind": "bill", "date": bdate})
        return {"month": month, "today": today.isoformat(), "days": days}


# ---------------------------------------------------------------- 年费

@app.put("/api/cards/{card_id}/fee")
def save_fee(request: Request, card_id: int, body: dict):
    """保存年费配置（一卡一条）。body: {amount, next_date, rule_note, target_count, done_count}"""
    require_auth(request)
    try:
        amount = round(float(body.get("amount") or 0), 2)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="年费金额格式不正确")
    if amount < 0:
        raise HTTPException(status_code=400, detail="年费金额不能为负")
    try:
        target = int(body.get("target_count") or 0)
        done = int(body.get("done_count") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="笔数格式不正确")
    if not 0 <= target <= 999:
        raise HTTPException(status_code=400, detail="目标笔数需在 0-999 之间")
    if not 0 <= done <= 999:
        raise HTTPException(status_code=400, detail="已刷笔数需在 0-999 之间")
    next_date = str(body.get("next_date") or "").strip()
    if next_date:
        try:
            datetime.date.fromisoformat(next_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="年费日期格式不正确")
    rule_note = str(body.get("rule_note") or "").strip()[:100]
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with db() as conn:
        if not conn.execute("SELECT id FROM cards WHERE id=?", (card_id,)).fetchone():
            raise HTTPException(status_code=404, detail="卡片不存在")
        existing = conn.execute("SELECT id FROM fees WHERE card_id=?", (card_id,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE fees SET amount=?, next_date=?, rule_note=?, target_count=?, "
                "done_count=?, updated_at=? WHERE id=?",
                (amount, next_date, rule_note, target, done, now, existing["id"]))
        else:
            conn.execute(
                "INSERT INTO fees (card_id, amount, next_date, rule_note, target_count, "
                "done_count, updated_at) VALUES (?,?,?,?,?,?,?)",
                (card_id, amount, next_date, rule_note, target, done, now))
        return _card_payload(conn, card_id)


@app.post("/api/cards/{card_id}/fee/bump")
def bump_fee(request: Request, card_id: int, body: dict):
    """已刷 +1 / -1（撤销）。body: {"delta": 1 或 -1}"""
    require_auth(request)
    delta = int(body.get("delta") or 1)
    if delta not in (1, -1):
        raise HTTPException(status_code=400, detail="delta 只支持 1 或 -1")
    with db() as conn:
        row = conn.execute("SELECT done_count FROM fees WHERE card_id=?", (card_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="该卡未配置年费")
        done = max(0, row["done_count"] + delta)
        conn.execute("UPDATE fees SET done_count=?, updated_at=? WHERE card_id=?",
                     (done, datetime.datetime.now().isoformat(timespec="seconds"), card_id))
        return _card_payload(conn, card_id)


# ---------------------------------------------------------------- 权益

def _validate_benefit(body: dict) -> dict:
    name = str(body.get("name") or "").strip()
    if not name or len(name) > 30:
        raise HTTPException(status_code=400, detail="权益名不能为空且不超过 30 字")
    try:
        total = int(body.get("total") or 0)
        used = int(body.get("used") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="次数格式不正确")
    if not 0 <= total <= 9999:
        raise HTTPException(status_code=400, detail="总量需在 0-9999 之间")
    if not 0 <= used <= 9999:
        raise HTTPException(status_code=400, detail="已用需在 0-9999 之间")
    expire_type = str(body.get("expire_type") or "date")
    if expire_type not in ("date", "cycle"):
        raise HTTPException(status_code=400, detail="不支持的有效期类型")
    cycle = str(body.get("cycle") or "yearly")
    if cycle not in ALLOWED_CYCLES:
        raise HTTPException(status_code=400, detail="不支持的刷新周期")
    expire_date = str(body.get("expire_date") or "").strip()
    next_reset = str(body.get("next_reset") or "").strip()
    for label, v in (("到期日", expire_date), ("刷新日", next_reset)):
        if v:
            try:
                datetime.date.fromisoformat(v)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"{label}格式不正确")
    if expire_type == "date" and not expire_date:
        raise HTTPException(status_code=400, detail="固定日期型权益需填写到期日")
    if expire_type == "cycle" and not next_reset:
        raise HTTPException(status_code=400, detail="周期型权益需填写下次刷新日")
    return {"name": name, "total": total, "used": used, "expire_type": expire_type,
            "expire_date": expire_date, "cycle": cycle, "next_reset": next_reset}


@app.post("/api/cards/{card_id}/benefits")
def create_benefit(request: Request, card_id: int, body: dict):
    require_auth(request)
    data = _validate_benefit(body)
    with db() as conn:
        if not conn.execute("SELECT id FROM cards WHERE id=?", (card_id,)).fetchone():
            raise HTTPException(status_code=404, detail="卡片不存在")
        conn.execute(
            "INSERT INTO benefits (card_id, name, total, used, expire_type, expire_date, "
            "cycle, next_reset, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (card_id, data["name"], data["total"], data["used"], data["expire_type"],
             data["expire_date"], data["cycle"], data["next_reset"],
             datetime.datetime.now().isoformat(timespec="seconds")))
        return _card_payload(conn, card_id)


@app.put("/api/benefits/{benefit_id}")
def update_benefit(request: Request, benefit_id: int, body: dict):
    """更新权益（含 用掉一次/退回一次：直接改 used）。"""
    require_auth(request)
    data = _validate_benefit(body)
    with db() as conn:
        row = conn.execute("SELECT id, card_id FROM benefits WHERE id=?", (benefit_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="权益不存在")
        conn.execute(
            "UPDATE benefits SET name=?, total=?, used=?, expire_type=?, expire_date=?, "
            "cycle=?, next_reset=? WHERE id=?",
            (data["name"], data["total"], data["used"], data["expire_type"],
             data["expire_date"], data["cycle"], data["next_reset"], benefit_id))
        return _card_payload(conn, row["card_id"])


@app.delete("/api/benefits/{benefit_id}")
def delete_benefit(request: Request, benefit_id: int):
    require_auth(request)
    with db() as conn:
        row = conn.execute("SELECT id, card_id FROM benefits WHERE id=?", (benefit_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="权益不存在")
        conn.execute("DELETE FROM benefits WHERE id=?", (benefit_id,))
        return _card_payload(conn, row["card_id"])


# ---------------------------------------------------------------- 品牌资产（背景图 / 图标 / 登录页）

@app.post("/api/brand/background")
def upload_background(request: Request, file: UploadFile = File(...)):
    require_auth(request)
    filename, data = _save_image(file, "bg", IMAGE_MAX_BYTES)
    with open(os.path.join(MEDIA_DIR, filename), "wb") as f:
        f.write(data)
    with db() as conn:
        _update_brand_setting(conn, "bg_image", filename)
        return {"ok": True, "bg_image": filename}


@app.delete("/api/brand/background")
def clear_background(request: Request):
    require_auth(request)
    with db() as conn:
        _update_brand_setting(conn, "bg_image", None)
    return {"ok": True}


@app.post("/api/brand/icon")
def upload_icon(request: Request, file: UploadFile = File(...)):
    require_auth(request)
    filename, data = _save_image(file, "icon", 2 * 1024 * 1024)
    with open(os.path.join(MEDIA_DIR, filename), "wb") as f:
        f.write(data)
    with db() as conn:
        _update_brand_setting(conn, "brand_icon", filename)
        return {"ok": True, "brand_icon": filename}


@app.delete("/api/brand/icon")
def clear_icon(request: Request):
    require_auth(request)
    with db() as conn:
        _update_brand_setting(conn, "brand_icon", None)
    return {"ok": True}


@app.post("/api/brand/login-icon")
def upload_login_icon(request: Request, file: UploadFile = File(...)):
    require_auth(request)
    filename, data = _save_image(file, "loginicon", 2 * 1024 * 1024)
    with open(os.path.join(MEDIA_DIR, filename), "wb") as f:
        f.write(data)
    with db() as conn:
        _update_brand_setting(conn, "login_icon", filename)
        return {"ok": True, "login_icon": filename}


@app.delete("/api/brand/login-icon")
def clear_login_icon(request: Request):
    require_auth(request)
    with db() as conn:
        _update_brand_setting(conn, "login_icon", None)
    return {"ok": True}


@app.post("/api/brand/login-background")
def upload_login_background(request: Request, file: UploadFile = File(...)):
    require_auth(request)
    filename, data = _save_image(file, "loginbg", IMAGE_MAX_BYTES)
    with open(os.path.join(MEDIA_DIR, filename), "wb") as f:
        f.write(data)
    with db() as conn:
        _update_brand_setting(conn, "login_bg", filename)
        return {"ok": True, "login_bg": filename}


@app.delete("/api/brand/login-background")
def clear_login_background(request: Request):
    require_auth(request)
    with db() as conn:
        _update_brand_setting(conn, "login_bg", None)
    return {"ok": True}


def _update_brand_setting(conn, key: str, filename: str | None) -> None:
    """更新品牌文件设置并清理旧上传文件（预设值与空值不删文件）。"""
    old = get_setting(conn, key, "")
    set_setting(conn, key, filename or "")
    if old and re.match(r"^(bg|icon|loginicon|loginbg)_\d+\.(png|jpg|webp)$", old):
        old_path = os.path.join(MEDIA_DIR, old)
        if os.path.isfile(old_path):
            os.remove(old_path)


def _media_file_response(filename: str, cache: str) -> FileResponse:
    if not BRAND_RE.match(filename):
        raise HTTPException(status_code=400, detail="非法文件名")
    path = os.path.join(MEDIA_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    media = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}[filename.rsplit(".", 1)[1]]
    return FileResponse(path, media_type=media, headers={"Cache-Control": cache})


@app.get("/api/brand/background")
def get_background(request: Request):
    require_auth(request)
    with db() as conn:
        filename = get_setting(conn, "bg_image", "")
    if not filename or filename.startswith("preset:"):
        raise HTTPException(status_code=404, detail="未设置自定义背景图")
    return _media_file_response(filename, "private, max-age=3600")


@app.get("/api/brand/icon")
def get_icon(request: Request):
    """品牌图标（favicon / 主屏图标共用；未设置时 404，前端回落静态默认图标）。"""
    require_auth(request)
    with db() as conn:
        filename = get_setting(conn, "brand_icon", "")
    if not filename:
        raise HTTPException(status_code=404, detail="未设置自定义图标")
    return _media_file_response(filename, "private, max-age=3600")


@app.get("/api/brand/login-page")
def login_page_public():
    """登录页装饰配置（公开无害：不包含任何邮箱、密码、账单数据）。"""
    with db() as conn:
        return {
            "app_name": get_setting(conn, "app_name", "Fiscus") or "Fiscus",
            "theme_color": get_setting(conn, "theme_color", ""),
            "login_title": get_setting(conn, "login_title", ""),
            "login_welcome": get_setting(conn, "login_welcome", ""),
            "login_bg": get_setting(conn, "login_bg", ""),
            "login_bg_mask": int(get_setting(conn, "login_bg_mask", "45") or 45),
            "login_icon": get_setting(conn, "login_icon", ""),
            "icon_ver": get_setting(conn, "login_icon", "") or get_setting(conn, "brand_icon", "") or "",
        }


@app.get("/api/brand/login-icon")
def get_login_icon(request: Request):
    """登录页图标（公开：登录页在认证前渲染）。"""
    with db() as conn:
        filename = get_setting(conn, "login_icon", "")
    if not filename:
        raise HTTPException(status_code=404, detail="未设置登录页图标")
    return _media_file_response(filename, "private, max-age=600")


@app.get("/api/brand/login-background")
def get_login_background(request: Request):
    """登录页背景（公开：登录页在认证前渲染）。"""
    with db() as conn:
        filename = get_setting(conn, "login_bg", "")
    if not filename or filename in ("", "none") or filename.startswith("preset:"):
        raise HTTPException(status_code=404, detail="未设置登录页背景")
    return _media_file_response(filename, "private, max-age=600")


# ---------------------------------------------------------------- 数据备份（照抄 SubDeck 逻辑）

@app.get("/api/export")
def export_backup(request: Request, sensitive: int = 0):
    """导出备份包 zip。sensitive=1 时保留 SMTP 授权码等敏感设置（默认剔除）。"""
    require_auth(request)
    from . import backup
    data = backup.export_bytes(sensitive=bool(sensitive))
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    filename = f"fiscus-backup-{stamp}.zip"
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/import-status")
def import_status(request: Request):
    """回滚可用性查询（前端据此显隐"回滚上次导入"按钮）。"""
    require_auth(request)
    from . import backup
    return {"has_rollback": backup.has_rollback()}


@app.post("/api/import")
async def import_backup(request: Request):
    """覆盖式导入备份包 zip；导入前自动留档，可一键回滚到导入前。"""
    require_auth(request)
    from . import backup
    try:
        form = await request.form()
        upload = form.get("file")
        if upload is None or isinstance(upload, str):
            raise ValueError("缺少上传文件（字段名 file）")
        data = await upload.read()
        if not data:
            raise ValueError("上传文件为空")
        if len(data) > 64 * 1024 * 1024:
            raise ValueError("备份包超过 64MB 上限，请检查是否选错文件")
        return backup.import_zip_bytes(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/import/rollback")
def rollback_import(request: Request):
    """一键回滚到最近一次导入前的状态（回滚后存档作废）。"""
    require_auth(request)
    from . import backup
    try:
        return backup.rollback()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------- 静态资源与入口

@app.get("/manifest.webmanifest")
def manifest():
    with db() as conn:
        name = get_setting(conn, "app_name", "Fiscus") or "Fiscus"
        icon = get_setting(conn, "brand_icon", "")
        color = get_setting(conn, "theme_color", "")
    icons = [{"src": "/api/brand/icon", "sizes": "192x192", "type": "image/png"}] if icon else [
        {"src": "/assets/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/assets/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
    ]
    return JSONResponse({
        "name": name,
        "short_name": name,
        "start_url": "/",
        "display": "standalone",
        "background_color": "#F5F6FA",
        "theme_color": color if COLOR_RE.match(color or "") else "#4F6EF7",
        "icons": icons,
    })


app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.get("/help/smtp")
def smtp_help():
    path = os.path.join(STATIC_DIR, "docs", "smtp-guide.zh.html")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="帮助文档缺失")
    return FileResponse(path, media_type="text/html")


@app.get("/", response_class=HTMLResponse)
def index():
    # 版本戳注入（照抄 SubDeck v1.6.13）：HTML 里的 ?v=xxx 统一替换为当前 APP_VERSION，
    # 前端资源更新必须换戳，否则浏览器缓存让更新假性失效
    html = Path(os.path.join(STATIC_DIR, "index.html")).read_text(encoding="utf-8")
    return HTMLResponse(content=re.sub(r"\?v=[\w.\-]+", f"?v={APP_VERSION}", html), headers={"Cache-Control": "no-cache"})
