"""开源字体渲染字库字形位图（Windows GDI+ / ctypes，零第三方依赖）。

用途：
  1. 作库被 patch_sjis_font.py 调用：--glyph-source open 时渲染 GLY1 全部像素；
  2. 独立运行做标定/试印：

     python scripts/font_render.py --font fontres --ttf work/fonts/NotoSansCJKsc-Regular.otf \
         --em 46 --png work/fonts/render_fontres.png

原理（与字库的接口约定）：
  - 名册 = 原字库 MAP1 逆映射：method-3 的 {码位: 字形索引} 取逆（码位即 Unicode），
    method-0 区间按 idx = 码位 - startCode 展开（ASCII 槽 idx 0x20..0x7F -> 0..95）；
  - 每个字形槽渲染成一格 cell（48x48）：GDI+ 路径（AddPathString -> bounds -> 平移 -> FillPath），
    4x 超采样后盒式降采样，gamma 后量化为 I4（0..15，高值 = 墨）；
  - 摆放：inherit 模式把新字形墨迹中心对准原字形墨迹中心（继承原版排版），
    无原墨迹（新补槽）或 center 模式则对准格中心。

平台门禁：渲染需要 Windows（GDI+ 在系统 gdiplus.dll 里）；本工具是维护者侧的资产生成，
不进游戏运行链路。
"""

import ctypes
import json
import os
import struct
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import bfn_repack as R
import paths
import yaz0

DEFAULT_EM = 46.0
DEFAULT_GAMMA = 0.9
DEFAULT_SUPER = 4
DEFAULT_BASELINE = 42


# ---------------------------------------------------------------- sfnt / cmap

def _sfnt_tables(data):
    num = struct.unpack_from(">H", data, 4)[0]
    tables = {}
    for i in range(num):
        off = 12 + i * 16
        tag = data[off : off + 4]
        toff, tlen = struct.unpack_from(">II", data, off + 8)
        tables[tag] = (toff, tlen)
    return tables


def _cmap4(data, off):
    """yield (码位, 字形号)：format 4（BMP 段表）。"""
    seg2 = struct.unpack_from(">H", data, off + 6)[0]
    seg = seg2 // 2
    ends = struct.unpack_from(">%dH" % seg, data, off + 14)
    starts = struct.unpack_from(">%dH" % seg, data, off + 16 + seg2)
    deltas = struct.unpack_from(">%dh" % seg, data, off + 16 + 2 * seg2)
    ro_base = off + 16 + 3 * seg2
    rngs = struct.unpack_from(">%dH" % seg, data, ro_base)
    for i in range(seg):
        if starts[i] == 0xFFFF and ends[i] == 0xFFFF:
            continue
        for c in range(starts[i], min(ends[i], 0xFFFE) + 1):
            if rngs[i] == 0:
                g = (c + deltas[i]) & 0xFFFF
            else:
                p = ro_base + 2 * i + rngs[i] + 2 * (c - starts[i])
                if p + 2 > len(data):
                    continue
                g = struct.unpack_from(">H", data, p)[0]
                if g:
                    g = (g + deltas[i]) & 0xFFFF
            if g:
                yield c, g


def _cmap12(data, off):
    """yield (码位, 字形号)：format 12（UCS-4 分组）。"""
    n = struct.unpack_from(">I", data, off + 12)[0]
    for k in range(n):
        s, e, g = struct.unpack_from(">III", data, off + 16 + k * 12)
        if g == 0:
            continue
        for c in range(s, e + 1):
            yield c, g


def _cmap_pairs(path):
    """[(码位, 字形号)]：全部 format 4 子表 + 第一张 format 12 子表。"""
    with open(path, "rb") as f:
        data = f.read()
    tables = _sfnt_tables(data)
    if b"cmap" not in tables:
        raise ValueError("no cmap table: %s" % path)
    coff = tables[b"cmap"][0]
    num = struct.unpack_from(">H", data, coff + 2)[0]
    out = []
    seen12 = False
    for i in range(num):
        platform, enc, sub = struct.unpack_from(">HHI", data, coff + 4 + i * 8)
        off = coff + sub
        fmt = struct.unpack_from(">H", data, off)[0]
        if fmt == 12 and not seen12:
            out += list(_cmap12(data, off))
            seen12 = True
        elif fmt == 4:
            out += list(_cmap4(data, off))
    return out


