"""Decode a tiled HEIC (iPhone) photo to JPEG using ffmpeg's HEVC decoder.

ImageMagick's libheif here can't read iPhone HEIC, so this parses the HEIF
container, rebuilds each tile as an Annex-B HEVC stream, decodes the tiles
with ffmpeg, and stitches the grid.
"""
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


def read_boxes(buf, start, end):
    o = start
    while o < end:
        size, kind = struct.unpack(">I4s", buf[o:o + 8])
        header = 8
        if size == 1:
            size = struct.unpack(">Q", buf[o + 8:o + 16])[0]
            header = 16
        elif size == 0:
            size = end - o
        yield kind.decode(), o + header, o + size
        o += size


def child(buf, start, end, kind):
    return next((b for b in read_boxes(buf, start, end) if b[0] == kind), None)


def uint(buf, o, n):
    return int.from_bytes(buf[o:o + n], "big") if n else 0


def parse(buf):
    _, ms, me = child(buf, 0, len(buf), "meta")
    ms += 4
    items, locs, props, assoc, refs = {}, {}, [], {}, {}
    idat = None
    for kind, s, e in read_boxes(buf, ms, me):
        if kind == "pitm":
            primary = uint(buf, s + 4, 2 if buf[s] == 0 else 4)
        elif kind == "iinf":
            ver = buf[s]
            p = s + 4 + (2 if ver == 0 else 4)
            for _, is_, _ in read_boxes(buf, p, e):
                iv = buf[is_]
                idw = 2 if iv < 3 else 4
                item_id = uint(buf, is_ + 4, idw)
                items[item_id] = buf[is_ + 4 + idw + 2:is_ + 4 + idw + 6].decode()
        elif kind == "iloc":
            ver = buf[s]
            p = s + 4
            off_sz, len_sz = buf[p] >> 4, buf[p] & 15
            base_sz, idx_sz = buf[p + 1] >> 4, (buf[p + 1] & 15 if ver in (1, 2) else 0)
            p += 2
            count = uint(buf, p, 2 if ver < 2 else 4)
            p += 2 if ver < 2 else 4
            for _ in range(count):
                item_id = uint(buf, p, 2 if ver < 2 else 4)
                p += 2 if ver < 2 else 4
                method = 0
                if ver in (1, 2):
                    method = buf[p + 1] & 15
                    p += 2
                p += 2
                base = uint(buf, p, base_sz)
                p += base_sz
                n = uint(buf, p, 2)
                p += 2
                extents = []
                for _ in range(n):
                    p += idx_sz
                    eo = uint(buf, p, off_sz)
                    p += off_sz
                    el = uint(buf, p, len_sz)
                    p += len_sz
                    extents.append((base + eo, el))
                locs[item_id] = (method, extents)
        elif kind == "iprp":
            _, ps, pe = child(buf, s, e, "ipco")
            props = [(k, a, b) for k, a, b in read_boxes(buf, ps, pe)]
            _, as_, _ = child(buf, s, e, "ipma")
            ver, flags = buf[as_], uint(buf, as_ + 1, 3)
            p = as_ + 4
            count = uint(buf, p, 4)
            p += 4
            for _ in range(count):
                item_id = uint(buf, p, 2 if ver < 1 else 4)
                p += 2 if ver < 1 else 4
                n = buf[p]
                p += 1
                lst = []
                for _ in range(n):
                    if flags & 1:
                        lst.append(uint(buf, p, 2) & 0x7FFF)
                        p += 2
                    else:
                        lst.append(buf[p] & 0x7F)
                        p += 1
                assoc[item_id] = lst
        elif kind == "iref":
            idw = 2 if buf[s] == 0 else 4
            for rk, rs, _ in read_boxes(buf, s + 4, e):
                frm = uint(buf, rs, idw)
                n = uint(buf, rs + idw, 2)
                to = [uint(buf, rs + idw + 2 + i * idw, idw) for i in range(n)]
                refs.setdefault(rk, {})[frm] = to
        elif kind == "idat":
            idat = (s, e)
    return primary, items, locs, props, assoc, refs, idat


def item_data(buf, locs, idat, item_id):
    method, extents = locs[item_id]
    base = idat[0] if method == 1 else 0
    return b"".join(buf[base + o:base + o + n] for o, n in extents)


def item_prop(props, assoc, item_id, kind):
    for idx in assoc.get(item_id, []):
        if idx and props[idx - 1][0] == kind:
            return props[idx - 1]
    return None


def hvcc_annexb(buf, prop):
    _, s, _ = prop
    p = s + 22
    out = b""
    for _ in range(buf[p]):
        p += 1
        p += 1
        n = uint(buf, p, 2)
        p += 2
        for _ in range(n):
            ln = uint(buf, p, 2)
            p += 2
            out += b"\0\0\0\1" + buf[p:p + ln]
            p += ln
        p -= 1
    return out


def length_prefixed_to_annexb(data):
    out, o = b"", 0
    while o < len(data):
        n = uint(data, o, 4)
        out += b"\0\0\0\1" + data[o + 4:o + 4 + n]
        o += 4 + n
    return out


def decode_tile(stream, workdir, idx):
    src = workdir / f"t{idx}.hevc"
    dst = workdir / f"t{idx}.png"
    src.write_bytes(stream)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "hevc", "-i", str(src),
                    "-frames:v", "1", str(dst)], check=True)
    return Image.open(dst).convert("RGB")


def convert(src, dst, max_side=1600):
    buf = Path(src).read_bytes()
    primary, items, locs, props, assoc, refs, idat = parse(buf)
    if items[primary] != "grid":
        raise SystemExit(f"primary item is {items[primary]!r}, only grid HEIC is supported")
    grid = item_data(buf, locs, idat, primary)
    flags = grid[1]
    rows, cols = grid[2] + 1, grid[3] + 1
    fw = 4 if flags & 1 else 2
    width, height = uint(grid, 4, fw), uint(grid, 4 + fw, fw)
    tiles = refs["dimg"][primary]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        decoded = []
        for i, tid in enumerate(tiles):
            header = hvcc_annexb(buf, item_prop(props, assoc, tid, "hvcC"))
            body = length_prefixed_to_annexb(item_data(buf, locs, idat, tid))
            decoded.append(decode_tile(header + body, tmp, i))
    tw, th = decoded[0].size
    canvas = Image.new("RGB", (cols * tw, rows * th))
    for i, tile in enumerate(decoded):
        canvas.paste(tile, ((i % cols) * tw, (i // cols) * th))
    image = canvas.crop((0, 0, width, height))
    rot = item_prop(props, assoc, primary, "irot")
    if rot:
        turns = buf[rot[1]] & 3
        image = image.rotate(90 * turns, expand=True)
    image.thumbnail((max_side, max_side))
    image.save(dst, quality=88)
    return image.size


if __name__ == "__main__":
    print(convert(sys.argv[1], sys.argv[2]))
