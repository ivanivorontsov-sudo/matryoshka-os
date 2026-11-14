import os, sys
from PIL import Image, ImageDraw

def draw(size):
    k = 8
    s = size * k
    f = s / 128.0
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(30 * f), fill="#e53935")
    pts = [(38, 28), (90, 28), (90, 41), (52, 41), (52, 57), (86, 57), (86, 70), (52, 70), (52, 87), (91, 87), (91, 100), (38, 100)]
    d.polygon([(x * f, y * f) for x, y in pts], fill="#ffffff")
    d.ellipse(((91 - 7) * f, (91 - 7) * f, (91 + 7) * f, (91 + 7) * f), fill="#ffb5b2")
    return im.resize((size, size), Image.LANCZOS)

root = sys.argv[1]
for n in (16, 22, 24, 32, 48, 64, 128, 256):
    p = os.path.join(root, "usr/share/icons/hicolor/%dx%d/apps" % (n, n))
    os.makedirs(p, exist_ok=True)
    draw(n).save(os.path.join(p, "tiho-browser.png"))
c = os.path.join(root, "opt/tiho/firefox/browser/chrome/icons/default")
if os.path.isdir(c):
    for n in (16, 32, 48, 64, 128):
        draw(n).save(os.path.join(c, "default%d.png" % n))
