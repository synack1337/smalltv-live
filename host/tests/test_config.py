import os
import tempfile
import unittest
from pathlib import Path

from smalltv_live.config import ConfigError, load


def _load(text):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "config.toml"
        p.write_text(text, encoding="utf-8")
        return load(p)


class ConfigTest(unittest.TestCase):
    def test_missing_file_gives_defaults(self):
        cfg = load(Path(tempfile.gettempdir()) / "does-not-exist.toml")
        self.assertEqual(cfg.tv.host, "smalltv.local")
        self.assertFalse(cfg.location.has_coordinates)

    def test_example_config_loads(self):
        example = Path(__file__).resolve().parents[2] / "config.example.toml"
        cfg = load(example)
        self.assertEqual(cfg.display.language, "en")

    def test_values(self):
        cfg = _load('[tv]\nhost = "10.0.0.5"\n[location]\nlatitude = 46.7\nlongitude = 23.6\n'
                    'timezone = "Europe/Bucharest"\n[display]\nlanguage = "ro"\n')
        self.assertEqual(cfg.tv.host, "10.0.0.5")
        self.assertTrue(cfg.location.has_coordinates)
        self.assertEqual(str(cfg.tz), "Europe/Bucharest")

    def test_rejects_bad_values(self):
        for text in ('[display]\nlanguage = "de"\n', '[display]\nfps = 0\n', '[display]\nnight_start = 24\n',
                     '[location]\ntimezone = "Mars/Base"\n', '[location]\nlatitude = 91.0\nlongitude = 0.0\n',
                     '[tv]\nport = 70000\n', '[tv]\nhost = "-oProxy=x"\n', '[tv]\nhost = "a b"\n', '[tv]\nhots = "x"\n', '[nope]\n', 'not toml ='):
            with self.subTest(text=text), self.assertRaises(ConfigError):
                _load(text)

    def test_env_override(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.toml"
            p.write_text('[tv]\nport = 9000\n', encoding="utf-8")
            old = os.environ.get("SMALLTV_LIVE_CONFIG")
            os.environ["SMALLTV_LIVE_CONFIG"] = str(p)
            try:
                self.assertEqual(load().tv.port, 9000)
            finally:
                if old is None:
                    del os.environ["SMALLTV_LIVE_CONFIG"]
                else:
                    os.environ["SMALLTV_LIVE_CONFIG"] = old


if __name__ == "__main__":
    unittest.main()
