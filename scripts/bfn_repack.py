"""BFN(GLY1, GX I4) 重打包：把多页字形拼成单页大图集。

平铺是 8x8 块行主序、块内每行 4 字节，偶数 x 取高半字节、奇数 x 取低半字节；重排时必须保持这个顺序。
"""

import struct
import sys
import zlib

BLOCKS = (b"INF1", b"WID1", b"GLY1", b"MAP1")


def untile_i4(data, w, h):
    img = bytearray(w * h)
    bw = w // 8
    p = 0
    for by in range(h // 8):
        for bx in range(bw):
            block = data[p : p + 32]
            p += 32
            for y in range(8):
                row = block[y * 4 : y * 4 + 4]
                for x in range(8):
                    b = row[x // 2]
                    img[(by * 8 + y) * w + bx * 8 + x] = (b >> 4) if x % 2 == 0 else (b & 0xF)
    return img


def tile_i4(img, w, h):
    out = bytearray()
    for by in range(h // 8):
        for bx in range(w // 8):
            for y in range(8):
                row = bytearray(4)
                for x in range(8):
                    nib = img[(by * 8 + y) * w + bx * 8 + x] & 0xF
                    if x % 2 == 0:
                        row[x // 2] |= nib << 4
                    else:
                        row[x // 2] |= nib
                out += row
    return bytes(out)


def parse_bfn(d):
    p = d.find(b"INF1")
    start = p - 0x20
    blocks = []
    off = p
    while off + 8 <= len(d):
        magic = d[off : off + 4]
        size = struct.unpack_from(">I", d, off + 4)[0]
        if magic not in BLOCKS or size < 8:
            break
        blocks.append((magic, off - start, size))
        off += size
    return start, d[start:off], blocks


def gly1_fields(d, off):
    return {
        "startCode": struct.unpack_from(">H", d, off + 8)[0],
        "endCode": struct.unpack_from(">H", d, off + 0xA)[0],
        "cellWidth": struct.unpack_from(">H", d, off + 0xC)[0],
        "cellHeight": struct.unpack_from(">H", d, off + 0xE)[0],
        "textureSize": struct.unpack_from(">I", d, off + 0x10)[0],
        "textureFormat": struct.unpack_from(">H", d, off + 0x14)[0],
        "numRows": struct.unpack_from(">H", d, off + 0x16)[0],
        "numColumns": struct.unpack_from(">H", d, off + 0x18)[0],
        "textureWidth": struct.unpack_from(">H", d, off + 0x1A)[0],
        "textureHeight": struct.unpack_from(">H", d, off + 0x1C)[0],
    }


def write_png(path, img, w, h, scale=1):
    rows = []
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            v = img[y * w + x] * 17
            row += bytes((v, v, v))
        rows.append(bytes(row))
    raw = b"".join(rows)
    if scale != 1:
        return
    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 6))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def main():
    src = sys.argv[1]
    d = open(src, "rb").read()
    start, bfn, blocks = parse_bfn(d)
    print("BFN @%#x size=%d blocks=%s" % (start, len(bfn), [(m.decode(), s) for m, _, s in blocks]))
    hdr = bfn[:0x20]
    print("header magic=%r filesize=%d numBlocks=%d"
          % (hdr[:8], struct.unpack_from(">I", hdr, 8)[0], struct.unpack_from(">I", hdr, 0xC)[0]))

    g = next(b for b in blocks if b[0] == b"GLY1")
    f = gly1_fields(bfn, g[1])
    print("GLY1 %s" % f)
    data = bfn[g[1] + 0x20 : g[1] + g[2]]
    pages = len(data) // f["textureSize"]
    print("pages=%d  (data=%d / pageBytes=%d)" % (pages, len(data), f["textureSize"]))

    tw, th, cw, ch = f["textureWidth"], f["textureHeight"], f["cellWidth"], f["cellHeight"]
    per_page_x = tw // cw
    per_page_y = th // ch
    print("per page grid: %dx%d = %d cells (header says numRows=%d numColumns=%d)"
          % (per_page_x, per_page_y, per_page_x * per_page_y, f["numRows"], f["numColumns"]))

    imgs = [untile_i4(data[p * f["textureSize"] : (p + 1) * f["textureSize"]], tw, th) for p in range(pages)]
    print("untiled %d pages" % len(imgs))

    rt = b"".join(tile_i4(img, tw, th) for img in imgs)
    print("tile round-trip byte-identical: %s" % (rt == data))

    if len(sys.argv) > 2:
        write_png(sys.argv[2], imgs[0], tw, th)
        print("wrote %s" % sys.argv[2])


if __name__ == "__main__":
    main()
