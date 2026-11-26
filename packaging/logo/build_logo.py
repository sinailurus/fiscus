# -*- coding: utf-8 -*-
"""Fiscus logo 生成器（v1.0.0 资产）。
设计：两张层叠的信用卡 + 前卡金色芯片（信用卡符号，呼应应用内卡面元素）
+ 对勾（还款已清）。青绿渐变底（钱袋意象），与 SubDeck 的主题蓝区分。
导出：SVG 源文件 / PNG 全尺寸 / maskable 512。
"""
import os
import cairosvg

OUT = "/home/z/my-project/fiscus/packaging/logo"
WEB = "/home/z/my-project/fiscus/static/icons"
os.makedirs(OUT, exist_ok=True)

GREEN = "#1fa07e"          # Fiscus 主色（钱袋青绿）
GREEN_D = "#137a5f"        # 渐变深端
GOLD_A = "#f3d680"         # 芯片金（与应用内卡面芯片同色）
GOLD_B = "#c9a85c"

# ---------- 主视觉 SVG（1024×1024，图形居中于 maskable 安全区内） ----------
SVG_FULL = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{GREEN}"/>
      <stop offset="1" stop-color="{GREEN_D}"/>
    </linearGradient>
    <linearGradient id="chip" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{GOLD_A}"/>
      <stop offset="1" stop-color="{GOLD_B}"/>
    </linearGradient>
  </defs>
  <rect width="1024" height="1024" rx="228" fill="url(#bg)"/>
  <g transform="rotate(-7 512 512)"><rect x="300" y="244" width="440" height="316" rx="52" fill="#ffffff" opacity="0.30"/></g>
  <g transform="rotate(-3 512 512)"><rect x="278" y="286" width="474" height="336" rx="55" fill="#ffffff" opacity="0.55"/></g>
  <rect x="256" y="336" width="512" height="380" rx="58" fill="#ffffff"/>
  <rect x="310" y="394" width="112" height="84" rx="16" fill="url(#chip)"/>
  <path d="M330 420 l30 0 M330 448 l30 0 M368 402 l0 68" stroke="{GOLD_B}" stroke-width="8"
        stroke-linecap="round" opacity="0.8" fill="none"/>
  <path d="M466 560 l76 76 l196 -210" fill="none" stroke="{GREEN}" stroke-width="46"
        stroke-linecap="round" stroke-linejoin="round"/>
</svg>'''

# ---------- favicon 简化版（≤48px：双层卡 + 芯片色块 + 加粗对勾） ----------
SVG_SIMPLE = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{GREEN}"/>
      <stop offset="1" stop-color="{GREEN_D}"/>
    </linearGradient>
    <linearGradient id="chip" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{GOLD_A}"/>
      <stop offset="1" stop-color="{GOLD_B}"/>
    </linearGradient>
  </defs>
  <rect width="1024" height="1024" rx="228" fill="url(#bg)"/>
  <g transform="rotate(-6 512 512)"><rect x="296" y="268" width="440" height="392" rx="56" fill="#ffffff" opacity="0.42"/></g>
  <rect x="248" y="316" width="528" height="420" rx="60" fill="#ffffff"/>
  <rect x="300" y="374" width="118" height="90" rx="18" fill="url(#chip)"/>
  <path d="M472 556 l86 86 l188 -204" fill="none" stroke="{GREEN}" stroke-width="60"
        stroke-linecap="round" stroke-linejoin="round"/>
</svg>'''

# ---------- maskable（图形收缩进安全区，四边留 12% 空白） ----------
SVG_MASKABLE = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
  <rect width="1024" height="1024" fill="{GREEN}"/>
  <defs>
    <linearGradient id="chip" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{GOLD_A}"/>
      <stop offset="1" stop-color="{GOLD_B}"/>
    </linearGradient>
  </defs>
  <g transform="translate(512 512) scale(0.72) translate(-512 -512)">
    <g transform="rotate(-7 512 512)"><rect x="300" y="244" width="440" height="316" rx="52" fill="#ffffff" opacity="0.30"/></g>
    <g transform="rotate(-3 512 512)"><rect x="278" y="286" width="474" height="336" rx="55" fill="#ffffff" opacity="0.55"/></g>
    <rect x="256" y="336" width="512" height="380" rx="58" fill="#ffffff"/>
    <rect x="310" y="394" width="112" height="84" rx="16" fill="url(#chip)"/>
    <path d="M470 566 l78 78 l206 -222" fill="none" stroke="{GREEN}" stroke-width="46"
          stroke-linecap="round" stroke-linejoin="round"/>
  </g>
</svg>'''


def render(svg: str, path: str, size: int) -> None:
    cairosvg.svg2png(bytestring=svg.encode(), write_to=path, output_width=size, output_height=size)


# 网页/通用 PNG
for size, svg in [(1024, SVG_FULL), (512, SVG_FULL), (192, SVG_FULL), (180, SVG_FULL), (64, SVG_FULL)]:
    render(svg, f"{OUT}/logo-{size}.png", size)
for size, svg in [(48, SVG_SIMPLE), (32, SVG_SIMPLE), (16, SVG_SIMPLE)]:
    render(svg, f"{OUT}/logo-{size}.png", size)
render(SVG_MASKABLE, f"{OUT}/logo-maskable-512.png", 512)

# SVG 源文件
for name, svg in [("logo.svg", SVG_FULL), ("logo-simple.svg", SVG_SIMPLE),
                  ("logo-maskable.svg", SVG_MASKABLE)]:
    with open(f"{OUT}/{name}", "w", encoding="utf-8") as f:
        f.write(svg)

# 网页图标（favicon / PWA）
render(SVG_FULL, f"{WEB}/icon-192.png", 192)
render(SVG_FULL, f"{WEB}/icon-512.png", 512)
render(SVG_FULL, f"{WEB}/icon-180.png", 180)

print("done:", sorted(os.listdir(OUT)))
