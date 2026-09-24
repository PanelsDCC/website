#!/usr/bin/env python3
"""Unit tests for install progress parser against sample vendor log."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from progress_status import ProgressParser, parse_log  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "panels-dcc-vendor.log"


def _prefix_until(lines: list[str], predicate) -> str:
    out = []
    for line in lines:
        out.append(line)
        if predicate(line):
            break
    return "\n".join(out) + "\n"


def _prefix_n_matches(lines: list[str], start_pred, match_pred, n: int) -> str:
    out = []
    started = False
    count = 0
    for line in lines:
        out.append(line)
        if not started and start_pred(line):
            started = True
            continue
        if started and match_pred(line):
            count += 1
            if count >= n:
                break
    return "\n".join(out) + "\n"


class ProgressStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FIXTURE.is_file():
            raise unittest.SkipTest(f"missing fixture {FIXTURE}")
        cls.lines = FIXTURE.read_text(encoding="utf-8", errors="replace").splitlines()

    def test_after_network_and_clock_early(self):
        text = _prefix_until(self.lines, lambda l: "clock OK" in l)
        s = parse_log(text, hostname="panels-dcc")
        self.assertIn(s["stage"], ("clock", "network"))
        self.assertLess(s["overall_pct"], 15)
        self.assertFalse(s["done"])

    def test_dist_upgrade_download_counts(self):
        # After summary + 3 Get: lines in dist-upgrade section
        text = _prefix_n_matches(
            self.lines,
            start_pred=lambda l: "4 upgraded, 0 newly installed" in l,
            match_pred=lambda l: l.startswith("Get:"),
            n=3,
        )
        s = parse_log(text, hostname="panels-dcc")
        self.assertEqual(s["stage"], "dist_upgrade")
        self.assertIn("Downloading packages:", s["detail"])
        self.assertIn("/ 4", s["detail"])
        # At least some of 3 downloads reflected
        self.assertRegex(s["detail"], r"Downloading packages: [1-4] / 4")

    def test_big_apt_download_100_of_513(self):
        text = _prefix_n_matches(
            self.lines,
            start_pred=lambda l: "513 newly installed" in l,
            match_pred=lambda l: l.startswith("Get:"),
            n=100,
        )
        s = parse_log(text, hostname="panels-dcc")
        self.assertEqual(s["stage"], "panels_installer")
        self.assertEqual(s["detail"], "Downloading packages: 100 / 513")
        self.assertGreaterEqual(s["overall_pct"], 20)
        self.assertLess(s["overall_pct"], 100)

    def test_unpacking_and_setting_up_switch(self):
        # After 513 summary, past downloads into unpacking
        text = _prefix_n_matches(
            self.lines,
            start_pred=lambda l: "513 newly installed" in l,
            match_pred=lambda l: l.startswith("Unpacking "),
            n=50,
        )
        s = parse_log(text, hostname="panels-dcc")
        self.assertEqual(s["stage"], "panels_installer")
        self.assertTrue(
            s["detail"].startswith("Unpacking:") or s["detail"].startswith("Installing:"),
            msg=s["detail"],
        )
        self.assertIn("/ 513", s["detail"])

    def test_finished_is_done(self):
        s = parse_log("\n".join(self.lines), hostname="panels-dcc")
        self.assertTrue(s["done"])
        self.assertEqual(s["overall_pct"], 100)
        self.assertEqual(s["stage"], "finished")
        self.assertTrue(s["connect_ready"])
        self.assertTrue(s["handover"])
        self.assertEqual(s["connect_url"], "http://panels-dcc:9000/")

    def test_connect_ready_after_connect_deb(self):
        text = _prefix_until(self.lines, lambda l: "Installing connect.deb" in l)
        s = parse_log(text, hostname="panels-dcc")
        self.assertTrue(s["connect_ready"])
        self.assertFalse(s["done"])
        self.assertEqual(s["connect_url"], "http://panels-dcc:9000/")

    def test_installation_complete_before_vendor_finished(self):
        text = _prefix_until(self.lines, lambda l: "Installation complete." in l)
        s = parse_log(text, hostname="panels-dcc")
        self.assertFalse(s["done"])
        self.assertEqual(s["stage"], "panels_installer")
        self.assertIn("complete", s["detail"].lower())

    def test_monotonic_across_prefixes(self):
        markers = [
            lambda l: "network ready" in l,
            lambda l: "clock OK" in l,
            lambda l: "[panels-dcc-vendor] apt-get update" in l,
            lambda l: "[panels-dcc-vendor] apt-get dist-upgrade" in l,
            lambda l: "4 upgraded, 0 newly installed" in l,
            lambda l: "[panels-dcc-vendor] running Panels DCC installer" in l,
            lambda l: "513 newly installed" in l,
            lambda l: "Installation complete." in l,
            lambda l: "[panels-dcc-vendor] finished" in l,
        ]
        parser = ProgressParser()
        last = -1
        for pred in markers:
            # Rebuild from full prefix each time (simulates client polls with full log)
            text = _prefix_until(self.lines, pred)
            p = ProgressParser()
            p.feed_text(text)
            pct = p.status()["overall_pct"]
            self.assertGreaterEqual(pct, last, msg=f"progress went backwards: {last} -> {pct}")
            last = pct
            parser = p
        self.assertEqual(last, 100)

    def test_npm_ansi_noise_does_not_crash(self):
        # Include a slice with npm spinner lines (before vendor finished)
        start = next(i for i, l in enumerate(self.lines) if "Control Node.js dependencies" in l)
        end = next(i for i, l in enumerate(self.lines) if "[panels-dcc-vendor] finished" in l)
        chunk = "\n".join(self.lines[: min(start + 80, end)])
        s = parse_log(chunk, hostname="panels-dcc")
        self.assertEqual(s["stage"], "panels_installer")
        self.assertIsInstance(s["overall_pct"], int)


if __name__ == "__main__":
    unittest.main()
