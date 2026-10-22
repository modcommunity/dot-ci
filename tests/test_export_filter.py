"""Fixtures for check-export-filter.sh. Run: python3 -m unittest discover -s tests"""
import os
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "check-export-filter.sh")


def check(*presets):
    d = tempfile.mkdtemp()
    body = ""
    for i, (inc, exc) in enumerate(presets):
        body += '[preset.%d]\n\nname="P%d"\ninclude_filter="%s"\nexclude_filter="%s"\n\n[preset.%d.options]\n\nx=1\n\n' % (i, i, inc, exc, i)
    with open(os.path.join(d, "export_presets.cfg"), "w") as fh:
        fh.write(body)
    r = subprocess.run(["bash", SCRIPT, d], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


class ExportFilter(unittest.TestCase):
    def test_include_passes(self):
        self.assertEqual(check(("cfg/*", "tools/*"))[0], 0)

    def test_dropped_cfg_fails(self):
        code, out = check(("addons.lock", "tools/*"))
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)

    def test_deliberate_exclude_is_a_note(self):
        code, out = check(("addons.lock, cfg/addons/*", "tools/*, cfg/*"))
        self.assertEqual(code, 0)
        self.assertIn("note", out)

    def test_exclude_does_not_excuse_other_preset(self):
        self.assertEqual(check(("cfg/*", "cfg/*"), ("", "tools/*"))[0], 1)


if __name__ == "__main__":
    unittest.main()
