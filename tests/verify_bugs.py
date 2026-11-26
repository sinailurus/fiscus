# -*- coding: utf-8 -*-
"""真机反馈五 bug 专项验证（2026-11-26）：390px 手机视口。

1. 设置页不再撑宽（横向无滚动）
2. 待办勾选后进入「本期已还」区，可撤销恢复
3. 上传卡面后不再渲染金色芯片装饰
4. 编辑弹窗上传行不再重叠
5. 卡面为实体银行卡比例（85.6:54）
"""
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8901"
SHOT = "/home/z/my-project/fiscus/tests/"

results = []


def check(name, ok, extra=""):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {extra}")


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))

    pg.goto(BASE, wait_until="networkidle")
    pg.fill("#login-password", "test123")
    pg.click("#btn-login")
    pg.wait_for_selector("#view-app:not(.hidden)", timeout=5000)
    for c in ctx.request.get(f"{BASE}/api/overview").json()["cards"]:
        ctx.request.delete(f"{BASE}/api/cards/{c['id']}")
    pg.reload(wait_until="networkidle")

    # 建 3 张卡（其中一张上传卡面）
    from PIL import Image
    Image.new("RGB", (856, 540), (90, 110, 200)).save("/tmp/face.png")
    for i, (name, bank, day) in enumerate([("招行白金", "招商银行", 5), ("建行卡", "建设银行", 12), ("农行卡", "农业银行", 20)]):
        pg.click("#btn-add-card")
        pg.fill("#f-name", name)
        pg.fill("#f-bank", bank)
        pg.fill("#f-repay", str(day))
        if i == 0:
            pg.set_input_files("#f-image", "/tmp/face.png")
        pg.click("#btn-card-save")
        pg.wait_for_timeout(600)
    check("bug5：编辑保存链路可用（建卡无 500）", pg.locator(".card-row").count() == 3)

    # bug1：设置页不撑宽
    pg.locator('.tab-item[data-tab="settings"]').click()
    pg.wait_for_timeout(600)
    sw = pg.evaluate("document.documentElement.scrollWidth")
    check("bug1：设置页无横向溢出", sw <= 390, f"scrollWidth={sw}")
    pg.screenshot(path=SHOT + "10_fix_settings.png")

    # bug2：待办勾选 → 本期已还 → 撤销
    pg.locator('.tab-item[data-tab="todo"]').click()
    pg.wait_for_timeout(600)
    pg.locator(".todo-check").first.click()
    pg.wait_for_timeout(800)
    done_items = pg.locator(".todo-section", has_text="本期已还").locator(".todo-item").count()
    check("bug2：勾选后出现在本期已还", done_items >= 1, f"done={done_items}")
    pg.screenshot(path=SHOT + "11_fix_todo_done.png")
    pg.locator(".todo-section", has_text="本期已还").locator(".todo-check").first.click()
    pg.wait_for_timeout(800)
    done_items2 = pg.locator(".todo-section", has_text="本期已还").locator(".todo-item").count()
    check("bug2：撤销后从已还区移除", done_items2 == 0, f"done={done_items2}")

    # bug3：卡包里上传过卡面的卡无芯片装饰，未上传的有
    pg.locator('.tab-item[data-tab="cards"]').click()
    pg.click('.seg-btn[data-view="wallet"]')
    pg.wait_for_timeout(600)
    chips = pg.locator(".wallet-chip").count()
    faces = pg.locator(".wallet-face").count()
    withimg = pg.locator('.wallet-face[style*="background-image"]').count()
    check("bug3：卡面图卡无芯片装饰", chips == faces - withimg, f"chip={chips} face={faces} withimg={withimg}")
    ar = pg.evaluate("document.querySelector('.wallet-face').getBoundingClientRect().width / document.querySelector('.wallet-face').getBoundingClientRect().height")
    check("卡面为实体卡比例", abs(ar - 85.6 / 54) < 0.02, f"ratio={ar:.3f} 目标={85.6 / 54:.3f}")
    pg.screenshot(path=SHOT + "12_fix_wallet_ratio.png")

    # bug4：编辑弹窗上传行不重叠
    pg.locator(".wallet-card").first.click(position={"x": 100, "y": 20})
    pg.wait_for_selector("#card-detail:not(.hidden)")
    pg.click("#btn-detail-edit")
    pg.wait_for_selector("#card-modal:not(.hidden)")
    row_box = pg.locator("#f-bank-logo").bounding_box()
    hint_box = pg.locator("#f-bank-logo ~ * , .form-hint").first.bounding_box()
    overlap = hint_box and row_box and hint_box["y"] < row_box["y"] + row_box["height"] - 2
    check("bug4：上传行与提示不重叠", not overlap)
    pg.screenshot(path=SHOT + "13_fix_modal.png")
    pg.click("#btn-card-modal-close")

    console_errs = [e for e in errors if "favicon" not in e.lower()]
    check("无控制台错误", not console_errs, "; ".join(console_errs[:2]))
    ctx.close()
    browser.close()

fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)}/{len(results)} 通过")
sys.exit(1 if fails else 0)