def parse_cmap(path):
    """解析 TTF/OTF 的 cmap（format 4/12），返回有字形的码位集合。"""
    return {cp for cp, _ in _cmap_pairs(path)}


def read_advances(path):
    """{码位: 前进宽度}：hmtx / unitsPerEm，以 em 为单位。"""
    with open(path, "rb") as f:
        data = f.read()
    tables = _sfnt_tables(data)
    for tag in (b"head", b"hhea", b"hmtx"):
        if tag not in tables:
            raise ValueError("缺 %s 表：%s" % (tag.decode(), path))
    upem = struct.unpack_from(">H", data, tables[b"head"][0] + 18)[0]
    num_h = struct.unpack_from(">H", data, tables[b"hhea"][0] + 34)[0]
    hmtx = tables[b"hmtx"][0]

    def advance(gid):
        off = hmtx + (min(gid, num_h - 1) if num_h else 0) * 4
        return struct.unpack_from(">H", data, off)[0] if off + 2 <= len(data) else upem

    if not upem:
        return {}
    return {cp: advance(gid) / float(upem) for cp, gid in _cmap_pairs(path)}


# ---------------------------------------------------------------- 名册 / 覆盖

def read_map(bfn):
    """从（单页或多页）BFN 读 MAP1：返回 (entries dict code->idx, method-0 区间列表)。"""
    _, body, blocks = R.parse_bfn(bfn)
    entries = {}
    m0 = []
    for magic, off, size in blocks:
        if magic != b"MAP1":
            continue
        method, sc, ec, n = struct.unpack_from(">HHHH", body, off + 8)
        if method == 0:
            m0.append((sc, ec))
        elif method == 3:
            for k in range(n):
                code, idx = struct.unpack_from(">HH", body, off + 0x10 + k * 4)
                entries[code] = idx
    return entries, m0


def read_inf1(bfn):
    """读 INF1 度量：fontType / ascent / descent / width / leading。"""
    _, body, blocks = R.parse_bfn(bfn)
    for magic, off, size in blocks:
        if magic == b"INF1":
            vals = struct.unpack_from(">HHHHH", body, off + 8)
            return dict(zip(("fontType", "ascent", "descent", "width", "leading"), vals))
    return None


def build_roster(entries, m0_ranges):
    """名册：{字形槽 idx: 字符}。method-3 取逆 + method-0 恒等展开。"""
    roster = {}
    trouble = []
    for code, idx in entries.items():
        ch = chr(code)
        if idx in roster and roster[idx] != ch:
            trouble.append((idx, roster[idx], ch))
        roster[idx] = ch
    for sc, ec in m0_ranges:
        for c in range(sc, ec + 1):
            idx = c - sc
            ch = chr(c)
            if idx in roster and roster[idx] != ch:
                trouble.append((idx, roster[idx], ch))
            roster[idx] = ch
    return roster, trouble


def check_coverage(cmap, roster):
    """名册里字体缺哪些字符：返回 [(idx, ch, 码位)]。控制字符不参与（不绘制）。"""
    missing = []
    for idx, ch in sorted(roster.items()):
        cp = ord(ch)
        if cp < 0x20 or cp == 0x7F:
            continue
        if cp not in cmap:
            missing.append((idx, ch, cp))
    return missing


# ---------------------------------------------------------------- 原字形扫描

