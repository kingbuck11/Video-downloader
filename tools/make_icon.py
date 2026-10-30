"""Draws the app icon (orange rounded square, white download arrow).
Writes static/icon-512.png (Dock icon at runtime) and tools/AppIcon.icns.
Run:  python3 tools/make_icon.py   (needs Pillow)"""
import os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 1024


def draw():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = 100                                   # macOS icon grid: art inside ~824px
    d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=185, fill=(232, 87, 42, 255))
    d = ImageDraw.Draw(img)
    w, white, cx = 64, (255, 255, 255, 255), S // 2
    d.line([(cx, 290), (cx, 610)], fill=white, width=w)                       # shaft
    d.line([(cx - 165, 455), (cx, 620), (cx + 165, 455)], fill=white, width=w, joint="curve")  # head
    for x, y in [(cx, 290), (cx - 165, 455), (cx + 165, 455), (cx, 620)]:
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=white)   # round caps
    d.line([(cx - 215, 735), (cx + 215, 735)], fill=white, width=w)          # tray
    for x in (cx - 215, cx + 215):
        d.ellipse([x - w / 2, 735 - w / 2, x + w / 2, 735 + w / 2], fill=white)
    return img


if __name__ == "__main__":
    icon = draw()
    icon.resize((512, 512), Image.LANCZOS).save(os.path.join(ROOT, "static", "icon-512.png"))
    icon.save(os.path.join(ROOT, "tools", "AppIcon.icns"),
              sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)])
    print("icons written")
