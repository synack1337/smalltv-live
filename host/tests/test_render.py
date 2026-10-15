import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from smalltv_live import dog, weather
from smalltv_live.config import load
from smalltv_live.screen import Screen

SAMPLE = {
    "current": {"temperature_2m": 7.6, "weather_code": 61, "is_day": 1},
    "hourly": {"precipitation_probability": list(range(24))},
    "daily": {"temperature_2m_max": [10.2], "temperature_2m_min": [5.5], "precipitation_probability_max": [80]},
}


class WeatherTest(unittest.TestCase):
    def test_parse(self):
        w = weather.parse(SAMPLE, 14)
        self.assertEqual((w.temperature, w.code, w.is_day, w.high, w.low, w.rain_chance), (8, 61, True, 10, 6, 14))

    def test_missing_hourly_falls_back_to_daily(self):
        data = dict(SAMPLE, hourly={})
        self.assertEqual(weather.parse(data, 3).rain_chance, 80)


class DogTest(unittest.TestCase):
    def test_every_mood_renders(self):
        for mood in dog.MOODS:
            img = dog.sprite(mood, 1.25)
            self.assertEqual(img.size, dog.SIZE)
            self.assertEqual(img.mode, "RGBA")
            self.assertIsNotNone(img.getchannel("A").getbbox(), mood)

    def test_moods(self):
        self.assertEqual(dog.mood_for(0, True), "happy")
        self.assertEqual(dog.mood_for(0, False), "sleep")
        self.assertEqual(dog.mood_for(3, True), "cuddle")
        self.assertEqual(dog.mood_for(63, True), "sleep")
        self.assertEqual(dog.mood_for(73, True), "shiver")
        self.assertEqual(dog.mood_for(None, True), "sleep")


class ScreenTest(unittest.TestCase):
    def test_frames_with_and_without_data(self):
        with tempfile.TemporaryDirectory() as d:
            cfg_path = Path(d) / "c.toml"
            cfg_path.write_text(f'[usage]\ncache = "{Path(d) / "none.json"}"\n[display]\nlanguage = "ro"\n')
            screen = Screen(load(cfg_path))
            now = datetime(2026, 10, 15, 19, 30, 5).timestamp()
            for w in (None, weather.parse(SAMPLE, 19)):
                img = screen.frame(now, w)
                self.assertEqual(img.size, (240, 240))
                self.assertEqual(img.mode, "RGB")
            # seconds change between frames, the rest of the static layer is reused
            a, b = screen.frame(now, None), screen.frame(now + 1, None)
            self.assertNotEqual(a.tobytes(), b.tobytes())


if __name__ == "__main__":
    unittest.main()