def scan_bboxes(bfn, idxes=None):
    """扫描原字库墨迹 bbox：返回 ({idx: (x0, y0, x1, y1)}, 直方图)。
    bbox 为格内坐标、x1/y1 为开区间；只收集有墨迹的槽。"""
    _, body, blocks = R.parse_bfn(bfn)
    g = next(b for b in blocks if b[0] == b"GLY1")
    f = R.gly1_fields(body, g[1])
    tw, th = f["textureWidth"], f["textureHeight"]
    cw, ch = f["cellWidth"], f["cellHeight"]
    rows, cols = f["numRows"], f["numColumns"]
    per_page = rows * cols
    data = body[g[1] + 0x20 : g[1] + g[2]]
    pages = len(data) // f["textureSize"]
    total = f["endCode"] - f["startCode"]
    if idxes is None:
        idxes = range(total)
    box = {}
    hist = [0] * 16
    for p in range(pages):
        img = R.untile_i4(data[p * f["textureSize"] : (p + 1) * f["textureSize"]], tw, th)
        for v in img:
            hist[v & 0xF] += 1
        for gidx in idxes:
            if gidx < p * per_page or gidx >= (p + 1) * per_page:
                continue
            j = gidx - p * per_page
            sx, sy = (j % rows) * cw, (j // rows) * ch
            x0, y0, x1, y1 = cw, ch, 0, 0
            for y in range(ch):
                base = (sy + y) * tw + sx
                row = img[base : base + cw]
                if not any(row):
                    continue
                if y < y0:
                    y0 = y
                y1 = y + 1
                for x in range(cw):
                    if row[x]:
                        if x < x0:
                            x0 = x
                        if x >= x1:
                            x1 = x + 1
            if x1 > x0:
                box[gidx] = (x0, y0, x1, y1)
    return box, hist


# ---------------------------------------------------------------- GDI+ 渲染

_PF32 = 0x26200A  # PixelFormat32bppARGB
_LOCK_READ = 1
_SMOOTH_AA = 4
_FILL_WINDING = 1


class Renderer:
    """GDI+ 单字渲染器：私有字体集 + 复用画布。

    cell 与 super 决定画布尺寸（默认 48*4=192）；render() 返回 48x48 灰度。
    """

    def __init__(self, ttf, cell=48, super=DEFAULT_SUPER):
        if sys.platform != "win32":
            raise RuntimeError("font_render 渲染需要 Windows（GDI+）")
        self.ttf = ttf
        self.cell = cell
        self.super = super
        self.px = cell * super
        lib = ctypes.WinDLL("gdiplus")
        self._lib = lib

        class StartupInput(ctypes.Structure):
            _fields_ = [("GdiplusVersion", ctypes.c_uint32),
                        ("DebugEventCallback", ctypes.c_void_p),
                        ("SuppressBackgroundThread", ctypes.c_int),
                        ("SuppressExternalCodecs", ctypes.c_int)]

        self._StartupInput = StartupInput
        lib.GdiplusStartup.argtypes = [ctypes.POINTER(ctypes.c_void_p),
                                       ctypes.POINTER(StartupInput), ctypes.c_void_p]
        lib.GdiplusStartup.restype = ctypes.c_int
        lib.GdiplusShutdown.argtypes = [ctypes.c_void_p]
        for name, args in (
            ("GdipNewPrivateFontCollection", [ctypes.POINTER(ctypes.c_void_p)]),
            ("GdipPrivateAddFontFile", [ctypes.c_void_p, ctypes.c_wchar_p]),
            ("GdipGetFontCollectionFamilyCount", [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]),
            ("GdipGetFontCollectionFamilyList", [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_int)]),
            ("GdipGetFamilyName", [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ushort]),
            ("GdipDeletePrivateFontCollection", [ctypes.POINTER(ctypes.c_void_p)]),
        ):
            fn = getattr(lib, name)
            fn.argtypes = args
            fn.restype = ctypes.c_int
        lib.GdiplusShutdown.restype = None

        token = ctypes.c_void_p()
        si = StartupInput(1, None, 0, 0)
        st = lib.GdiplusStartup(ctypes.byref(token), ctypes.byref(si), None)
        if st != 0:
            raise RuntimeError("GdiplusStartup failed: %d" % st)
        self._token = token

        coll = ctypes.c_void_p()
        if lib.GdipNewPrivateFontCollection(ctypes.byref(coll)) != 0:
            raise RuntimeError("GdipNewPrivateFontCollection failed")
        self._coll = coll
        st = lib.GdipPrivateAddFontFile(coll, ttf)
        if st != 0:
            raise RuntimeError("GdipPrivateAddFontFile failed: %d （%s）" % (st, ttf))
        n = ctypes.c_int()
        lib.GdipGetFontCollectionFamilyCount(coll, ctypes.byref(n))
        if n.value < 1:
            raise RuntimeError("字体未加载出任何 family（CFF/OTF 不受支持？）：%s" % ttf)
        fams = (ctypes.c_void_p * n.value)()
        got = ctypes.c_int()
        lib.GdipGetFontCollectionFamilyList(coll, n.value, fams, ctypes.byref(got))
        self._families = fams
        buf = ctypes.create_unicode_buffer(64)
        lib.GdipGetFamilyName(fams[0], buf, 0)
        self.family_name = buf.value

        class RectF(ctypes.Structure):
            _fields_ = [("X", ctypes.c_float), ("Y", ctypes.c_float),
                        ("Width", ctypes.c_float), ("Height", ctypes.c_float)]

        class Rect(ctypes.Structure):
            _fields_ = [("X", ctypes.c_int), ("Y", ctypes.c_int),
                        ("Width", ctypes.c_int), ("Height", ctypes.c_int)]

        class BmpData(ctypes.Structure):
            _fields_ = [("Width", ctypes.c_uint32), ("Height", ctypes.c_uint32),
                        ("Stride", ctypes.c_int), ("PixelFormat", ctypes.c_int),
                        ("Scan0", ctypes.c_void_p), ("Reserved", ctypes.c_void_p)]

        self._RectF = RectF
        self._Rect = Rect
        self._BmpData = BmpData

        for name, args in (
            ("GdipCreatePath", [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]),
            ("GdipResetPath", [ctypes.c_void_p]),
            ("GdipDeletePath", [ctypes.c_void_p]),
            ("GdipAddPathString", [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_float, ctypes.POINTER(RectF), ctypes.c_void_p]),
            ("GdipGetPathWorldBounds", [ctypes.c_void_p, ctypes.POINTER(RectF), ctypes.c_void_p, ctypes.c_void_p]),
            ("GdipCreateMatrix", [ctypes.POINTER(ctypes.c_void_p)]),
            ("GdipSetMatrixElements", [ctypes.c_void_p] + [ctypes.c_float] * 6),
            ("GdipTranslateMatrix", [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_int]),
            ("GdipTransformPath", [ctypes.c_void_p, ctypes.c_void_p]),
            ("GdipDeleteMatrix", [ctypes.c_void_p]),
            ("GdipCreateBitmapFromScan0", [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]),
            ("GdipGetImageGraphicsContext", [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]),
            ("GdipSetSmoothingMode", [ctypes.c_void_p, ctypes.c_int]),
            ("GdipGraphicsClear", [ctypes.c_void_p, ctypes.c_uint32]),
            ("GdipCreateSolidFill", [ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]),
            ("GdipFillPath", [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]),
            ("GdipBitmapLockBits", [ctypes.c_void_p, ctypes.POINTER(Rect), ctypes.c_uint32, ctypes.c_int, ctypes.POINTER(BmpData)]),
            ("GdipBitmapUnlockBits", [ctypes.c_void_p, ctypes.POINTER(BmpData)]),
            ("GdipDisposeImage", [ctypes.c_void_p]),
            ("GdipDeleteGraphics", [ctypes.c_void_p]),
            ("GdipDeleteBrush", [ctypes.c_void_p]),
        ):
            fn = getattr(lib, name)
            fn.argtypes = args
            fn.restype = ctypes.c_int

        self._path = ctypes.c_void_p()
        self._measure_path = ctypes.c_void_p()
        self._matrix = ctypes.c_void_p()
        self._bmp = ctypes.c_void_p()
        self._g = ctypes.c_void_p()
        self._brush = ctypes.c_void_p()
        if lib.GdipCreatePath(_FILL_WINDING, ctypes.byref(self._path)) != 0:
            raise RuntimeError("GdipCreatePath failed")
        if lib.GdipCreatePath(_FILL_WINDING, ctypes.byref(self._measure_path)) != 0:
            raise RuntimeError("GdipCreatePath failed")
        lib.GdipCreateMatrix(ctypes.byref(self._matrix))
        lib.GdipCreateBitmapFromScan0(self.px, self.px, 0, _PF32, None, ctypes.byref(self._bmp))
        lib.GdipGetImageGraphicsContext(self._bmp, ctypes.byref(self._g))
        lib.GdipSetSmoothingMode(self._g, _SMOOTH_AA)
        lib.GdipCreateSolidFill(0xFFFFFFFF, ctypes.byref(self._brush))
        self._baseline_cache = {}
        self._closed = False

    def _ink_bottom(self, ch, em_draw):
        """字形墨迹底边在布局坐标里的 y（只算路径包围盒，不栅格化）。

        用单独的测量 path：render() 先建好要画的字形路径再算基线，
        两者共用一条 path 会把待画的字形换掉（量基线时往里塞 H/E/T）。
        """
        lib = self._lib
        lib.GdipResetPath(self._measure_path)
        rect = self._RectF(-em_draw, -em_draw, em_draw * 4, em_draw * 4)
        st = lib.GdipAddPathString(self._measure_path, ch, 1, self._families[0], 0, em_draw,
                                   ctypes.byref(rect), None)
        if st != 0:
            raise RuntimeError("GdipAddPathString failed %d: %r" % (st, ch))
        b = self._RectF()
        lib.GdipGetPathWorldBounds(self._measure_path, ctypes.byref(b), None, None)
        return b.Y + b.Height

    def baseline_in_path(self, em):
        """基线在布局坐标里的 y：带方格的字（H E T）底边就落在基线上。

        anchor="baseline" 时用它把字形的基线（而不是墨迹底边）对到目标 y——
        墨迹底边对齐会把「一」这种单横画压到基线上，看起来像下划线。
        """
        em_draw = em * self.super
        if em_draw not in self._baseline_cache:
            y = None
            for ref in "HET":
                b = self._ink_bottom(ref, em_draw)
                if b:
                    y = b
                    break
            if y is None:
                raise RuntimeError("量不到基线：字体里没有 H/E/T")
            self._baseline_cache[em_draw] = y
        return self._baseline_cache[em_draw] / self.super

    def render(self, ch, em, center=None, anchor="center"):
        """渲染单字到 cell 格。

        em: 48 尺度下的字号像素；center: (cx, cy) 目标锚点（48 尺度），
        anchor=center 时 cy 为墨迹中心、bottom 时 cy 为墨迹底边、baseline 时 cy 为基线；
        默认格中心。返回 (48x48 灰度 bytearray, clipped bool)。"""
        lib = self._lib
        cell, super, px = self.cell, self.super, self.px
        if center is None:
            center = (cell / 2.0, cell / 2.0)
        tcx, tcy = center[0] * super, center[1] * super

        lib.GdipResetPath(self._path)
        em_draw = em * super
        rect = self._RectF(-em_draw, -em_draw, em_draw * 4, em_draw * 4)
        st = lib.GdipAddPathString(self._path, ch, 1, self._families[0], 0,
                                   em_draw, ctypes.byref(rect), None)
        if st != 0:
            raise RuntimeError("GdipAddPathString failed %d: %r" % (st, ch))
        bounds = self._RectF()
        lib.GdipGetPathWorldBounds(self._path, ctypes.byref(bounds), None, None)
        dx = tcx - (bounds.X + bounds.Width / 2.0)
        if anchor == "baseline":
            dy = tcy - self.baseline_in_path(em) * super
        elif anchor == "bottom":
            dy = tcy - (bounds.Y + bounds.Height)
        else:
            dy = tcy - (bounds.Y + bounds.Height / 2.0)
        clipped = (bounds.X + dx < -super or bounds.Y + dy < -super
                   or bounds.X + bounds.Width + dx > px + super
                   or bounds.Y + bounds.Height + dy > px + super)
        self.last_info = {"ch": ch, "bounds": (bounds.X, bounds.Y, bounds.Width, bounds.Height),
                          "dx": dx, "dy": dy, "center": center, "clipped": clipped}
        lib.GdipSetMatrixElements(self._matrix, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        lib.GdipTranslateMatrix(self._matrix, dx, dy, 0)
        lib.GdipTransformPath(self._path, self._matrix)

        lib.GdipGraphicsClear(self._g, 0)
        lib.GdipFillPath(self._g, self._brush, self._path)

        bd = self._BmpData()
        rc = self._Rect(0, 0, px, px)
        lib.GdipBitmapLockBits(self._bmp, ctypes.byref(rc), _LOCK_READ, _PF32, ctypes.byref(bd))
        raw = ctypes.string_at(bd.Scan0, bd.Stride * px)
        lib.GdipBitmapUnlockBits(self._bmp, ctypes.byref(bd))

        # raw 是 ARGB 字节流：像素 (row, col) 的 alpha 在 row*Stride + col*4 + 3。
        # 超采样 super x super 盒式平均——按字节偏移取样（Stride 可能含行填充，
        # 不能拿字节偏移当下标去索引 raw[3::4] 那种已压缩成像素下标的副本）。
        stride = bd.Stride
        step = super * 4
        out = bytearray(cell * cell)
        for y in range(cell):
            base = y * super * stride
            o = y * cell
            for x in range(cell):
                b = base + x * step
                s = 0
                for j in range(super):
                    rb = b + j * stride + 3
                    s += sum(raw[rb : rb + step : 4])
                out[o + x] = s // (super * super)
        return out, clipped

    def close(self):
        if self._closed:
            return
        self._closed = True
        lib = self._lib
        lib.GdipDeletePath(self._path)
        lib.GdipDeletePath(self._measure_path)
        lib.GdipDeleteMatrix(self._matrix)
        lib.GdipDeleteBrush(self._brush)
        lib.GdipDeleteGraphics(self._g)
        lib.GdipDisposeImage(self._bmp)
        lib.GdipDeletePrivateFontCollection(ctypes.byref(self._coll))
        lib.GdiplusShutdown(self._token)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _fit_render(renderer, char, em, center, tries=4, anchor="bottom"):
    """超界字形按比例缩小重渲（不放大），直到落进格内（底边/中心锚不动）。"""
    cur = em
    clipped = True
    gray = None
    for _ in range(tries):
        gray, clipped = renderer.render(char, cur, center, anchor=anchor)
        if not clipped:
            break
        _, by, bw, bh = renderer.last_info["bounds"]
        cy4 = center[1] * renderer.super
        cx4 = center[0] * renderer.super
        avail_h = max(cy4, 1.0)
        avail_w = max(2 * min(cx4, renderer.px - cx4), 1.0)
        s = min(avail_h / bh, avail_w / bw) * 0.985
        if not (0 < s < 1):
            s = 0.85
        cur *= s
    return gray, clipped, cur


def render_atlas(renderer, roster, fields, em=DEFAULT_EM, gamma=DEFAULT_GAMMA,
                 bboxes=None, place="inherit", limit=None, baseline=DEFAULT_BASELINE,
                 anchor="bottom"):
    """渲染整页 GLY1 图集（未平铺，值 0..15，高值=墨）。

    fields: R.gly1_fields 的输出；bboxes: scan_bboxes 的 {idx: bbox}（inherit 用）；
    place: inherit 时优先对原字形底边中心，否则（新补槽）坐 baseline 基线；
    place=center 则全部用格中心；anchor: 基线的含义（bottom = 墨迹底边，baseline = 字体基线）。
    返回 (atlas bytearray(texW*texH), stats dict)。"""
    tw, th = fields["textureWidth"], fields["textureHeight"]
    cw, ch = fields["cellWidth"], fields["cellHeight"]
    rows = fields["numRows"]
    lut = [int(round(15 * (a / 255.0) ** gamma)) for a in range(256)]
    atlas = bytearray(tw * th)
    stats = {"rendered": 0, "clipped": 0, "inherit": 0, "fallback": 0, "blank": 0,
             "control": 0, "rescaled": 0}
    items = sorted(roster.items())
    if limit:
        items = items[:limit]
    for idx, char in items:
        if ord(char) < 0x20 or ord(char) == 0x7F:
            stats["control"] += 1
            continue
        if place == "inherit" and bboxes and idx in bboxes:
            x0, y0, x1, y1 = bboxes[idx]
            center = ((x0 + x1 - 1) / 2.0, float(y1))
            stats["inherit"] += 1
        else:
            center = (cw / 2.0, float(baseline))
            stats["fallback"] += 1
        gray, clipped = renderer.render(char, em, center, anchor=anchor)
        if clipped:
            gray, clipped, used = _fit_render(renderer, char, em, center, anchor=anchor)
            stats["rescaled"] += 1
        if clipped:
            stats["clipped"] += 1
            stats.setdefault("clipped_list", []).append((idx, char))
        if not any(gray):
            stats["blank"] += 1
            stats.setdefault("blank_list", []).append((idx, char))
        col, row = idx % rows, idx // rows
        for y in range(ch):
            src = y * cw
            dst = (row * ch + y) * tw + col * cw
            atlas[dst : dst + cw] = bytes(map(lut.__getitem__, gray[src : src + cw]))
        stats["rendered"] += 1
    return atlas, stats


# ---------------------------------------------------------------- GLY1 覆写

def overwrite_gly1(bfn, atlas, end_code=None):
    """把渲染图集写进 BFN 的 GLY1 像素区（保留 0x20 头；end_code 可调）。

    断言：像素长度不变、GLY1 块总长不变（其余字段原样）。"""
    _, body, blocks = R.parse_bfn(bfn)
    g = next(b for b in blocks if b[0] == b"GLY1")
    fields = R.gly1_fields(body, g[1])
    data = R.tile_i4(atlas, fields["textureWidth"], fields["textureHeight"])
    if len(data) != fields["textureSize"]:
        raise ValueError("图集长度 %d != textureSize %d" % (len(data), fields["textureSize"]))
    header = bytearray(body[g[1] : g[1] + 0x20])
    if end_code is not None:
        struct.pack_into(">H", header, 0x0A, end_code)
    new_gly1 = bytes(header) + data
    if len(new_gly1) != g[2]:
        raise ValueError("GLY1 块长 %d != %d" % (len(new_gly1), g[2]))
    out = bytearray(bfn)
    out[g[1] : g[1] + g[2]] = new_gly1
    return bytes(out)


# ---------------------------------------------------------------- PNG 输出

def write_png8(path, data, w, h):
    """8-bit 灰度 PNG（data: 0..255 序列）。"""
    raw = b"".join(b"\x00" + bytes(data[y * w : (y + 1) * w]) for y in range(h))

    def chunk(tag, body):
        return (struct.pack(">I", len(body)) + tag + body
                + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def atlas_gray(atlas):
    """GLY1 图集（0..15）转 8-bit 灰度（x17）。"""
    return bytes(v * 17 for v in atlas)


# ---------------------------------------------------------------- CLI（标定/试印）

def _arg(name, default=None):
    for i, a in enumerate(sys.argv):
        if a == name:
            return sys.argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def _repacked(arc):
    """把 RARC 里的多页 BFN 重打包成单页（与主管线同款），返回 (packed, fields)。"""
    from gly1_single_page import repack_bfn
    start, bfn, _ = R.parse_bfn(arc)
    size = struct.unpack_from(">I", bfn, 0x08)[0]
    packed = repack_bfn(bfn[:size])
    _, body, blocks = R.parse_bfn(packed)
    g = next(b for b in blocks if b[0] == b"GLY1")
    return packed, R.gly1_fields(body, g[1])


def main():
    font_name = _arg("--font", "fontres")
    ttf = _arg("--ttf")
    em = float(_arg("--em", DEFAULT_EM))
    gamma = float(_arg("--gamma", DEFAULT_GAMMA))
    place = _arg("--place", "inherit")
    limit = _arg("--limit")
    limit = int(limit) if limit else None
    outdir = os.path.join(ROOT, "work", "fonts")
    os.makedirs(outdir, exist_ok=True)
    png = _arg("--png", os.path.join(outdir, "render_%s_em%g_%s.png" % (font_name, em, place)))
    orig_png = _arg("--orig-png", os.path.join(outdir, "orig_%s.png" % font_name))

    if not ttf:
        sys.exit("需要 --ttf <字体文件>（或 config 的 fonts.<字库>.file）")
    arc_path = os.path.join(paths.font_source_dir(), "%s.arc.yaz0" % font_name)
    if not os.path.exists(arc_path):
        sys.exit("缺少 %s：把字库归档导出到参照字库目录（见 docs/管线复现.md）" % arc_path)

    t0 = time.time()
    with open(arc_path, "rb") as f:
        arc = yaz0.decompress(f.read())
    packed, fields = _repacked(arc)
    print("单页重打包完成 %.1fs  GLY1 %dx%d cell %dx%d 槽位 %d"
          % (time.time() - t0, fields["textureWidth"], fields["textureHeight"],
             fields["cellWidth"], fields["cellHeight"], fields["endCode"] - fields["startCode"]))

    entries, m0 = read_map(packed)
    roster, trouble = build_roster(entries, m0)
    print("名册 %d 槽（method-3 %d 条 + method-0 %s；重复冲突 %d）"
          % (len(roster), len(entries), m0, len(trouble)))
    for idx, a, b in trouble[:10]:
        print("   槽 %#x 冲突: %r vs %r" % (idx, a, b))
    inf1 = read_inf1(packed)
    baseline = inf1["ascent"] if inf1 else DEFAULT_BASELINE
    print("INF1 %s" % inf1)

    t0 = time.time()
    bboxes, hist = scan_bboxes(packed, sorted(roster))
    print("原字形扫描 %.1fs：有墨迹 %d 槽 / 空白 %d 槽；灰度直方图 %s"
          % (time.time() - t0, len(bboxes), len(roster) - len(bboxes), hist))
    widths = [x1 - x0 for x0, y0, x1, y1 in bboxes.values()]
    heights = [y1 - y0 for x0, y0, x1, y1 in bboxes.values()]
    if widths:
        widths.sort()
        heights.sort()
        print("原墨迹尺寸：宽 %d..%d（中位 %d） 高 %d..%d（中位 %d）"
              % (widths[0], widths[-1], widths[len(widths) // 2],
                 heights[0], heights[-1], heights[len(heights) // 2]))
    # 原图 PNG（对照）
    _, body, blocks = R.parse_bfn(packed)
    g = next(b for b in blocks if b[0] == b"GLY1")
    data = body[g[1] + 0x20 : g[1] + g[2]][: fields["textureSize"]]
    orig_img = R.untile_i4(data, fields["textureWidth"], fields["textureHeight"])
    write_png8(orig_png, atlas_gray(orig_img), fields["textureWidth"], fields["textureHeight"])
    print("原图已存 %s" % orig_png)

    t0 = time.time()
    cmap = parse_cmap(ttf)
    missing = check_coverage(cmap, roster)
    print("字体 %s cmap 覆盖 %d 码位；名册缺字 %d" % (os.path.basename(ttf), len(cmap), len(missing)))
    for idx, ch, cp in missing[:20]:
        print("   缺字 槽 %#x 码位 U+%04X %r" % (idx, cp, ch))
    print("cmap 解析 %.1fs" % (time.time() - t0))

    t0 = time.time()
    with Renderer(ttf) as r:
        print("渲染器就绪：family=%r baseline=%d" % (r.family_name, baseline))
        atlas, stats = render_atlas(r, roster, fields, em=em, gamma=gamma,
                                    bboxes=bboxes, place=place, limit=limit,
                                    baseline=baseline)
    dt = time.time() - t0
    print("渲染 %d 字 %.1fs（%.2f 字/秒）place=%s em=%g gamma=%g"
          % (stats["rendered"], dt, stats["rendered"] / max(dt, 1e-9), place, em, gamma))
    print("统计：继承 %d / 基线 %d / 缩放充入 %d / 裁剪警告 %d / 空字形 %d / 控制符跳过 %d"
          % (stats["inherit"], stats["fallback"], stats["rescaled"], stats["clipped"],
             stats["blank"], stats["control"]))
    for idx, char in stats.get("clipped_list", [])[:15]:
        print("   裁剪 槽 %#x %r" % (idx, char))
    for idx, char in stats.get("blank_list", [])[:15]:
        print("   空字形 槽 %#x %r" % (idx, char))

    write_png8(png, atlas_gray(atlas), fields["textureWidth"], fields["textureHeight"])
    print("渲染图已存 %s" % png)


if __name__ == "__main__":
    main()
