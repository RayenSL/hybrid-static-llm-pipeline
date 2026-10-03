import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ArchitectureFigureTests(unittest.TestCase):
    def test_figure_uses_direct_editing_context_reruns(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            subprocess.run(
                [
                    sys.executable,
                    "analysis/architecture_figure.py",
                    "--out-dir",
                    str(out),
                    "--name",
                    "architecture",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            svg = (out / "architecture.svg").read_text(encoding="utf-8")

        self.assertIn("432 assignments", svg)
        self.assertIn("108 assignments", svg)
        self.assertIn("Referenced type declarations", svg)
        self.assertIn("No separate applier", svg)
        self.assertNotIn("DeepSeek", svg)
        self.assertNotIn("suggestion-plus-applier", svg)

    def test_figure_uses_shared_test_generation_and_arrow_payload_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            subprocess.run(
                [
                    sys.executable,
                    "analysis/architecture_figure.py",
                    "--out-dir",
                    str(out),
                    "--name",
                    "architecture",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            svg = (out / "architecture.svg").read_text(encoding="utf-8")

        self.assertIn("Detection and nested context construction", svg)
        self.assertIn("Structural only to grounded factorial cells", svg)
        self.assertIn("All four payloads to context-ladder runs", svg)
        self.assertIn("Confirmatory diagnosis-blind test generation and admission", svg)
        self.assertIn("Visible only to test-ON factorial assignments", svg)
        self.assertIn("Corpus: frozen author-written characterisation drivers", svg)
        self.assertIn("Ibis: frozen author-written 90-driver golden-master harness", svg)
        self.assertNotIn("Corpus and Ibis ladders: hidden until post-repair oracle", svg)
        self.assertNotIn("hidden; post-repair oracle", svg)
        self.assertNotIn("Diagnosis-blind test generation - factorial", svg)
        self.assertNotIn("All four nested payloads", svg)


if __name__ == "__main__":
    unittest.main()
