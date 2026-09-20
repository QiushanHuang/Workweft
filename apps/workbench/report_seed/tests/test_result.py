from pathlib import Path
import unittest


class ResultTest(unittest.TestCase):
    def test_deliverable_exists(self):
        content = Path('result.md').read_text()
        self.assertGreater(len(content.strip()), 150)
        self.assertNotIn('The Harness worker will replace', content)
        self.assertIn('#', content)
