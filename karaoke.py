#!/usr/bin/env python3
"""
Karaoke (CLI) — minimal, fast, no-frills.
- Plays audio via ffplay (FFmpeg) for rock-solid timing and cross‑platform reliability.
- Displays .lrc lyrics with timestamps in a curses TUI.
- Progress bar, current/prev/next lines, and simple sync offset control.
- Works best on macOS/Linux out of the box. On Windows, install "windows-curses".

Usage:
  python karaoke.py path/to/song.mp3 path/to/lyrics.lrc [--offset SECONDS] [--tempo 1.0] [--pitch 0]

Notes:
  • You must have FFmpeg (ffplay) in PATH. Get it from https://ffmpeg.org/
  • .lrc format supports lines like: [00:12.34] lyric text
  • If your audio starts slightly later/earlier than the first lyric, tweak --offset (e.g., 0.3 or -0.2).
  • Tempo and pitch are optional and applied by ffplay filters (simple, decent quality).
"""

import argparse
import curses
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import List, Tuple

TIMESTAMP = re.compile(r"\[(\d{2}):(\d{2})(?:\.(\d{1,2}))?\]")

@dataclass
class Line:
    t: float  # seconds since start
    text: str

def parse_lrc(path: str) -> List[Line]:
    lines: List[Line] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.rstrip("\n")
            stamps = list(TIMESTAMP.finditer(raw))
            if not stamps:
                continue
            text = TIMESTAMP.sub("", raw).strip()
            for m in stamps:
                mm = int(m.group(1))
                ss = int(m.group(2))
                cc = m.group(3) or "0"
                # Normalize centiseconds/milliseconds
                if len(cc) == 1:
                    frac = int(cc) / 10.0
                else:
                    frac = int(cc[:2]) / 100.0
                t = mm * 60 + ss + frac
                lines.append(Line(t=t, text=text))
    lines.sort(key=lambda x: x.t)
    return lines

def build_ffplay_cmd(audio: str, tempo: float, pitch_semitones: float) -> list:
    # Compose audio filter chain. Tempo without pitch change is done with atempo (0.5..2.0 range per filter).
    # For modest pitch shifting, use asetrate + atempo trick (quality is ok for karaoke demos).
    afilters = []
    if abs(pitch_semitones) > 1e-6:
        # pitch shift by changing sample rate then atempo to restore tempo
        ratio = 2 ** (pitch_semitones / 12.0)
        afilters.append(f"asetrate=sr*{ratio}")
        # adjust tempo back so overall speed ~1.0 (may interact with user tempo below)
        afilters.append(f"atempo={1/ratio:.6f}")
    if abs(tempo - 1.0) > 1e-6:
        # ffplay's atempo supports 0.5..2.0, chain if outside
        # We'll clamp to safe range and warn in UI if out-of-range.
        afilters.append(f"atempo={tempo:.6f}")

    args = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]
    if afilters:
        args += ["-af", ",".join(afilters)]
    args += [audio]
    return args

