#!/usr/bin/env python3
"""Lightweight HTTP progress UI for PanelsDCC first-boot install."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

# Allow running from /run/panels-dcc-progress or from repo scripts/progress
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from progress_status import ProgressParser  # noqa: E402

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>PanelsDCC — Installing</title>
  <style>
    :root {
      --bg: #1a242f;
      --fg: #e8eef4;
      --muted: #9aa8b5;
      --accent: #3b82f6;
      --track: #2c3a48;
      --ok: #34d399;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background: radial-gradient(ellipse at top, #243447 0%, var(--bg) 55%);
      color: var(--fg);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
    }
    main {
      width: min(36rem, 100%);
    }
    h1 {
      font-size: clamp(1.6rem, 4vw, 2rem);
      font-weight: 700;
      letter-spacing: -0.02em;
      margin: 0 0 0.35rem;
    }
    .strap {
      color: var(--muted);
      margin: 0 0 1.75rem;
      font-size: 1rem;
      line-height: 1.45;
    }
    .bar-wrap {
      height: 0.85rem;
      background: var(--track);
      border-radius: 999px;
      overflow: hidden;
      margin-bottom: 0.75rem;
    }
    .bar {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--accent), #60a5fa);
      border-radius: 999px;
      transition: width 0.4s ease;
    }
    .bar.done { background: var(--ok); }
    .bar.pulse {
      background: linear-gradient(90deg, var(--accent), #93c5fd, var(--accent));
      background-size: 200% 100%;
      animation: shimmer 1.4s linear infinite;
    }
    @keyframes shimmer {
      0% { background-position: 100% 0; }
      100% { background-position: -100% 0; }
    }
    .pct {
      font-size: 1.75rem;
      font-weight: 650;
      font-variant-numeric: tabular-nums;
      margin: 0 0 0.35rem;
    }
    .stage {
      font-size: 1.05rem;
      font-weight: 600;
      margin: 0 0 0.25rem;
    }
    .detail {
      color: var(--muted);
      margin: 0;
      min-height: 1.4em;
      font-size: 0.95rem;
    }
    .next {
      display: none;
      margin-top: 1.75rem;
      padding-top: 1.25rem;
      border-top: 1px solid color-mix(in srgb, var(--muted) 35%, transparent);
    }
    .next.visible { display: block; }
    .next a.btn, .next button.btn {
      display: inline-block;
      margin: 0;
      padding: 0.65rem 1.15rem;
      border: none;
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-weight: 600;
      text-decoration: none;
      cursor: pointer;
    }
    .next a.btn:hover, .next button.btn:hover { filter: brightness(1.08); }
  </style>
</head>
<body>
  <main>
    <h1>Panels DCC</h1>
    <p class="strap">Installing. This can take 15–30 minutes.</p>
    <p class="pct" id="pct">0%</p>
    <div class="bar-wrap"><div class="bar" id="bar"></div></div>
    <p class="stage" id="stage">Starting</p>
    <p class="detail" id="detail"></p>
    <div class="next" id="next">
      <button type="button" class="btn" id="openBtn">Open PanelsDCC</button>
    </div>
  </main>
  <script>
    const pctEl = document.getElementById('pct');
    const barEl = document.getElementById('bar');
    const stageEl = document.getElementById('stage');
    const detailEl = document.getElementById('detail');
    const nextEl = document.getElementById('next');
    const openBtn = document.getElementById('openBtn');
    openBtn.addEventListener('click', function () {
      window.location.reload();
    });
    async function tick() {
      try {
        const r = await fetch('/status.json', { cache: 'no-store' });
        const s = await r.json();
        const pct = Math.max(0, Math.min(100, s.overall_pct || 0));
        pctEl.textContent = pct + '%';
        barEl.style.width = pct + '%';
        stageEl.textContent = s.stage_label || s.stage || '';
        detailEl.textContent = s.detail || '';
        barEl.classList.toggle('done', !!s.done || !!s.handover);
        barEl.classList.toggle('pulse', !s.done && !s.handover && (s.phase_pct === null || s.phase_pct === undefined));

        const showOpen = !!s.handover || !!s.done;
        if (showOpen && s.done) {
          detailEl.textContent = s.detail || 'Install finished';
        }
        nextEl.classList.toggle('visible', showOpen);
      } catch (e) {
        detailEl.textContent = 'Waiting for progress…';
      }
    }
    tick();
    setInterval(tick, 1500);
  </script>
</body>
</html>
"""


class ProgressState:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.parser = ProgressParser()
        self._offset = 0
        self._lock = threading.Lock()

    def refresh(self) -> dict:
        with self._lock:
            try:
                if not self.log_path.exists():
                    return self.parser.status()
                size = self.log_path.stat().st_size
                if size < self._offset:
                    # Log rotated / recreated
                    self.parser = ProgressParser()
                    self._offset = 0
                with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(self._offset)
                    chunk = f.read()
                    self._offset = f.tell()
                if chunk:
                    self.parser.feed_text(chunk)
            except OSError:
                pass
            return self.parser.status()


def make_handler(state: ProgressState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # quieter
            return

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                body = HTML_PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/status.json":
                payload = json.dumps(state.refresh()).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_error(404)

    return Handler


def write_pid(pid_path: Path) -> None:
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()) + "\n", encoding="utf-8")


def default_pid_path(*, replay: bool) -> str:
    env = os.environ.get("PANELS_PROGRESS_PID")
    if env is not None:
        return env
    if replay:
        return str(Path(tempfile.gettempdir()) / "panels-dcc-progress.pid")
    return "/run/panels-dcc-progress/server.pid"


