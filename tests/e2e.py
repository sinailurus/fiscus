# -*- coding: utf-8 -*-
"""Fiscus v1.0.0 本地 e2e 验证（无头浏览器）。

前置：测试服务已运行在 127.0.0.1:8901（AUTH_PASSWORD=test123，干净数据目录）。
覆盖：登录 / 建卡 / 记金额 / 标记已还 / 双视图 / 待办页打卡 / 聚焦详情 / 设置页。
"""
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8901"
SHOT = "/home/z/my-project/fiscus/tests/"

results = []


def check(name, ok, extra=""):
    results.append((name, ok, extra))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {extra}")


with sync_playwright() as p:
    browser = p.chromium.launch()

    # ============ 手机视口 ============
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    pg.goto(BASE, wait_until="networkidle")
    check("登录页渲染", pg.is_visible("#view-login"))
    pg.screenshot(path=SHOT + "01_login.png")

    pg.fill("#login-password", "test123")
    pg.click("#btn-login")
    pg.wait_for_selector("#view-app:not(.hidden)", timeout=5000)
    check("登录进入主应用", pg.is_visible("#view-app"))

    # 清理历史数据（保证 e2e 幂等重跑）
    for c in ctx.request.get(f"{BASE}/api/overview").json()["cards"]:
        ctx.request.delete(f"{BASE}/api/cards/{c['id']}")
    pg.reload(wait_until="networkidle")

    # 建卡
    pg.click("#btn-add-card")
    pg.fill("#f-name", "招行白金卡")
    pg.fill("#f-bank", "招商银行")
    pg.fill("#f-repay", "10")
    pg.fill("#f-limit", "30000")
    pg.click("#btn-card-save")
    pg.wait_for_timeout(600)
    check("建卡出现列表", pg.is_visible(".card-row"))

    # 再建两张（不同还款日，制造临期/常规/已还三种状态）
    pg.click("#btn-add-card")
    pg.fill("#f-name", "建行卡")
    pg.fill("#f-bank", "建设银行")
    pg.fill("#f-repay", "28")
    pg.click("#btn-card-save")
    pg.wait_for_timeout(500)
    pg.click("#btn-add-card")
    pg.fill("#f-name", "邮储卡")
    pg.fill("#f-repay", "1")
    pg.click("#btn-card-save")
    pg.wait_for_timeout(500)
    rows = pg.locator(".card-row").count()
    check("三张卡都在列表", rows == 3, f"rows={rows}")
    pg.screenshot(path=SHOT + "02_mobile_list.png")

    # 列表视图 → 点第一张卡进聚焦详情
    pg.locator(".card-row").first.click()
    pg.wait_for_selector("#card-detail:not(.hidden)", timeout=5000)
    check("聚焦详情打开", pg.is_visible("#card-detail"))
    pg.screenshot(path=SHOT + "03_mobile_detail.png")

    # 记金额 + 标记已还
    pg.fill("#bill-input", "2400")
    pg.click("#bill-save")
    pg.wait_for_timeout(500)
    body = pg.inner_text("#detail-body")
    check("金额已保存显示", "2,400" in body)
    pg.click("#q-toggle-paid")
    pg.wait_for_timeout(600)
    check("标记已还按钮翻转", "撤销已还" in pg.inner_text("#detail-body"))
    pg.click("#btn-detail-close")

    # 详情 → 编辑回填（回归：closeDetail 清空 detailId 曾导致编辑变空白新增）
    pg.locator(".card-row").first.click()
    pg.wait_for_selector("#card-detail:not(.hidden)", timeout=5000)
    pg.click("#btn-detail-edit")
    pg.wait_for_selector("#card-modal:not(.hidden)", timeout=5000)
    check("编辑弹窗回填卡名", pg.input_value("#f-name") != "",
          f"got={pg.input_value('#f-name')!r}")
    check("编辑弹窗标题正确", "编辑" in pg.inner_text("#card-modal-title"))
    check("编辑表单含银行 Logo 上传", pg.is_visible("#f-bank-logo"))
    pg.click("#btn-card-modal-close")
    pg.wait_for_timeout(300)
    pg.locator(".card-row").first.click()
    pg.wait_for_selector("#card-detail:not(.hidden)", timeout=5000)
    pg.click("#btn-detail-close")

    # 上传卡面图（回归：card_state 曾漏 image_url 导致列表/卡包不显示）
    from PIL import Image
    Image.new("RGB", (640, 400), (79, 110, 247)).save("/tmp/e2e_cardface.png")
    pg.click("#btn-add-card")
    pg.fill("#f-name", "卡面图测试")
    pg.fill("#f-repay", "15")
    pg.set_input_files("#f-image", "/tmp/e2e_cardface.png")
    pg.click("#btn-card-save")
    pg.wait_for_timeout(900)
    ov = pg.evaluate("fetch('/api/overview').then(r => r.json())")
    target = next((c for c in ov["cards"] if c["name"] == "卡面图测试"), None)
    check("列表数据含卡面图地址", bool(target and target.get("image_url")),
          f"image_url={target and target.get('image_url')!r}")
    pg.click('.tab-item[data-tab="cards"]')
    pg.click('.seg-btn[data-view="wallet"]')
    pg.wait_for_timeout(600)
    check("卡包视图渲染卡面图",
          pg.locator('.wallet-face[style*="background-image"]').count() >= 1)
    # 清理这张测试卡（不影响后续用例计数）
    if target:
        ctx.request.delete(f"{BASE}/api/cards/{target['id']}")
    pg.wait_for_timeout(400)

    # 待办页
    pg.locator('.tab-item[data-tab="todo"]').click()
    pg.wait_for_timeout(700)
    check("待办页渲染", pg.is_visible(".todo-section"))
    check("日期条渲染", pg.locator(".date-cell").count() >= 14)
    pg.screenshot(path=SHOT + "04_mobile_todo.png")

    # 卡包视图切换
    pg.locator('.tab-item[data-tab="cards"]').click()
    pg.click('.seg-btn[data-view="wallet"]')
    pg.wait_for_timeout(500)
    check("卡包视图渲染", pg.locator(".wallet-card").count() == 3)
    pg.screenshot(path=SHOT + "05_mobile_wallet.png")

    # 卡包视图点卡（点第一张卡顶部露出区，避免点到被后卡覆盖的区域）
    pg.locator(".wallet-card").first.click(position={"x": 100, "y": 20})
    pg.wait_for_selector("#card-detail:not(.hidden)", timeout=5000)
    pg.click("#btn-detail-close")
    check("卡包视图点卡开详情", True)

    # 设置页
    pg.locator('.tab-item[data-tab="settings"]').click()
    pg.wait_for_timeout(400)
    check("设置页渲染", pg.is_visible("#set-app-name"))
    pg.screenshot(path=SHOT + "06_mobile_settings.png")
    console_errs = [e for e in errors if "favicon" not in e.lower()]
    check("手机端无控制台错误", not console_errs, "; ".join(console_errs[:2]))
    ctx.close()

    # ============ 桌面视口 ============
    ctx2 = browser.new_context(viewport={"width": 1280, "height": 800})
    pg2 = ctx2.new_page()
    pg2.goto(BASE, wait_until="networkidle")
    pg2.fill("#login-password", "test123")
    pg2.click("#btn-login")
    pg2.wait_for_selector("#view-app:not(.hidden)", timeout=5000)
    check("桌面端登录进入", pg2.is_visible("#view-app"))
    pg2.click('.seg-btn[data-view="wallet"]')
    pg2.wait_for_timeout(400)
    pg2.screenshot(path=SHOT + "07_desktop_wallet.png")
    pg2.locator(".wallet-card").first.click(position={"x": 100, "y": 20})
    pg2.wait_for_selector("#card-detail:not(.hidden)", timeout=5000)
    pg2.screenshot(path=SHOT + "08_desktop_drawer.png")
    check("桌面抽屉打开", pg2.is_visible("#card-detail"))
    ctx2.close()

    browser.close()

fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)}/{len(results)} 通过")
sys.exit(1 if fails else 0)