def draw_progress(stdscr, now_s: float, total_s: float, width: int) -> None:
    width = max(10, width)
    frac = 0.0 if total_s <= 0 else min(1.0, max(0.0, now_s / total_s))
    filled = int(frac * (width - 2))
    bar = "[" + "#" * filled + "-" * ((width - 2) - filled) + "]"
    mins = int(now_s // 60)
    secs = int(now_s % 60)
    tmins = int(total_s // 60)
    tsecs = int(total_s % 60)
    label = f" {mins:02d}:{secs:02d} / {tmins:02d}:{tsecs:02d} "
    # Fit label inside bar if possible
    if len(label) < len(bar) - 2:
        start = (len(bar) - len(label)) // 2
        bar = bar[:start] + label + bar[start + len(label):]
    stdscr.addstr(bar)

def find_current_index(lyrics: List[Line], t: float) -> int:
    # Return index of the line that should be active at time t
    lo, hi = 0, len(lyrics) - 1
    ans = -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if lyrics[mid].t <= t:
            ans = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return ans

def estimate_total_duration(audio: str, fallback: float = 0.0) -> float:
    # We won't parse duration to avoid ffprobe dependency. Let user live without total length, or approximate from last lyric.
    return fallback

def karaoke(stdscr, audio: str, lrc: str, offset: float, tempo: float, pitch: float):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(50)  # 20 FPS

    lyrics = parse_lrc(lrc)
    if not lyrics:
        raise SystemExit("No timestamped lyrics found in .lrc")

    last_stamp = lyrics[-1].t
    approx_total = last_stamp + 5.0  # a bit of tail

    # Prepare player
    cmd = build_ffplay_cmd(audio, tempo, pitch)

    # Launch audio
    try:
        player = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise SystemExit("ffplay not found. Install FFmpeg and ensure 'ffplay' is in PATH.")

    start = time.perf_counter() + offset
    # Main loop
    active_idx = -1
    try:
        while True:
            now = time.perf_counter() - start
            # update active index
            idx = find_current_index(lyrics, now)
            if idx != active_idx:
                active_idx = idx

            # Clear and draw
            stdscr.erase()
            h, w = stdscr.getmaxyx()

            title = "Karaoke CLI  •  q:quit  ↑/↓: nudge offset  ±0.05s  •  offset={:+.2f}s  tempo={:.2f}×  pitch={:+.1f} st".format(offset, tempo, pitch)
            stdscr.addstr(0, 0, title[:max(0, w-1)])
            # progress bar line
            stdscr.move(1, 0)
            draw_progress(stdscr, max(0.0, now), approx_total, max(10, w-1))

            # Determine which lines to show: prev, current, next (and maybe one more)
            lines_to_show = []
            for rel in (-2, -1, 0, 1, 2):
                j = active_idx + rel
                if 0 <= j < len(lyrics):
                    prefix = "  "
                    if rel == 0:
                        prefix = "> "
                    elif rel == -1:
                        prefix = "· "
                    elif rel == 1:
                        prefix = "· "
                    lines_to_show.append(prefix + lyrics[j].text)

            # Center this block vertically
            y_start = max(3, (h // 2) - len(lines_to_show) // 2)
            for i, line in enumerate(lines_to_show):
                y = y_start + i
                if y >= h - 1:
                    break
                if line.startswith("> "):
                    stdscr.attron(curses.A_BOLD)
                    stdscr.addstr(y, 0, line[:max(0, w-1)])
                    stdscr.attroff(curses.A_BOLD)
                else:
                    stdscr.addstr(y, 0, line[:max(0, w-1)])

            stdscr.refresh()

            # Keyboard handling
            try:
                ch = stdscr.getch()
            except KeyboardInterrupt:
                ch = ord('q')
            if ch != -1:
                if ch in (ord('q'), 27):  # q or ESC
                    break
                elif ch == curses.KEY_UP:
                    offset += 0.05
                    start -= 0.05
                elif ch == curses.KEY_DOWN:
                    offset -= 0.05
                    start += 0.05

            # Exit if player finished and last lyric has passed
            if player.poll() is not None and now > last_stamp + 1.0:
                break

            time.sleep(0.02)
    finally:
        # Clean up player if still running
        if player.poll() is None:
            with contextlib.suppress(Exception):
                player.terminate()
                time.sleep(0.2)
                player.kill()

def main():
    ap = argparse.ArgumentParser(description="Command-line Karaoke")
    ap.add_argument("audio", help="Path to audio file (mp3, wav, etc.). Requires ffplay in PATH.")
    ap.add_argument("lrc", help="Path to .lrc lyrics file with timestamps.")
    ap.add_argument("--offset", type=float, default=0.0, help="Starting sync offset in seconds (+ delays lyrics)")
    ap.add_argument("--tempo", type=float, default=1.0, help="Playback tempo multiplier (0.5–2.0 recommended)")
    ap.add_argument("--pitch", type=float, default=0.0, help="Pitch shift in semitones (±4 recommended)")
    args = ap.parse_args()

    # Basic checks
    if not os.path.exists(args.audio):
        print(f"Audio not found: {args.audio}", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(args.lrc):
        print(f"LRC not found: {args.lrc}", file=sys.stderr)
        sys.exit(1)

    # Windows: suggest windows-curses if needed
    try:
        curses.initscr()
        curses.endwin()
    except Exception:
        print("If you're on Windows, install 'windows-curses' (pip install windows-curses).", file=sys.stderr)

    curses.wrapper(lambda scr: karaoke(scr, args.audio, args.lrc, args.offset, args.tempo, args.pitch))

if __name__ == "__main__":
    import contextlib
    main()
