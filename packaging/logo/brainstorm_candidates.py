# -*- coding: utf-8 -*-
"""Fiscus logo 方向打样：三个独立设计并排渲染，供选择。

A 罗马硬币 F —— Fiscus 直译「国库」：一枚罗马钱币，珠链币缘 + 碑刻阴文 F，
   圆形形态与 SubDeck 的圆角方彻底区分，与 Compitum/Ignis 的罗马族系同源。
B 束口钱袋 + 卡角 —— fiscus 的本义是罗马人随身钱篮：两张卡从束口袋口探出，
   「卡收进钱袋」就是产品本体。
C 竖卡 + 表盘 —— 记卡与提醒还款的合体：竖置信用卡下半嵌一只表盘，
   指针临近十二点 = 临近还款日。
"""
import cairosvg
from PIL import Image, ImageDraw

OUT = "/home/z/my-project/fiscus/packaging/logo"

GREEN = "#1fa07e"
GREEN_D = "#137a5f"
GOLD_A = "#f3d680"
GOLD_B = "#c9a85c"
INK = "#0e6a52"

BG = f'''<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="{GREEN}"/><stop offset="1" stop-color="{GREEN_D}"/>
</linearGradient></defs>
<rect width="1024" height="1024" rx="228" fill="url(#bg)"/>'''

# ---------------- A 罗马硬币 F ----------------
SVG_A = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
{BG}
<defs>
  <radialGradient id="coin" cx="0.38" cy="0.34" r="0.9">
    <stop offset="0" stop-color="#f2d98e"/><stop offset="1" stop-color="#b8863c"/>
  </radialGradient>
</defs>
<circle cx="512" cy="512" r="318" fill="url(#coin)"/>
<circle cx="512" cy="512" r="296" fill="none" stroke="#8a6a2e" stroke-width="12"
        stroke-dasharray="4 26" stroke-linecap="round" opacity="0.85"/>
<circle cx="512" cy="512" r="268" fill="none" stroke="#ffffff" stroke-width="6" opacity="0.35"/>
<g fill="#ffffff" opacity="0.35" transform="translate(-9 -9)">
  <rect x="446" y="356" width="112" height="330" rx="10"/>
  <rect x="446" y="356" width="240" height="112" rx="10"/>
  <rect x="446" y="500" width="196" height="92" rx="10"/>
</g>
<g fill="{INK}">
  <rect x="446" y="356" width="112" height="330" rx="10"/>
  <rect x="446" y="356" width="240" height="112" rx="10"/>
  <rect x="446" y="500" width="196" height="92" rx="10"/>
</g>
</svg>'''

# ---------------- B 束口钱袋 + 卡角 ----------------
SVG_B = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
{BG}
<defs>
  <linearGradient id="chip" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{GOLD_A}"/><stop offset="1" stop-color="{GOLD_B}"/>
  </linearGradient>
</defs>
<g transform="rotate(-6 512 400)"><rect x="420" y="262" width="216" height="360" rx="34" fill="#ffffff" opacity="0.45"/></g>
<rect x="388" y="292" width="232" height="380" rx="36" fill="#ffffff"/>
<rect x="428" y="330" width="84" height="64" rx="14" fill="url(#chip)"/>
<path d="M356 462 L668 462 C662 700 604 786 512 786 C420 786 362 700 356 462 Z" fill="#ffffff"/>
<path d="M356 462 L668 462 C666 528 652 576 632 616 C600 560 512 560 512 560 C512 560 424 560 392 616 C372 576 358 528 356 462 Z"
      fill="{GREEN_D}" opacity="0.16"/>
<rect x="340" y="428" width="344" height="64" rx="32" fill="url(#chip)"/>
<circle cx="512" cy="460" r="26" fill="{GREEN_D}"/>
<rect x="492" y="486" width="16" height="110" rx="8" fill="url(#chip)"/>
<rect x="516" y="486" width="16" height="86" rx="8" fill="url(#chip)"/>
</svg>'''

# ---------------- C 竖卡 + 表盘 ----------------
SVG_C = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
{BG}
<defs>
  <radialGradient id="dial" cx="0.4" cy="0.35" r="0.95">
    <stop offset="0" stop-color="{GOLD_A}"/><stop offset="1" stop-color="{GOLD_B}"/>
  </radialGradient>
</defs>
<rect x="356" y="262" width="292" height="460" rx="42" fill="#ffffff" opacity="0.42" transform="rotate(-4 512 512)"/>
<rect x="336" y="284" width="292" height="460" rx="42" fill="#ffffff"/>
<rect x="382" y="336" width="86" height="66" rx="14" fill="url(#dial)"/>
<path d="M382 430 h110" stroke="#1F2430" stroke-width="18" stroke-linecap="round" opacity="0.18"/>
<path d="M382 470 h86" stroke="#1F2430" stroke-width="18" stroke-linecap="round" opacity="0.18"/>
<circle cx="606" cy="606" r="164" fill="url(#dial)"/>
<circle cx="606" cy="606" r="128" fill="#ffffff"/>
<g stroke="{GREEN_D}" stroke-width="10" stroke-linecap="round">
  <path d="M606 494 v26"/><path d="M606 692 v26"/><path d="M494 606 h26"/><path d="M692 606 h26"/>
</g>
<path d="M606 606 L606 516" stroke="{GREEN_D}" stroke-width="16" stroke-linecap="round"/>
<path d="M606 606 L668 656" stroke="{GREEN_D}" stroke-width="16" stroke-linecap="round"/>
<circle cx="606" cy="606" r="16" fill="{GREEN_D}"/>
</svg>'''


def render(svg, path, size):
    cairosvg.svg2png(bytestring=svg.encode(), write_to=path, output_width=size, output_height=size)


panels = [("logo-candidate-a.png", SVG_A), ("logo-candidate-b.png", SVG_B), ("logo-candidate-c.png", SVG_C)]
imgs = []
for name, svg in panels:
    render(svg, f"{OUT}/{name}", 560)
    imgs.append(Image.open(f"{OUT}/{name}"))

gap, pad = 36, 24
W = pad * 2 + gap * 2 + 560 * 3
sheet = Image.new("RGBA", (W, 560 + pad * 2 + 64), (255, 255, 255, 255))
d = ImageDraw.Draw(sheet)
for i, im in enumerate(imgs):
    x = pad + i * (560 + gap)
    sheet.paste(im, (x, pad), im)
    d.text((x + 560 // 2 - 10, pad + 560 + 18), "ABC"[i], fill=(40, 44, 52))
sheet.convert("RGB").save(f"{OUT}/logo-candidates.png")
print("done")
