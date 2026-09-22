"""字库单页重打包：把多页字形拼成一张大图集，并把它写回 RARC（`MAP1` 的字形索引不动）。

单页是硬要求：引擎按 `GLY1` 的 rows × cols 推页数再拼成一张纹理，页数多了拼合高度超纹理上限。
"""

import struct

import bfn_repack as R

ROW_CELLS = 64
COL_CELLS = 42


def repack_bfn(bfn):
    start, body, blocks = R.parse_bfn(bfn)
    assert start == 0 and len(body) == len(bfn)
    g = next(b for b in blocks if b[0] == b"GLY1")
    f = R.gly1_fields(body, g[1])
    tw, th = f["textureWidth"], f["textureHeight"]
    cw, ch = f["cellWidth"], f["cellHeight"]
    per_x, per_y = tw // cw, th // ch
    codes = f["endCode"] - f["startCode"]
    gdata = body[g[1] + 0x20 : g[1] + g[2]]
    pages = len(gdata) // f["textureSize"]
    print("  source: %d pages, grid %dx%d, %d codes" % (pages, per_x, per_y, codes))

    imgs = [R.untile_i4(gdata[p * f["textureSize"] : (p + 1) * f["textureSize"]], tw, th)
            for p in range(pages)]
    assert R.tile_i4(imgs[0], tw, th) == gdata[: f["textureSize"]]

    nw, nh = ROW_CELLS * cw, COL_CELLS * ch
    assert ROW_CELLS * COL_CELLS >= codes
    assert nw <= 16384 and nh <= 16384
    atlas = bytearray(nw * nh)
    for gidx in range(codes):
        p, j = divmod(gidx, per_x * per_y)
        sx, sy = (j % per_y) * cw, (j // per_y) * ch
        dx, dy = (gidx % ROW_CELLS) * cw, (gidx // ROW_CELLS) * ch
        for y in range(ch):
            src = (sy + y) * tw + sx
            dst = (dy + y) * nw + dx
            atlas[dst : dst + cw] = imgs[p][src : src + cw]

    for gidx in range(codes):
        p, j = divmod(gidx, per_x * per_y)
        sx, sy = (j % per_y) * cw, (j // per_y) * ch
        dx, dy = (gidx % ROW_CELLS) * cw, (gidx // ROW_CELLS) * ch
        for y in range(ch):
            a = atlas[(dy + y) * nw + dx : (dy + y) * nw + dx + cw]
            assert a == imgs[p][(sy + y) * tw + sx : (sy + y) * tw + sx + cw]
    print("  verified: every glyph bitmap moved intact")

    new_data = R.tile_i4(atlas, nw, nh)
    assert len(new_data) == nw * nh // 2

    new_header = bytearray(body[g[1] : g[1] + 0x20])
    struct.pack_into(">I", new_header, 0x10, len(new_data))
    struct.pack_into(">H", new_header, 0x16, ROW_CELLS)
    struct.pack_into(">H", new_header, 0x18, COL_CELLS)
    struct.pack_into(">H", new_header, 0x1A, nw)
    struct.pack_into(">H", new_header, 0x1C, nh)
    struct.pack_into(">I", new_header, 0x04, 0x20 + len(new_data))
    new_gly1 = bytes(new_header) + new_data

    out = bytearray(body[:0x20])
    out += body[0x20 : g[1]]
    out += new_gly1
    out += body[g[1] + g[2] :]
    struct.pack_into(">I", out, 0x08, len(out))
    print("  new: GLY1 %dx%d grid, texture %dx%d, bytes=%d (was %d)"
          % (ROW_CELLS, COL_CELLS, nw, nh, len(new_gly1), g[2]))
    return bytes(out)


def patch_rarc(arc, bfn_off, new_bfn):
    """把新 BFN 写进 RARC：BFF 文件表里的 dataSize 跟着改，尾部多余字节清零。"""
    hdr = struct.unpack_from(">I", arc, 8)[0]
    num_files = struct.unpack_from(">I", arc, hdr + 0x08)[0]
    file_off = hdr + struct.unpack_from(">I", arc, hdr + 0x0C)[0]
    out = bytearray(arc)
    out[bfn_off : bfn_off + len(new_bfn)] = new_bfn
    for i in range(num_files):
        o = file_off + i * 0x14
        if struct.unpack_from(">H", out, o + 4)[0] == 0x1100:
            old = struct.unpack_from(">I", out, o + 0x0C)[0]
            struct.pack_into(">I", out, o + 0x0C, len(new_bfn))
            print("  file entry %d: dataSize %d -> %d" % (i, old, len(new_bfn)))
    for i in range(bfn_off + len(new_bfn), len(out)):
        out[i] = 0
    return bytes(out)
