#!/usr/bin/env python3
"""Parse panels-dcc-vendor.log into coarse + apt-refined install progress."""

from __future__ import annotations

import re
import socket
from dataclasses import dataclass, field
from typing import Optional

APT_SUMMARY_RE = re.compile(
    r"^(\d+)\s+upgraded,\s+(\d+)\s+newly installed",
)
GET_RE = re.compile(r"^Get:\d+\s+")
UNPACKING_RE = re.compile(r"^Unpacking\s+")
SETTING_UP_RE = re.compile(r"^Setting up\s+")

# Coarse stage weights (sum to 100). Tuned so panels installer dominates.
STAGE_WEIGHTS = {
    "starting": 2,
    "network": 2,
    "clock": 1,
    "apt_update": 5,
    "dist_upgrade": 15,
    "panels_installer": 70,
    "finished": 5,
}

STAGE_ORDER = [
    "starting",
    "network",
    "clock",
    "apt_update",
    "dist_upgrade",
    "panels_installer",
    "finished",
]

STAGE_LABELS = {
    "starting": "Starting",
    "network": "Waiting for network",
    "clock": "Waiting for system clock",
    "apt_update": "Updating package lists",
    "dist_upgrade": "Upgrading system packages",
    "panels_installer": "Installing PanelsDCC",
    "finished": "Finished",
}

INSTALL_SUBSTEPS = [
    ("Installing required packages", "Installing required packages (curl, jq, nodejs, npm)"),
    ("Fetching latest release metadata for PanelsDCC/connect", "Downloading PanelsDCC Connect"),
    ("Downloading PanelsDCC/connect", "Downloading PanelsDCC Connect"),
    ("Fetching latest release metadata for PanelsDCC/control", "Downloading PanelsDCC Control"),
    ("Downloading PanelsDCC/control", "Downloading PanelsDCC Control"),
    ("Installing connect.deb", "Installing PanelsDCC Connect"),
    ("Installing control.deb", "Installing PanelsDCC Control"),
    ("Installing Control Node.js dependencies", "Installing Control dependencies"),
    ("Creating Desktop folder", "Creating desktop shortcuts"),
    ("Creating desktop launchers", "Creating desktop shortcuts"),
    ("Installation complete", "Installation complete"),
]


@dataclass
class AptWindow:
    total: int = 0
    gets: int = 0
    unpacking: int = 0
    setting_up: int = 0
    active: bool = False

    def reset(self, upgraded: int, newly: int) -> None:
        self.total = max(0, upgraded + newly)
        self.gets = 0
        self.unpacking = 0
        self.setting_up = 0
        self.active = self.total > 0

    def phase(self) -> tuple[str, int, int]:
        """Return (label, current, total) for the active apt sub-phase."""
        if not self.active or self.total <= 0:
            return ("", 0, 0)
        if self.setting_up > 0 or self.unpacking >= self.total:
            return ("Installing", min(self.setting_up, self.total), self.total)
        if self.unpacking > 0 or self.gets >= self.total:
            return ("Unpacking", min(self.unpacking, self.total), self.total)
        return ("Downloading packages", min(self.gets, self.total), self.total)

    def phase_pct(self) -> Optional[int]:
        label, cur, total = self.phase()
        if not label or total <= 0:
            return None
        # Map download / unpack / configure into 0–33 / 33–66 / 66–100 within apt window
        if label.startswith("Downloading"):
            return int(33 * cur / total)
        if label.startswith("Unpacking"):
            return 33 + int(33 * cur / total)
        return 66 + int(34 * cur / total)


