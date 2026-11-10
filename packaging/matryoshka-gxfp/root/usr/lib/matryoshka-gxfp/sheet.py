import glob
import os
import struct
import sys
import zlib


def readpgm(path):
    data = open(path, "rb").read()
    parts = []
    pos = 0
    while len(parts) < 4:
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            pos = data.index(b"\n", pos) + 1
            continue
        end = pos
        while not data[end:end + 1].isspace():
            end += 1
        parts.append(data[pos:end])
        pos = end
    pos += 1
    w, h, mx = int(parts[1]), int(parts[2]), int(parts[3])
    if mx > 255:
        px = list(struct.unpack(">%dH" % (w * h), data[pos:pos + 2 * w * h]))
    else:
        px = list(data[pos:pos + w * h])
    return w, h, px


def norm(px):
    s = sorted(px)
    lo, hi = s[len(s) // 100], s[-1 - len(s) // 100]
    hi = max(hi, lo + 1)
    return [max(0, min(255, (v - lo) * 255 // (hi - lo))) for v in px]


def relayout(w, h, px):
    return [px[(i % h) * w + i // h] for i in range(w * h)]


def png(path, w, h, rows):
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "/var/lib/fprint/gxfp-dump"
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/gxfp-sheet.png"
    files = sorted(glob.glob(os.path.join(src, "*-raw16.pgm")))[-24:]
    if not files:
        files = sorted(glob.glob(os.path.join(src, "*.pgm")))[-24:]
    if not files:
        print("Нет снимков в", src)
        return 1
    z, gap, per = 3, 6, 6
    tiles = []
    for f in files:
        w, h, px = readpgm(f)
        tiles.append((w, h, norm(px), norm(relayout(w, h, px))))
    w, h = tiles[0][0], tiles[0][1]
    tw, th = (2 * w * z + gap), h * z
    cols = per
    nrows = (len(tiles) + cols - 1) // cols
    W, H = cols * (tw + 2 * gap), nrows * (th + gap)
    img = [[40] * W for _ in range(H)]
    for k, (tw0, th0, a, b) in enumerate(tiles):
        ox, oy = (k % cols) * (tw + 2 * gap), (k // cols) * (th + gap)
        for y in range(h * z):
            ry = img[oy + y]
            for x in range(w * z):
                ry[ox + x] = a[(y // z) * w + x // z]
                ry[ox + w * z + gap + x] = b[(y // z) * w + x // z]
    png(out, W, H, img)
    with open(out + ".txt", "w") as t:
        for k, f in enumerate(files):
            t.write("%d %s\n" % (k + 1, os.path.basename(f)))
    print(out)
    return 0


sys.exit(main())
