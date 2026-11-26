# -*- coding: utf-8 -*-
"""Fiscus logo 生成器（v1.0.0 资产，C 方向定稿）。
设计：竖置信用卡 + 右下表盘压角，指针临近十二点（临近还款日）。
青绿渐变底，金表圈与金芯片同源呼应。TA 拍板方向 C（2026-11-26）。
导出：SVG 源文件 / PNG 全尺寸 / maskable 512 / 网页图标。
"""
import os
import cairosvg

OUT = "/home/z/my-project/fiscus/packaging/logo"
WEB = "/home/z/my-project/fiscus/static/icons"
os.makedirs(OUT, exist_ok=True)

GREEN = "#1fa07e"          # Fiscus 主色
GREEN_D = "#137a5f"
GOLD_A = "#f3d680"
GOLD_B = "#c9a85c"

BG = f'''<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="{GREEN}"/><stop offset="1" stop-color="{GREEN_D}"/>
</linearGradient>
<radialGradient id="dial" cx="0.4" cy="0.35" r="0.95">
<stop offset="0" stop-color="{GOLD_A}"/><stop offset="1" stop-color="{GOLD_B}"/>
</radialGradient></defs>
<rect width="1024" height="1024" rx="228" fill="url(#bg)"/>'''

# ---------- 主视觉（1024×1024，图形居 maskable 安全区内） ----------
SVG_FULL = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
{BG}
<rect x="322" y="268" width="292" height="470" rx="42" fill="#ffffff" opacity="0.5" transform="rotate(-5 512 512)"/>
<rect x="336" y="296" width="292" height="470" rx="42" fill="#ffffff"/>
<rect x="382" y="350" width="88" height="66" rx="14" fill="url(#dial)"/>
<path d="M382 448 h110" stroke="#1F2430" stroke-width="18" stroke-linecap="round" opacity="0.15"/>
<path d="M382 490 h84" stroke="#1F2430" stroke-width="18" stroke-linecap="round" opacity="0.15"/>
<circle cx="618" cy="610" r="170" fill="url(#dial)"/>
<circle cx="618" cy="610" r="134" fill="#ffffff"/>
<g stroke="{GREEN_D}" stroke-width="11" stroke-linecap="round">
  <path d="M618 492 v28"/><path d="M618 700 v28"/><path d="M500 610 h28"/><path d="M708 610 h28"/>
</g>
<path d="M618 610 L618 508" stroke="{GREEN_D}" stroke-width="19" stroke-linecap="round"/>
<path d="M618 610 L568 568" stroke="{GREEN_D}" stroke-width="17" stroke-linecap="round"/>
<circle cx="618" cy="610" r="16" fill="{GREEN_D}"/>
</svg>'''

# ---------- favicon 简化版（≤48px：卡角 + 大表盘 + 粗指针，去刻度） ----------
SVG_SIMPLE = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
{BG}
<rect x="378" y="322" width="228" height="360" rx="38" fill="#ffffff" opacity="0.5" transform="rotate(-6 512 512)"/>
<rect x="348" y="356" width="228" height="360" rx="38" fill="#ffffff"/>
<circle cx="596" cy="616" r="162" fill="url(#dial)"/>
<circle cx="596" cy="616" r="122" fill="#ffffff"/>
<path d="M596 616 L596 516" stroke="{GREEN_D}" stroke-width="30" stroke-linecap="round"/>
<path d="M596 616 L546 574" stroke="{GREEN_D}" stroke-width="26" stroke-linecap="round"/>
<circle cx="596" cy="616" r="22" fill="{GREEN_D}"/>
</svg>'''

# ---------- maskable（图形收缩进安全区） ----------
SVG_MASKABLE = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
<rect width="1024" height="1024" fill="{GREEN}"/>
<g transform="translate(512 512) scale(0.72) translate(-512 -512)">
<defs>
<radialGradient id="dial" cx="0.4" cy="0.35" r="0.95">
<stop offset="0" stop-color="{GOLD_A}"/><stop offset="1" stop-color="{GOLD_B}"/>
</radialGradient></defs>
<rect x="322" y="268" width="292" height="470" rx="42" fill="#ffffff" opacity="0.5" transform="rotate(-5 512 512)"/>
<rect x="336" y="296" width="292" height="470" rx="42" fill="#ffffff"/>
<rect x="382" y="350" width="88" height="66" rx="14" fill="url(#dial)"/>
<circle cx="618" cy="610" r="170" fill="url(#dial)"/>
<circle cx="618" cy="610" r="134" fill="#ffffff"/>
<path d="M618 610 L618 508" stroke="{GREEN_D}" stroke-width="19" stroke-linecap="round"/>
<path d="M618 610 L568 568" stroke="{GREEN_D}" stroke-width="17" stroke-linecap="round"/>
<circle cx="618" cy="610" r="16" fill="{GREEN_D}"/>
</g>
</svg>'''


def render(svg: str, path: str, size: int) -> None:
    cairosvg.svg2png(bytestring=svg.encode(), write_to=path, output_width=size, output_height=size)


for size, svg in [(1024, SVG_FULL), (512, SVG_FULL), (192, SVG_FULL), (180, SVG_FULL), (64, SVG_FULL)]:
    render(svg, f"{OUT}/logo-{size}.png", size)
for size, svg in [(48, SVG_SIMPLE), (32, SVG_SIMPLE), (16, SVG_SIMPLE)]:
    render(svg, f"{OUT}/logo-{size}.png", size)
render(SVG_MASKABLE, f"{OUT}/logo-maskable-512.png", 512)

for name, svg in [("logo.svg", SVG_FULL), ("logo-simple.svg", SVG_SIMPLE),
                  ("logo-maskable.svg", SVG_MASKABLE)]:
    with open(f"{OUT}/{name}", "w", encoding="utf-8") as f:
        f.write(svg)

render(SVG_FULL, f"{WEB}/icon-192.png", 192)
render(SVG_FULL, f"{WEB}/icon-512.png", 512)
render(SVG_FULL, f"{WEB}/icon-180.png", 180)

print("done:", sorted(os.listdir(OUT)))
