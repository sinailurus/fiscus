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
    check("详情页快捷区含删除", pg.locator("#q-detail-del").count() == 1)
    pg.click("#btn-detail-close")

    # 详情 → 编辑回填（回归：closeDetail 清空 detailId 曾导致编辑变空白新增）
    pg.locator(".card-row").first.click()
    pg.wait_for_selector("#card-detail:not(.hidden)", timeout=5000)
    pg.click("#btn-detail-edit")
    pg.wait_for_selector("#card-modal:not(.hidden)", timeout=5000)
    check("编辑弹窗回填卡名", pg.input_value("#f-name") != "",
          f"got={pg.input_value('#f-name')!r}")
    check("编辑弹窗标题正确", "编辑" in pg.inner_text("#card-modal-title"))
    check("编辑表单含银行 Logo 上传", pg.is_visible("#card-modal .file-btn") and pg.locator("#f-bank-logo").count() == 1)
    # 编辑弹窗删除按钮 → 应用内二次确认（1.2.1：原浏览器原生 confirm 已替换）
    n_before = pg.evaluate("fetch('/api/overview').then(r => r.json()).then(j => j.cards.length)")
    pg.click("#btn-card-delete")
    pg.wait_for_timeout(400)
    check("编辑弹窗删除弹确认", pg.is_visible("#confirm-mask")
          and pg.input_value("#f-name") in pg.inner_text("#confirm-text"),
          pg.inner_text("#confirm-text")[:36])
    pg.click("#btn-confirm-cancel")
    pg.wait_for_timeout(400)
    check("编辑弹窗删除可取消", not pg.is_visible("#confirm-mask")
          and pg.is_visible("#card-modal")
          and pg.evaluate("fetch('/api/overview').then(r => r.json()).then(j => j.cards.length)") == n_before)
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
    # 滑动操作层：模拟展开后点「金额」→ 详情打开并聚焦金额输入
    pg.evaluate("document.querySelector('#todo-sections .swipe-wrap').classList.add('open')")
    pg.wait_for_timeout(200)
    pg.locator(".ta-amount").first.click()
    pg.wait_for_selector("#card-detail:not(.hidden)", timeout=5000)
    check("待办滑动操作进账单编辑", pg.is_visible("#bill-input"))
    focused = pg.evaluate("document.activeElement?.id")
    check("金额输入自动聚焦", focused == "bill-input", f"focused={focused}")
    pg.click("#btn-detail-close")
    pg.screenshot(path=SHOT + "04_mobile_todo.png")

    # ---------- 账单 tab（1.2.0：跨卡月度总账 / 单卡历史 / 补录） ----------
    import datetime as _dt
    today = _dt.date.today()
    ym = today.strftime("%Y-%m")
    prev_ym = (_dt.date(today.year, today.month, 1) - _dt.timedelta(days=1)).strftime("%Y-%m")
    pg.locator('.tab-item[data-tab="bills"]').click()
    pg.wait_for_timeout(900)
    check("账单页月份标签", today.strftime("%Y年%m月") in pg.inner_text("#bill-month-label"),
          pg.inner_text("#bill-month-label"))
    sumtxt = pg.inner_text("#bill-sum")
    check("账单汇总三格", "本期应还" in sumtxt and "已还" in sumtxt and "未还" in sumtxt)
    api_rows = pg.evaluate(f"fetch('/api/bills?month={ym}').then(r => r.json())")
    check("汇总金额正确(已还卡)", api_rows["summary"]["total"] == 2400
          and api_rows["summary"]["paid"] == 2400, str(api_rows["summary"]))
    mk_card = next((r for r in api_rows["cards"] if r["name"] == "招行白金卡"), None)
    check("未录卡 has_bill=false", mk_card and not mk_card["has_bill"],
          str(mk_card and mk_card["name"]))
    badges = pg.locator("#bills-list .badge").all_inner_texts()
    check("徽章状态分布", "已还" in badges and "未录" in badges, str(badges))
    # 单卡历史展开（点已还徽章的行：建行卡有一期）
    pg.locator(".bill-row", has_text="已还").first.click()
    pg.wait_for_timeout(700)
    check("单卡历史展开", pg.locator(".bill-hist:not(.hidden)").count() == 1
          and "共 1 期" in pg.locator(".bill-hist:not(.hidden)").first.inner_text(),
          pg.locator(".bill-hist:not(.hidden)").first.inner_text()[:50])
    # 补录上期账单（建行卡上月）
    pg.click("#btn-bill-add")
    pg.wait_for_timeout(300)
    pg.select_option("#ba-card", label="建行卡")
    pg.fill("#ba-period", prev_ym)
    pg.fill("#ba-due", f"{prev_ym}-28")
    pg.fill("#ba-amount", "1800")
    pg.click("#btn-ba-go")
    pg.wait_for_timeout(900)
    api_prev = pg.evaluate(f"fetch('/api/bills?month={prev_ym}').then(r => r.json())")
    prev_row = next((r for r in api_prev["cards"] if r["name"] == "建行卡"), None)
    check("补录上月账单生效", prev_row and prev_row["has_bill"] and prev_row["amount"] == 1800,
          str(prev_row))
    # 逾期锚点（回归：倒计时不许被惰性滚动重置，SubDeck 前期同款教训）
    ov = pg.evaluate("fetch('/api/overview').then(r => r.json())")
    ccb = next((c for c in ov["cards"] if c["name"] == "建行卡"), None)
    check("逾期卡锚定最早未还期", ccb and ccb["next_due_days"] < 0
          and ccb["next_period"] == prev_ym and ccb["bill_amount"] == 1800,
          f"days={ccb and ccb['next_due_days']} period={ccb and ccb['next_period']}")
    check("概览条显示已逾期", "已逾期" in ov["summary"]["nearest"]["text"],
          str(ov["summary"]["nearest"]))
    pg.locator('.tab-item[data-tab="todo"]').click()
    pg.wait_for_timeout(800)
    check("待办页逾期红徽章", pg.locator('.todo-item', has_text="已过期").count() >= 1)
    pg.locator('.tab-item[data-tab="bills"]').click()
    pg.wait_for_timeout(600)
    # 切到上月看行渲染
    pg.click("#bill-prev")
    pg.wait_for_timeout(700)
    prev_badges = pg.locator("#bills-list .badge").all_inner_texts()
    check("上月视图含补录徽章", "逾期" in prev_badges, str(prev_badges))
    pg.click("#bill-next")
    pg.wait_for_timeout(600)

    # ---------- 待办月历（1.2.0：日期条 ↔ 月历双视图 + 点天打卡） ----------
    pg.locator('.tab-item[data-tab="todo"]').click()
    pg.wait_for_timeout(800)
    check("日期条为默认视图", pg.is_visible("#todo-datebar-wrap")
          and not pg.is_visible("#todo-mcal-wrap"))
    pg.click('#todo-seg button[data-tview="mcal"]')
    pg.wait_for_timeout(900)
    check("月历视图切换", pg.is_visible("#todo-mcal-wrap")
          and not pg.is_visible("#todo-datebar-wrap"))
    cells = pg.locator("#mcal-grid .cell").count()
    check("月历格子数", cells >= 28, f"cells={cells}")
    marks = pg.locator("#mcal-grid .mk").count()
    check("月历还款标记", marks >= 1, f"marks={marks}")
    legend = pg.inner_text(".mcal-legend")
    check("月历图例齐全", all(k in legend for k in ("逾期", "临期", "还款日", "已还", "账单日")))
    cal = pg.evaluate(f"fetch('/api/bills/calendar?month={ym}').then(r => r.json())")
    repay_days = [d for d, evs in cal["days"].items() if any(e["kind"] == "repay" for e in evs)]
    ok_state = any(e.get("state") == "paid" for evs in cal["days"].values() for e in evs if e["kind"] == "repay")
    check("月历状态含已还", ok_state)
    pg.screenshot(path=SHOT + "09_mobile_mcal.png")
    # 点有还款标记的天 → 当日清单 → 打卡
    pg.locator("#mcal-grid .cell:has(.mk):not(.blank)").first.click()
    pg.wait_for_timeout(700)
    check("点天出当日清单", pg.locator("#mcal-day .day-item").count() >= 1)
    has_check = pg.locator("#mcal-day .mday-check").count()
    if has_check:
        was_done = "done" in (pg.locator("#mcal-day .mday-check").first.get_attribute("class") or "")
        pg.locator("#mcal-day .mday-check").first.click()
        pg.wait_for_timeout(900)
        toggled = pg.evaluate(
            f"fetch('/api/bills/calendar?month={ym}').then(r => r.json())"
            ".then(r => Object.values(r.days).flat().filter(e => e.kind === 'repay')"
            ".map(e => e.state))")
        check("月历打卡翻转状态", ("paid" in toggled) != was_done, str(set(toggled)))
    # 切回日期条保持记忆
    pg.click('#todo-seg button[data-tview="datebar"]')
    pg.wait_for_timeout(400)
    check("切回日期条", pg.is_visible("#todo-datebar-wrap"))
    view_saved = pg.evaluate("localStorage.getItem('fiscus-todo-view')")
    check("月历视图记忆落盘", view_saved == "datebar", view_saved)

    # 待办角标开关（1.2.1：设置即改即存，关闭后底栏红色数字气泡隐藏）
    ov_b = pg.evaluate("fetch('/api/overview').then(r => r.json())")
    has_pending = ov_b["cards"] and (
        any(not c["bill_paid"] and c["next_due_days"] <= 7 for c in ov_b["cards"])
        or any(c.get("fee", {}) and c["fee"].get("alert") for c in ov_b["cards"]))
    badge_visible_before = pg.locator("#todo-badge").is_visible()
    pg.locator('.tab-item[data-tab="settings"]').click()
    pg.wait_for_timeout(700)
    if not pg.locator("#set-todo-badge").is_checked():
        pg.click("#set-todo-badge")
        pg.wait_for_timeout(700)
    check("角标开关默认可开", pg.locator("#todo-badge").is_visible()
          or not has_pending, f"pending={has_pending}")
    if has_pending:
        check("有临期项时角标可见", badge_visible_before or pg.locator("#todo-badge").is_visible())
    pg.click("#set-todo-badge")
    pg.wait_for_timeout(700)
    check("关闭后角标隐藏", not pg.locator("#todo-badge").is_visible())
    persisted = pg.evaluate("fetch('/api/settings').then(r => r.json())")
    check("角标开关已持久化", persisted["show_todo_badge"] is False, str(persisted["show_todo_badge"]))
    pg.click("#set-todo-badge")
    pg.wait_for_timeout(700)
    check("重开后角标恢复", pg.locator("#todo-badge").is_visible() or not has_pending)
    pg.locator('.tab-item[data-tab="cards"]').click()
    pg.wait_for_timeout(400)

    # SMTP 授权码教程帮助视图（1.2.1：照抄 SubDeck 站内视图，替换裸 HTML 新标签页）
    pg.locator('.tab-item[data-tab="settings"]').click()
    pg.wait_for_timeout(500)
    pg.click("#link-smtp-guide")
    pg.wait_for_timeout(800)
    check("帮助视图打开", not pg.locator("#tab-smtp-help").is_hidden()
          and "授权码" in pg.locator("#smtp-help-content").inner_text()[:200])
    settings_on = pg.locator('.tab-item[data-tab="settings"].active').count() == 1
    check("帮助页归属设置页高亮", settings_on)
    check("教程排版有样式容器", pg.locator("#smtp-help-content.doc-content h2").count() >= 1)
    pg.click("#btn-smtp-back")
    pg.wait_for_timeout(500)
    check("返回设置页", not pg.locator("#tab-settings").is_hidden()
          and pg.locator("#tab-smtp-help").is_hidden())

    # 登录页设置（1.2.1-beta.8：照抄 SubDeck 六宫格 + 图标区）
    pg.click('.tab-item[data-tab="settings"]'); pg.wait_for_timeout(600)
    check("背景六宫格渲染", pg.locator("#login-bg-picker .bg-card").count() == 6)
    check("主题渐变默认选中", "on" in (pg.locator('#login-bg-picker [data-bg=""]').get_attribute("class") or ""))
    pg.click('#login-bg-picker [data-bg="preset:aurora"]')
    pg.wait_for_timeout(600)
    saved = pg.evaluate("fetch('/api/settings').then(r => r.json()).then(j => j.login_bg)")
    check("选预设即存", saved == "preset:aurora", saved)
    aurora_on = "on" in (pg.locator('#login-bg-picker [data-bg="preset:aurora"]').get_attribute("class") or "")
    check("预设选中态", aurora_on)
    pg.click('#login-bg-picker [data-bg="none"]')
    pg.wait_for_timeout(600)
    saved2 = pg.evaluate("fetch('/api/settings').then(r => r.json()).then(j => j.login_bg)")
    check("无背景即存", saved2 == "none", saved2)
    pg.click('#login-bg-picker [data-bg=""]')
    pg.wait_for_timeout(600)
    # 遮罩滑杆带百分比
    pg.locator("#set-loginbg-mask").scroll_into_view_if_needed()
    mask_pct = pg.inner_text("#set-loginbg-mask-value")
    check("遮罩滑杆百分比", mask_pct.endswith("%"), mask_pct)
    # 登录页图标区（预览 + 两个按钮）
    check("图标区渲染", pg.locator("#login-icon-preview").count() == 1
          and pg.locator("#set-loginicon-file").count() == 1
          and pg.locator("#btn-loginicon-clear").count() == 1)

    # 借记卡（1.2.2：勾选后只进卡包，不进账单/待办/月历/邮件提醒）
    pg.click('.tab-item[data-tab="cards"]'); pg.wait_for_timeout(500)
    pg.click("#btn-add-card"); pg.fill("#f-name", "测试借记卡"); pg.fill("#f-bank", "工商银行")
    pg.check("#f-debit")
    check("勾选借记卡隐藏还款日", pg.locator("#row-repay").is_hidden())
    check("勾选借记卡隐藏账单日", pg.locator("#row-bill").is_hidden())
    pg.click("#btn-card-save"); pg.wait_for_timeout(900)
    ov = pg.evaluate("() => fetch('/api/overview').then(r => r.json())")
    deb = next((c for c in ov["cards"] if c["name"] == "测试借记卡"), None)
    check("借记卡已入卡包", deb is not None and deb["card_type"] == "debit")
    check("借记卡不进概览汇总", all(e["card_name"] != "测试借记卡" for e in ov.get("events", [])))
    # 卡包层叠显示借记卡（含灰徽章）
    pg.click('.seg-btn[data-view="wallet"]'); pg.wait_for_timeout(700)
    check("卡包层叠含借记卡", pg.locator(f'.wallet-card[data-id="{deb["id"]}"]').count() == 1)
    check("借记卡灰徽章", pg.locator(f'.wallet-card[data-id="{deb["id"]}"] .badge-mute').count() == 1)
    # 详情页：无还款信息
    did = deb["id"]
    pg.evaluate(f"() => openDetail({did})")
    pg.wait_for_timeout(900)
    check("借记卡详情无还款区", pg.locator("#q-toggle-paid").count() == 0
          and pg.locator("#bill-save").count() == 0)
    check("借记卡详情显示类型行", "借记卡" in pg.locator("#detail-body").inner_text())
    pg.evaluate("() => closeDetail()"); pg.wait_for_timeout(400)
    # 账单页不含借记卡
    bills = pg.evaluate("""() => fetch('/api/bills?month=' + new Date().toISOString().slice(0, 7))
        .then(r => r.json())""")
    check("账单页不含借记卡", all(c["name"] != "测试借记卡" for c in bills["cards"]))
    cal = pg.evaluate("""() => fetch('/api/bills/calendar?month=' + new Date().toISOString().slice(0, 7))
        .then(r => r.json())""")
    cal_names = [e["name"] for d in (cal.get("days") or {}).values() for e in d]
    check("月历不含借记卡", "测试借记卡" not in cal_names)
    # 编辑弹窗回显勾选
    pg.click('.seg-btn[data-view="list"]'); pg.wait_for_timeout(400)
    pg.evaluate(f"() => openCardModal({did})")
    pg.wait_for_timeout(500)
    check("编辑回显借记卡勾选", pg.locator("#f-debit").is_checked()
          and pg.locator("#row-repay").is_hidden())
    pg.click("#btn-card-modal-close"); pg.wait_for_timeout(300)

    # 卡面文字亮度自适应（1.2.1-beta.6：亮色卡深字/暗色卡白字）
    pg.evaluate("""async () => {
      await fetch('/api/cards', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({name: '亮色验证卡', color: '#FFD54F', repay_day: 15})});
      await fetch('/api/cards', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({name: '暗色验证卡', color: '#1A237E', repay_day: 16})});
    }""")
    pg.reload(wait_until="networkidle"); pg.wait_for_timeout(1200)
    id_map = pg.evaluate("""() => fetch('/api/overview').then(r => r.json())
      .then(j => Object.fromEntries(j.cards.map(c => [c.name, c.id])))""")
    light_ids = pg.evaluate("""() =>
      [...document.querySelectorAll('.wallet-card.face-light')].map(e => +e.dataset.id)""")
    check("亮色卡切深字", id_map.get("亮色验证卡") in light_ids,
          f"light={light_ids} map={id_map}")
    check("暗色卡保持白字", id_map.get("暗色验证卡") not in light_ids)
    # 图例并入月历容器
    pg.click('.tab-item[data-tab="todo"]'); pg.wait_for_timeout(600)
    pg.click('#todo-seg button[data-tview="mcal"]'); pg.wait_for_timeout(800)
    inside = pg.evaluate("() => !!document.querySelector('.mcal .mcal-legend')")
    legend_color = pg.evaluate("""() => {
      const i = document.querySelector('.mcal-legend i');
      return getComputedStyle(i).color;
    }""")
    check("图例并入月历容器", inside and legend_color not in ("rgba(0, 0, 0, 0)", ""),
        f"容器内={inside} 文字色={legend_color}")

    # 逾期账单打卡后倒计时恢复滚动（逾期义务确认了才走）
    ov2 = pg.evaluate("fetch('/api/overview').then(r => r.json())")
    ccb2 = next((c for c in ov2["cards"] if c["name"] == "建行卡"), None)
    if ccb2 and ccb2["next_due_days"] < 0:
        pg.evaluate("""(c) => fetch(`/api/cards/${c.id}/bill`, {method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({period: c.next_period, paid: true,
                due_date: c.next_due, amount: c.bill_amount || 0})}).then(r => r.json())""",
            ccb2)
        pg.wait_for_timeout(400)
        ov3 = pg.evaluate("fetch('/api/overview').then(r => r.json())")
        ccb3 = next((c for c in ov3["cards"] if c["name"] == "建行卡"), None)
        check("逾期打卡后恢复滚动", ccb3 and ccb3["next_due_days"] > 0,
              f"days={ccb3 and ccb3['next_due_days']} period={ccb3 and ccb3['next_period']}")
    else:
        check("逾期卡打卡后恢复滚动", False, "建行卡未处于逾期态，前置异常")

    # 卡包视图点卡 → 展开态（置顶卡 + 基本信息块 + 编辑按钮），点编辑进编辑弹窗
    pg.locator('.tab-item[data-tab="cards"]').click()
    pg.click('.seg-btn[data-view="wallet"]')
    pg.wait_for_timeout(500)
    check("卡包视图渲染", pg.locator(".wallet-card").count() >= 3)
    pg.locator(".wallet-card").first.click(position={"x": 100, "y": 20})
    pg.wait_for_selector(".wallet-info-panel", timeout=5000)
    check("卡包展开态含信息块", pg.is_visible(".wallet-info-panel"))
    pg.click("#btn-wallet-edit")
    pg.wait_for_selector("#card-modal:not(.hidden)", timeout=5000)
    check("展开态编辑按钮进编辑弹窗", pg.input_value("#f-name") != "")
    pg.click("#btn-card-modal-close")
    pg.wait_for_timeout(300)
    # 展开面板删除卡片（1.2.1：删除按钮 + 二次确认）
    rows_before = pg.evaluate("fetch('/api/overview').then(r => r.json()).then(j => j.cards.length)")
    wip_name = pg.locator(".wallet-open .wip-grid .wip-v").first.inner_text()
    pg.click("#btn-wallet-del")
    pg.wait_for_timeout(400)
    check("删除弹二次确认窗", pg.is_visible("#confirm-mask")
          and wip_name in pg.inner_text("#confirm-text"),
          pg.inner_text("#confirm-text")[:36])
    pg.click("#btn-confirm-cancel")
    pg.wait_for_timeout(500)
    check("取消后卡片仍在", pg.evaluate(
        "fetch('/api/overview').then(r => r.json()).then(j => j.cards.length)") == rows_before)
    pg.click("#btn-wallet-del")
    pg.wait_for_timeout(400)
    pg.click("#btn-confirm-go")
    pg.wait_for_timeout(1000)
    rows_after = pg.evaluate("fetch('/api/overview').then(r => r.json()).then(j => j.cards.length)")
    check("确认后卡片已删除", rows_after == rows_before - 1, f"{rows_before} -> {rows_after}")
    check("删除后回到层叠视图", pg.locator(".wallet-info-panel").count() == 0
          and pg.locator(".wallet-card").count() >= 1)
    pg.locator(".wallet-card").first.click(position={"x": 100, "y": 20})
    pg.wait_for_selector(".wallet-info-panel", timeout=5000)
    pg.click("#btn-wallet-collapse")
    pg.wait_for_timeout(300)
    check("收起返回层叠", pg.locator(".wallet-info-panel").count() == 0)
    pg.screenshot(path=SHOT + "05_mobile_wallet.png")

    # 展开态：点底部折叠卡面 → 恢复完整层叠视图
    pg.locator(".wallet-card").first.click(position={"x": 100, "y": 20})
    pg.wait_for_selector(".wallet-info-panel", timeout=5000)
    pg.locator(".wallet-card-mini").last.click(position={"x": 100, "y": 10})
    pg.wait_for_timeout(500)
    check("点折叠卡恢复完整视图", pg.locator(".wallet-info-panel").count() == 0
          and pg.locator(".wallet-card").count() >= 2)

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
    pg2.click('.topnav .nav-btn[data-tab="cards"]')
    pg2.wait_for_timeout(400)
    pg2.screenshot(path=SHOT + "07_desktop_table.png")
    pg2.locator("#cards-tbody tr").first.click()
    pg2.wait_for_selector("#card-detail:not(.hidden)", timeout=5000)
    pg2.screenshot(path=SHOT + "08_desktop_drawer.png")
    check("桌面抽屉打开", pg2.is_visible("#card-detail"))
    check("桌面表格视图", pg2.is_visible("#cards-table"))
    check("桌面顶栏导航", pg2.is_visible(".topnav"))
    ctx2.close()

    browser.close()

fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)}/{len(results)} 通过")
sys.exit(1 if fails else 0)
