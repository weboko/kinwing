import unittest

from tests.util import KwTestCase  # noqa: F401  (sets sys.path)
from kinwing import yamlio


SAMPLE = {
    "id": "fsrs",
    "title": "Spaced repetition: FSRS vs SM-2",
    "date": "2026-10-28",
    "ts": "2026-10-28T01:02:03Z",
    "flag": True, "none": None, "n": 3, "f": 0.9,
    "yesish": "yes", "numstr": "0123",
    "multi": "line one\nline two\n\nline four",
    "empty_list": [], "empty_map": {},
    "list": ["a", "b: c", "#hash", "trailing space "],
    "nested": {"budget": {"max_minutes": 40, "tags": ["x", "y"]}},
    "perspectives": [{"id": "econ", "name": "Economics", "why": "incentives: who pays"},
                     {"id": "tech", "name": "Technical", "why": ""}],
    "unicode": "“quoted” — dash ✓",
}


class YamlTest(unittest.TestCase):
    def test_roundtrip_builtin(self):
        text = yamlio.dump(SAMPLE)
        self.assertEqual(yamlio.load_builtin(text), SAMPLE)

    def test_roundtrip_pyyaml_agrees(self):
        if yamlio._pyyaml is None:
            self.skipTest("PyYAML not installed")
        text = yamlio.dump(SAMPLE)
        self.assertEqual(yamlio._normalize(yamlio._pyyaml.safe_load(text)), SAMPLE)

    def test_hand_written_yaml(self):
        text = """# a comment
title: Hand edited   # trailing comment
depth: deep
include: [economics, "adoption, failures", 'it''s']
budget: {max_minutes: 30, max_sources_per_run: 5}
perspectives:
- id: a
  name: A
- id: b
  name: B
notes: |
  first
  second
folded: >-
  one
  two
url: https://example.com/#frag
"""
        d = yamlio.load_builtin(text)
        self.assertEqual(d["title"], "Hand edited")
        self.assertEqual(d["include"], ["economics", "adoption, failures", "it's"])
        self.assertEqual(d["budget"], {"max_minutes": 30, "max_sources_per_run": 5})
        self.assertEqual([p["id"] for p in d["perspectives"]], ["a", "b"])
        self.assertEqual(d["notes"], "first\nsecond\n")
        self.assertEqual(d["folded"], "one two")
        self.assertEqual(d["url"], "https://example.com/#frag")

    def test_frontmatter(self):
        text = yamlio.join_frontmatter({"id": "x", "tags": ["a"]}, "# Body\n\ntext")
        meta, body = yamlio.split_frontmatter(text)
        self.assertEqual(meta, {"id": "x", "tags": ["a"]})
        self.assertEqual(body.strip(), "# Body\n\ntext")

    def test_bad_frontmatter(self):
        with self.assertRaises(yamlio.YamlError):
            yamlio.split_frontmatter("---\nid: x\nno end")


if __name__ == "__main__":
    unittest.main()
