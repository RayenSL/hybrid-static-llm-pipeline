import tempfile
import unittest
from pathlib import Path

from analysis import architecture_figure


class ArchitectureFigureTests(unittest.TestCase):
    def test_architecture_uses_frozen_v2_campaign_population(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)

            result = architecture_figure.main([
                "--out-dir", str(output),
                "--name", "architecture",
            ])

            self.assertEqual(0, result)
            svg = (output / "architecture.svg").read_text(encoding="utf-8")

        required = (
            "frozen at v2.0",
            "13 God Class - 13 Long Method - 10 Obsolete API",
            "26 God Class and Long Method targets x 3 repetitions x 8 cells = 624 assignments",
            "seed 20260812",
            "One planning and one implementation call per target",
            "exactly five cases",
            "three passes on the pristine system",
            "26 factorial targets",
            "270 frozen drivers",
        )
        for text in required:
            self.assertIn(text, svg)

        stale = (
            "frozen at v1.0",
            "10 God Class + 9 Long Method",
            "456 attempts",
            "seed 503999552",
            "One stateless call per target",
            "two passes on the pristine system",
            "19 factorial targets",
        )
        for text in stale:
            self.assertNotIn(text, svg)


if __name__ == "__main__":
    unittest.main()
