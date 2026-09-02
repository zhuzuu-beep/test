from __future__ import annotations

import unittest
from pathlib import Path

from app.config import load_config
from app.parser import decode_html, parse_candidates


ROOT = Path(__file__).resolve().parents[1]


class ParserTest(unittest.TestCase):
    def test_hnrsks_fixture(self) -> None:
        config = load_config(ROOT / "config")
        feed = config.feed("hnrsks_home")
        body = (ROOT / "tests/fixtures/hnrsks_home.html").read_bytes()
        candidates = parse_candidates(decode_html(body), feed)
        self.assertEqual(len(candidates), 6)
        self.assertEqual(candidates[0].publish_date, "2026-01-05")
        self.assertTrue(candidates[0].url.startswith("http://www.hnrsks.com/"))
        self.assertNotIn("example.com", {item.url for item in candidates})


if __name__ == "__main__":
    unittest.main()