def make_server(bind: str, port: int, handler) -> ThreadingHTTPServer:
    class ReusableServer(ThreadingHTTPServer):
        allow_reuse_address = True

    return ReusableServer((bind, port), handler)


STAGE_PAUSE_MARKERS = (
    "[panels-dcc-vendor]",
    "[panelsdcc-install]",
    "upgraded,",
    "newly installed",
)


def _is_stage_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s.startswith("Get:") or s.startswith("Unpacking ") or s.startswith("Setting up "):
        return False
    return any(m in s for m in STAGE_PAUSE_MARKERS)


def _is_apt_progress_line(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("Get:") or s.startswith("Unpacking ") or s.startswith("Setting up ")


def replay_worker(
    source: Path,
    dest: Path,
    *,
    delay: float = 0.1,
    stage_pause: float = 0.1,
    apt_batch: int = 3,
) -> None:
    """Replay a vendor log slowly enough to watch each stage in the UI.

    Important stage/install markers are emitted one line at a time with an
    extra pause. Apt Get/Unpacking/Setting up lines are batched so package
    counters still animate without taking forever.
    """
    dest.write_text("", encoding="utf-8")
    lines = source.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    print(
        f"[panels-progress] replay: {len(lines)} lines, "
        f"delay={delay}s, stage_pause={stage_pause}s (Ctrl+C to stop server)",
        flush=True,
    )
    with open(dest, "a", encoding="utf-8") as out:
        i = 0
        while i < len(lines):
            line = lines[i]
            if _is_stage_line(line):
                out.write(line)
                out.flush()
                preview = line.strip()[:90]
                print(f"[panels-progress] stage → {preview}", flush=True)
                time.sleep(max(delay, stage_pause))
                i += 1
                continue

            if _is_apt_progress_line(line):
                batch = []
                while i < len(lines) and len(batch) < apt_batch and _is_apt_progress_line(lines[i]):
                    batch.append(lines[i])
                    i += 1
                out.write("".join(batch))
                out.flush()
                time.sleep(delay)
                continue

            # Quiet filler (Reading database, npm ANSI, etc.) — emit in larger chunks
            batch = []
            while (
                i < len(lines)
                and len(batch) < 20
                and not _is_stage_line(lines[i])
                and not _is_apt_progress_line(lines[i])
            ):
                batch.append(lines[i])
                i += 1
            out.write("".join(batch))
            out.flush()
            time.sleep(delay)

    print("[panels-progress] replay finished — leave the page open or Ctrl+C to stop", flush=True)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="PanelsDCC install progress server")
    parser.add_argument(
        "--log",
        default=os.environ.get("PANELS_PROGRESS_LOG", "/var/log/panels-dcc-vendor.log"),
        help="Path to vendor install log",
    )
    parser.add_argument("--port", type=int, default=int(os.environ.get("PANELS_PROGRESS_PORT", "80")))
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument(
        "--pid-file",
        default=None,
        help="PID file path (default: /run/... on Pi; temp dir with --replay). Use empty string to skip.",
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Replay --log into a temp file in chunks (for local visual testing)",
    )
    parser.add_argument(
        "--replay-delay",
        type=float,
        default=0.1,
        help="Seconds between apt/filler batches during --replay (default: 0.1)",
    )
    parser.add_argument(
        "--replay-stage-pause",
        type=float,
        default=0.1,
        help="Extra seconds to pause on each stage/install marker (default: 0.1)",
    )
    parser.add_argument(
        "--replay-apt-batch",
        type=int,
        default=3,
        help="How many Get:/Unpacking/Setting up lines per tick (default: 3)",
    )
    args = parser.parse_args(argv)

    if args.pid_file is None:
        args.pid_file = default_pid_path(replay=args.replay)

    log_path = Path(args.log)
    if args.replay:
        if not log_path.is_file():
            print(f"Replay source not found: {log_path}", file=sys.stderr)
            return 1
        if args.port == 80:
            # Local replay should not need root / port 80
            args.port = 8765
            print("Note: --replay defaults to port 8765 (override with --port)", file=sys.stderr)
        tmp = Path(tempfile.gettempdir()) / "panels-dcc-vendor-replay.log"
        threading.Thread(
            target=replay_worker,
            args=(log_path, tmp),
            kwargs={
                "delay": args.replay_delay,
                "stage_pause": args.replay_stage_pause,
                "apt_batch": max(1, args.replay_apt_batch),
            },
            daemon=True,
        ).start()
        log_path = tmp
        print(f"Replaying into {log_path}")
        print(f"Open http://127.0.0.1:{args.port}/ in your browser")

    state = ProgressState(log_path)
    pid_path: Optional[Path] = None
    if args.pid_file:
        pid_path = Path(args.pid_file)
        try:
            write_pid(pid_path)
        except OSError as e:
            print(f"Warning: could not write pid file ({pid_path}): {e}", file=sys.stderr)
            pid_path = None

    handler = make_handler(state)
    try:
        httpd = make_server(args.bind, args.port, handler)
    except OSError as e:
        print(f"Failed to bind {args.bind}:{args.port}: {e}", file=sys.stderr)
        if getattr(e, "errno", None) == 98:  # EADDRINUSE
            print(
                f"Port {args.port} is already in use — pick another, e.g. --port 8766",
                file=sys.stderr,
            )
        return 1

    host = socket.gethostname()
    url_host = "127.0.0.1" if args.bind in ("0.0.0.0", "::") else args.bind
    print(f"[panels-progress] serving on http://{url_host}:{args.port}/ (hostname={host})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        if pid_path is not None:
            try:
                pid_path.unlink(missing_ok=True)
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