@dataclass
class ProgressParser:
    stage: str = "starting"
    install_detail: str = ""
    apt: AptWindow = field(default_factory=AptWindow)
    done: bool = False
    error: Optional[str] = None
    connect_ready: bool = False
    handover: bool = False
    _max_overall: int = 0

    def feed(self, line: str) -> None:
        # Strip CR and common ANSI noise for matching; keep original-ish text for markers
        clean = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line).rstrip("\r\n")
        if not clean:
            return

        if "[panels-dcc-vendor] starting" in clean:
            self.stage = "starting"
        elif "[panels-dcc-vendor] waiting for network" in clean:
            self.stage = "network"
        elif "[panels-dcc-vendor] network ready" in clean:
            self.stage = "network"
        elif "[panels-dcc-vendor] waiting for NTP" in clean or "[panels-dcc-vendor] waiting for NTP / sane" in clean:
            self.stage = "clock"
        elif "[panels-dcc-vendor] clock OK" in clean or "[panels-dcc-vendor] clock looks sane" in clean:
            self.stage = "clock"
        elif "[panels-dcc-vendor] apt-get update" in clean:
            self.stage = "apt_update"
            self.apt = AptWindow()
        elif "[panels-dcc-vendor] apt-get dist-upgrade" in clean:
            self.stage = "dist_upgrade"
            self.apt = AptWindow()
        elif "[panels-dcc-vendor] running Panels DCC installer" in clean:
            self.stage = "panels_installer"
            self.apt = AptWindow()
            self.install_detail = "Starting PanelsDCC installer"
        elif "[panels-dcc-vendor] finished" in clean:
            self.stage = "finished"
            self.done = True
            self.handover = True
            self.connect_ready = True
            self.apt.active = False
            self.install_detail = "Finished"
        elif "[panelsdcc-install] Installation complete" in clean:
            self.install_detail = "Installation complete"
            self.connect_ready = True
            self.handover = True
        elif "Handing over port 80 to Control" in clean or "Handing over to Control" in clean:
            self.handover = True
            self.connect_ready = True
            self.install_detail = "Handing over to Control"

        if clean.startswith("[panelsdcc-install] "):
            msg = clean[len("[panelsdcc-install] ") :]
            for needle, label in INSTALL_SUBSTEPS:
                if msg.startswith(needle):
                    self.install_detail = label
                    if needle.startswith("Installing Control Node.js"):
                        self.apt.active = False
                    break
            if msg.startswith("Installing connect.deb"):
                self.connect_ready = True
            if (
                msg.startswith("Installing control.deb")
                or msg.startswith("Stopping install progress")
                or msg.startswith("Handing over")
            ):
                self.connect_ready = True
                self.handover = True

        m = APT_SUMMARY_RE.match(clean)
        if m:
            self.apt.reset(int(m.group(1)), int(m.group(2)))
            return

        if self.apt.active:
            if GET_RE.match(clean):
                self.apt.gets += 1
            elif UNPACKING_RE.match(clean):
                self.apt.unpacking += 1
            elif SETTING_UP_RE.match(clean):
                self.apt.setting_up += 1

    def feed_text(self, text: str) -> None:
        for line in text.splitlines():
            self.feed(line)

    def status(self, hostname: Optional[str] = None) -> dict:
        if hostname is None:
            try:
                hostname = socket.gethostname()
            except OSError:
                hostname = "panels-dcc"

        overall = self._compute_overall()
        # Monotonic: never report a lower overall than before
        if overall < self._max_overall:
            overall = self._max_overall
        else:
            self._max_overall = overall

        detail, phase_pct = self._detail_and_phase()
        host = hostname or "panels-dcc"
        return {
            "overall_pct": overall,
            "stage": self.stage,
            "stage_label": STAGE_LABELS.get(self.stage, self.stage),
            "detail": detail,
            "phase_pct": phase_pct,
            "done": self.done,
            "error": self.error,
            "hostname": host,
            "connect_ready": self.connect_ready or self.done,
            "handover": self.handover or self.done,
            "connect_url": f"http://{host}:9000/",
            "control_url": f"http://{host}/",
        }

    def _detail_and_phase(self) -> tuple[str, Optional[int]]:
        if self.done:
            return ("Install finished", 100)
        label, cur, total = self.apt.phase()
        if label and total > 0:
            return (f"{label}: {cur} / {total}", self.apt.phase_pct())
        if self.install_detail:
            # Indeterminate npm / download metadata steps
            if "dependencies" in self.install_detail.lower():
                return (self.install_detail + "…", None)
            return (self.install_detail, None)
        return (STAGE_LABELS.get(self.stage, self.stage), None)

    def _compute_overall(self) -> int:
        if self.done or self.stage == "finished":
            return 100

        completed = 0
        for name in STAGE_ORDER:
            if name == self.stage:
                break
            completed += STAGE_WEIGHTS[name]
        else:
            return 100

        weight = STAGE_WEIGHTS[self.stage]
        within_apt = 0.0
        within_ladder = 0.0
        label, cur, total = self.apt.phase()
        if label and total > 0:
            within_apt = (self.apt.phase_pct() or 0) / 100.0

        if self.stage == "panels_installer" and self.install_detail:
            ladder = [
                "Starting PanelsDCC installer",
                "Installing required packages",
                "Downloading PanelsDCC Connect",
                "Downloading PanelsDCC Control",
                "Installing PanelsDCC Connect",
                "Installing PanelsDCC Control",
                "Installing Control dependencies",
                "Creating desktop shortcuts",
                "Installation complete",
            ]
            idx = 0
            for i, step in enumerate(ladder):
                if self.install_detail.startswith(step) or self.install_detail == step:
                    idx = i
            # Use floor of current step (not +1) so a fresh apt window can still
            # refine upward within the step without jumping the whole ladder.
            within_ladder = idx / max(1, len(ladder) - 1)

        if self.stage in ("network", "clock", "starting", "apt_update") and not label:
            within = 0.5
        else:
            # Never let a brand-new apt window (0/N) pull overall backwards
            # relative to install.sh substep progress.
            within = max(within_apt, within_ladder)

        return min(99, int(completed + weight * within))


def parse_log(text: str, hostname: Optional[str] = None) -> dict:
    p = ProgressParser()
    p.feed_text(text)
    return p.status(hostname=hostname)


def parse_log_file(path: str, hostname: Optional[str] = None) -> dict:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return parse_log(f.read(), hostname=hostname)
