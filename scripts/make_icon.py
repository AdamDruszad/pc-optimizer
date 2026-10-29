"""Az alkalmazásikon (assets/icon.ico) előállítása, függőség nélkül: zöld villám sötét, lekerekített négyzeten.

    python scripts/make_icon.py [előnézet.png]
"""
import struct
import sys
import zlib
from pathlib import Path

SIZES = (16, 24, 32, 48, 64, 128, 256)
SAMPLES = 4  # 4×4 részminta pixelenként az élsimításhoz
OUT = Path(__file__).resolve().parents[1] / "assets" / "icon.ico"

# Villám (0..1 koordináták, y lefelé), a négyzet közepére méretezve
BOLT = [(0.62, 0.05), (0.26, 0.55), (0.48, 0.55), (0.38, 0.95), (0.76, 0.42), (0.54, 0.42)]
BG_TOP, BG_BOTTOM = (0x24, 0x2C, 0x3A), (0x0F, 0x11, 0x15)
BOLT_TOP, BOLT_BOTTOM = (0x6E, 0xF5, 0xB8), (0x2B, 0xC4, 0x80)


def _inside_rounded(x: float, y: float, r: float) -> bool:
    dx, dy = max(r - x, 0, x - (1 - r)), max(r - y, 0, y - (1 - r))
    return dx * dx + dy * dy <= r * r


def _inside_polygon(x: float, y: float, poly) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _mix(a, b, t):
    return tuple(round(p + (q - p) * t) for p, q in zip(a, b))


def render(size: int) -> bytes:
    """RGBA pixelek soronként; kis méreten nagyobb villám, hogy 16 pixelen is felismerhető legyen."""
    scale = 0.74 if size <= 24 else 0.64
    poly = [(0.5 + (px - 0.5) * scale, 0.5 + (py - 0.5) * scale) for px, py in BOLT]
    radius = 0.22
    rows = []
    for j in range(size):
        row = bytearray()
        for i in range(size):
            bg = bolt = 0
            for sj in range(SAMPLES):
                for si in range(SAMPLES):
                    x, y = (i + (si + 0.5) / SAMPLES) / size, (j + (sj + 0.5) / SAMPLES) / size
                    if _inside_rounded(x, y, radius):
                        bg += 1
                        bolt += _inside_polygon(x, y, poly)
            total = SAMPLES * SAMPLES
            t = j / max(size - 1, 1)
            color = _mix(_mix(BG_TOP, BG_BOTTOM, t), _mix(BOLT_TOP, BOLT_BOTTOM, t), bolt / max(bg, 1))
            row += bytes(color) + bytes([round(255 * bg / total)])
        rows.append(bytes(row))
    return b"".join(rows)


def png(size: int, rgba: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    stride = size * 4
    raw = b"".join(b"\x00" + rgba[r * stride:(r + 1) * stride] for r in range(size))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def ico(images: dict[int, bytes]) -> bytes:
    """ICO-tároló PNG-képekkel (Windows Vista óta minden méretnél támogatott)."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, data = b"", b""
    for size, image in images.items():
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(image), offset + len(data))
        data += image
    return header + entries + data


def main() -> None:
    images = {s: png(s, render(s)) for s in SIZES}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_bytes(ico(images))
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_bytes(images[256])
    print(f"{OUT} ({OUT.stat().st_size} bájt, {len(images)} méret)")


if __name__ == "__main__":
    main()
