"""Yaz0 编解码。

`decompress` 支持完整格式（含回引）；`encode` 只写字面量，够用且实现最短。
"""

import struct


def decompress(src):
    if src[:4] != b"Yaz0":
        raise ValueError("not Yaz0")
    out_size = int.from_bytes(src[4:8], "big")
    p = 16
    out = bytearray()
    while len(out) < out_size and p < len(src):
        code = src[p]
        p += 1
        for bit in range(7, -1, -1):
            if len(out) >= out_size:
                break
            if code & (1 << bit):
                if p >= len(src):
                    break
                out.append(src[p])
                p += 1
                continue
            if p + 1 >= len(src):
                break
            b1 = src[p]
            b2 = src[p + 1]
            p += 2
            count = b1 >> 4
            dist = ((b1 & 0x0F) << 8) | b2
            if count == 0:
                if p >= len(src):
                    break
                count = src[p] + 0x12
                p += 1
            else:
                count += 2
            start = len(out) - (dist + 1)
            if start < 0:
                raise ValueError("bad backref at %d" % len(out))
            for k in range(count):
                out.append(out[start + k])
    return bytes(out[:out_size])


def encode(data):
    """只写字面量的 Yaz0 编码：8 字节一组、每组的 code 位全 1。

    不做回引，压出来的文件比标准编码器大，但实现只有几行且必然可被 decompress 还原。
    """
    out = bytearray(b"Yaz0")
    out += struct.pack(">I", len(data))
    out += b"\x00" * 8
    p = 0
    while p < len(data):
        n = min(8, len(data) - p)
        code = 0
        for i in range(8):
            if i < n:
                code |= 1 << (7 - i)
        out.append(code)
        out += data[p : p + n]
        p += n
    return bytes(out)
