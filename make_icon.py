# -*- coding: utf-8 -*-
"""生成水文监测主题图标 app.ico（水滴 + 水位波形，蓝色系）"""
import os
from PIL import Image, ImageDraw

SIZE = 512
ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]

# 配色（水文/水利主题）
BG_TOP = (11, 95, 165)       # 深蓝
BG_BOTTOM = (30, 136, 229)   # 亮蓝
DROP = (255, 255, 255)       # 水滴主体
DROP_EDGE = (187, 222, 251)  # 水滴描边
WAVE = (120, 190, 250)       # 波形


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def make_icon(size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size
    pad = s * 0.06

    # 圆角方形背景（垂直渐变）
    r = s * 0.22
    bg = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    bgd = ImageDraw.Draw(bg)
    for y in range(s):
        t = y / max(s - 1, 1)
        color = lerp(BG_TOP, BG_BOTTOM, t) + (255,)
        bgd.line([(0, y), (s, y)], fill=color)
    mask = Image.new('L', (s, s), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([pad, pad, s - pad, s - pad], radius=r, fill=255)
    img.paste(bg, (0, 0), mask)

    # 水滴主体（中心偏上）
    cx = s * 0.5
    top_y = s * 0.24
    bottom_y = s * 0.76
    w = s * 0.36
    drop = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    dd = ImageDraw.Draw(drop)
    # 使用椭圆堆叠近似水滴：顶部圆 + 底部圆 + 两侧切线
    dd.ellipse([cx - w / 2, top_y, cx + w / 2, bottom_y], fill=DROP)
    dd.ellipse([cx - w / 2, top_y - w * 0.28, cx + w / 2, top_y + w * 0.28], fill=DROP)
    # 修剪成水滴尖角：把顶部多余的去掉——改为用多边形覆盖成水滴形
    drop = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    dd = ImageDraw.Draw(drop)
    # 水滴轮廓：尖顶 + 两侧曲线 + 圆底（用多边形+椭圆组合）
    tip_x, tip_y = cx, top_y - w * 0.10
    dd.ellipse([cx - w * 0.62, top_y, cx + w * 0.62, bottom_y + w * 0.10], fill=DROP)
    dd.polygon([
        (tip_x, tip_y),
        (cx - w * 0.30, top_y + w * 0.42),
        (cx + w * 0.30, top_y + w * 0.42),
    ], fill=DROP)
    # 底部更圆润
    dd.ellipse([cx - w * 0.55, bottom_y - w * 0.30, cx + w * 0.55, bottom_y + w * 0.18], fill=DROP)
    img.alpha_composite(drop)

    # 水滴内高光（左上小椭圆）
    glint = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glint)
    gd.ellipse([cx - w * 0.34, top_y + w * 0.10, cx - w * 0.06, top_y + w * 0.42],
               fill=(255, 255, 255, 170))
    img.alpha_composite(glint)

    # 底部水位波形（三条横波纹）
    wave = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wave)
    for i, y_base in enumerate([s * 0.80, s * 0.87, s * 0.93]):
        alpha = 235 - i * 55
        wd.arc([s * 0.10, y_base - s * 0.05, s * 0.55, y_base + s * 0.05],
               0, 180, fill=WAVE + (alpha,), width=max(2, int(s * 0.028)))
        wd.arc([s * 0.45, y_base - s * 0.05, s * 0.90, y_base + s * 0.05],
               0, 180, fill=WAVE + (alpha,), width=max(2, int(s * 0.028)))
    img.alpha_composite(wave)

    return img


def main():
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.ico')
    base = make_icon(SIZE)
    base.save(out_path, format='ICO', sizes=[(x, x) for x in ICON_SIZES])
    print(f'ICO 图标已生成: {out_path}')
    print(f'包含尺寸: {ICON_SIZES}')


if __name__ == '__main__':
    main()
