"""Talking to the SmallTV Live firmware: RGB565 conversion, the wire protocol and the connection.

Protocol (see docs/protocol.md): every message starts with a 9-byte header
    type, x, y, width - 1, height - 1, payload length (uint32, little endian)
'R' rectangle of RGB565 pixels (big endian), 'F' end of frame (the TV answers 'K'),
'B' backlight level in x, 'C' panel command in x with parameter bytes as payload.
"""
from __future__ import annotations

import errno
import os
import select
import socket
import struct
import subprocess
import sys

from PIL import Image, ImageChops

WIDTH = HEIGHT = 240
BAND = 16                   # rows per diff band
ACK_TIMEOUT = 3.0

# ------------------------------------------------------------------ RGB565

_BAYER4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


def _threshold(levels: int) -> Image.Image:
    """Fixed ordered-dither offsets, so identical pixels always convert the same way."""
    img = Image.new("L", (WIDTH, HEIGHT))
    img.putdata([int((_BAYER4[y % 4][x % 4] + 0.5) * levels / 16)
                 for y in range(HEIGHT) for x in range(WIDTH)])
    return img


_DITHER_RB = _threshold(8)    # 5-bit channels lose 3 bits
_DITHER_G = _threshold(4)     # 6-bit green loses 2 bits


def to_rgb565(img: Image.Image) -> Image.Image:
    """240x240 RGB image -> two-channel image whose bytes are big-endian RGB565 pixels."""
    if img.size != (WIDTH, HEIGHT):
        raise ValueError("frame must be 240x240")
    r, g, b = img.convert("RGB").split()
    r = ImageChops.add(r, _DITHER_RB)
    b = ImageChops.add(b, _DITHER_RB)
    g = ImageChops.add(g, _DITHER_G)
    hi = ImageChops.add(r.point(lambda v: v & 0xF8), g.point(lambda v: v >> 5))
    lo = ImageChops.add(g.point(lambda v: ((v >> 2) & 0x07) << 5), b.point(lambda v: v >> 3))
    return Image.merge("LA", (hi, lo))


# ------------------------------------------------------------------ messages

def header(kind: bytes, x: int = 0, y: int = 0, w: int = 1, h: int = 1, length: int = 0) -> bytes:
    return struct.pack("<cBBBBI", kind, x, y, w - 1, h - 1, length)


def rect(img565: Image.Image, box: tuple[int, int, int, int]) -> bytes:
    x0, y0, x1, y1 = box
    data = img565.crop(box).tobytes()
    return header(b"R", x0, y0, x1 - x0, y1 - y0, len(data)) + data


def frame_update(cur: Image.Image, prev: Image.Image | None) -> bytes:
    """Rectangles covering what changed since `prev` (everything when prev is None), then 'F'."""
    out = bytearray()
    if prev is None:
        out += rect(cur, (0, 0, WIDTH, HEIGHT))
    else:
        diff = ImageChops.difference(cur, prev)
        for y in range(0, HEIGHT, BAND):
            bb = diff.crop((0, y, WIDTH, y + BAND)).getbbox()
            if bb:
                out += rect(cur, (bb[0], y + bb[1], bb[2], y + bb[3]))
    out += header(b"F")
    return bytes(out)


def backlight(level: int) -> bytes:
    return header(b"B", max(0, min(255, level)))


def panel_setup(invert: bool, bgr: bool) -> bytes:
    """Inversion and colour order, for panels that differ from the default."""
    return (header(b"C", 0x21 if invert else 0x20) +
            header(b"C", 0x36, length=1) + bytes([0x08 if bgr else 0x00]))


# ------------------------------------------------------------------ connection

class Link:
    """TCP connection to the TV.

    macOS Local Network privacy can refuse LAN connections from an interpreter that hasn't been granted
    access (EHOSTUNREACH). In that case the connection falls back to Apple's /usr/bin/nc, which is allowed.
    """

    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self._sock: socket.socket | None = None
        self._nc: subprocess.Popen | None = None

    def open(self) -> None:
        self.close()
        try:
            self._sock = socket.create_connection((self.host, self.port), timeout=5)
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock.settimeout(None)
        except OSError as exc:
            if sys.platform != "darwin" or exc.errno != errno.EHOSTUNREACH or not os.path.exists("/usr/bin/nc"):
                raise
            self._nc = subprocess.Popen(["/usr/bin/nc", self.host, str(self.port)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)

    def close(self) -> None:
        if self._sock:
            self._sock.close()
            self._sock = None
        if self._nc:
            self._nc.kill()
            self._nc.wait()
            self._nc = None

    def send(self, data: bytes) -> None:
        if self._sock:
            self._sock.sendall(data)
        elif self._nc and self._nc.stdin:
            self._nc.stdin.write(data)
        else:
            raise ConnectionError("not connected")

    def wait_ack(self, timeout: float = ACK_TIMEOUT) -> None:
        fd = self._sock.fileno() if self._sock else self._nc.stdout.fileno() if self._nc else None
        if fd is None:
            raise ConnectionError("not connected")
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            raise TimeoutError("no acknowledgement from the TV")
        data = self._sock.recv(64) if self._sock else os.read(fd, 64)
        if not data:
            raise ConnectionError("connection closed by the TV")
        if data[-1:] != b"K":
            raise ConnectionError("unexpected reply from the TV")
