import struct
import unittest

from PIL import Image

from smalltv_live import display


class HeaderTest(unittest.TestCase):
    def test_layout(self):
        h = display.header(b"R", 10, 20, 30, 40, 2400)
        self.assertEqual(len(h), 9)
        self.assertEqual(struct.unpack("<cBBBBI", h), (b"R", 10, 20, 29, 39, 2400))

    def test_full_width_fits_in_a_byte(self):
        self.assertEqual(display.header(b"R", 0, 0, 240, 240, 0)[3:5], bytes([239, 239]))

    def test_backlight_is_clamped(self):
        self.assertEqual(display.backlight(300)[1], 255)
        self.assertEqual(display.backlight(-5)[1], 0)


class Rgb565Test(unittest.TestCase):
    def test_primaries(self):
        for colour, expected in (((255, 255, 255), 0xFFFF), ((0, 0, 0), 0x0000),
                                 ((255, 0, 0), 0xF800), ((0, 255, 0), 0x07E0), ((0, 0, 255), 0x001F)):
            data = display.to_rgb565(Image.new("RGB", (240, 240), colour)).tobytes()
            self.assertEqual((data[0] << 8) | data[1], expected, colour)

    def test_rejects_wrong_size(self):
        with self.assertRaises(ValueError):
            display.to_rgb565(Image.new("RGB", (10, 10)))


def _messages(data):
    """Parse a stream back into (type, x, y, w, h, payload) tuples."""
    out, i = [], 0
    while i < len(data):
        kind, x, y, w1, h1, n = struct.unpack("<cBBBBI", data[i:i + 9])
        out.append((kind, x, y, w1 + 1, h1 + 1, data[i + 9:i + 9 + n]))
        i += 9 + n
    return out


class FrameUpdateTest(unittest.TestCase):
    def setUp(self):
        self.a = display.to_rgb565(Image.new("RGB", (240, 240), (20, 30, 40)))

    def test_first_frame_is_full(self):
        msgs = _messages(display.frame_update(self.a, None))
        self.assertEqual(msgs[0][:5], (b"R", 0, 0, 240, 240))
        self.assertEqual(len(msgs[0][5]), 240 * 240 * 2)
        self.assertEqual(msgs[-1][0], b"F")

    def test_unchanged_frame_sends_only_frame_end(self):
        msgs = _messages(display.frame_update(self.a, self.a))
        self.assertEqual([m[0] for m in msgs], [b"F"])

    def test_change_sends_its_bounding_box(self):
        img = Image.new("RGB", (240, 240), (20, 30, 40))
        img.paste((255, 255, 255), (100, 50, 110, 55))
        msgs = _messages(display.frame_update(display.to_rgb565(img), self.a))
        rects = [m for m in msgs if m[0] == b"R"]
        self.assertEqual(len(rects), 1)
        _, x, y, w, h, payload = rects[0]
        self.assertEqual((x, y, w, h), (100, 50, 10, 5))
        self.assertEqual(len(payload), w * h * 2)

    def test_rectangles_stay_on_screen(self):
        img = Image.new("RGB", (240, 240), (0, 0, 0))
        img.paste((255, 0, 0), (230, 230, 240, 240))
        for kind, x, y, w, h, payload in _messages(display.frame_update(display.to_rgb565(img), self.a)):
            if kind == b"R":
                self.assertLessEqual(x + w, 240)
                self.assertLessEqual(y + h, 240)
                self.assertEqual(len(payload), w * h * 2)


class PanelSetupTest(unittest.TestCase):
    def test_commands_match_firmware_allow_list(self):
        msgs = _messages(display.panel_setup(invert=True, bgr=True))
        self.assertEqual([(m[0], m[1], m[5]) for m in msgs], [(b"C", 0x21, b""), (b"C", 0x36, b"\x08")])


if __name__ == "__main__":
    unittest.main()
