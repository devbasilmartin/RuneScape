"""`skillbot doctor`: checks that the machine is ready for the bot."""
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .layout import CANVAS_H, CANVAS_W

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""


def check_session(env=os.environ) -> Check:
    if not env.get("DISPLAY"):
        return Check("display", FAIL, "no DISPLAY: run this from a terminal on the VM's desktop")
    session = env.get("XDG_SESSION_TYPE", "")
    if session == "wayland":
        return Check("display", FAIL, "Wayland session: pyautogui can't control it; log in to "
                                      "'Ubuntu on Xorg' (setup.sh disables Wayland, then reboot)")
    if session not in ("x11", ""):
        return Check("display", WARN, f"unexpected session type {session!r}")
    return Check("display", PASS, f"X11 on {env['DISPLAY']}")


def check_screen(monitor: dict) -> Check:
    w, h = monitor["width"], monitor["height"]
    # fixed-mode game (765x503) plus RuneLite's title bar and sidebar
    if w < CANVAS_W + 250 or h < CANVAS_H + 100:
        return Check("screen size", FAIL, f"{w}x{h} is too small; use at least 1280x800")
    return Check("screen size", PASS, f"{w}x{h}")


def check_capture(pixels) -> Check:
    import numpy as np
    arr = np.asarray(pixels)
    if arr.size == 0 or arr.std() < 1:
        return Check("screen capture", FAIL, "screenshot is blank; is the desktop visible?")
    return Check("screen capture", PASS, "screenshots work")


def check_gsetting(schema: str, key: str, good, label: str, run=subprocess.run) -> Check:
    try:
        out = run(["gsettings", "get", schema, key], capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return Check(label, WARN, "gsettings not available; check this by hand")
    value = out.stdout.strip()
    if out.returncode != 0:
        return Check(label, WARN, f"could not read {schema} {key}")
    if value.split()[-1] != good:
        return Check(label, FAIL, f"{key} is {value}; run scripts/vm/setup.sh")
    return Check(label, PASS, value)


def check_java() -> Check:
    if shutil.which("java"):
        return Check("java", PASS, shutil.which("java"))
    return Check("java", WARN, "java not found; fine if your client bundles its own")


def check_calibration(data_dir: Path) -> Check:
    missing = [f for f in ("origin.json", "fingerprint.json", "run_orb.json", "digits.json")
               if not (data_dir / f).exists()]
    if missing:
        return Check("calibration", WARN, f"not done yet: {', '.join(missing)} "
                                          "(see the README once the game is running)")
    return Check("calibration", PASS, "all calibration files present")


def run_checks(cfg) -> list[Check]:
    checks = [check_session()]
    if checks[0].status != FAIL:
        try:
            import mss
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                checks.append(check_screen(monitor))
                checks.append(check_capture(sct.grab(monitor)))
        except Exception as e:     # noqa: BLE001 - report anything that stops capture
            checks.append(Check("screen capture", FAIL, f"{type(e).__name__}: {e}"))
        try:
            import pyautogui
            pyautogui.position()
            checks.append(Check("mouse control", PASS, "pyautogui works"))
        except Exception as e:     # noqa: BLE001
            checks.append(Check("mouse control", FAIL, f"{type(e).__name__}: {e}"))
    checks += [
        check_gsetting("org.gnome.desktop.session", "idle-delay", "0", "screen blanking off"),
        check_gsetting("org.gnome.desktop.screensaver", "lock-enabled", "false", "lock screen off"),
        check_gsetting("org.gnome.desktop.notifications", "show-banners", "false",
                       "notification pop-ups off"),
        check_java(),
        check_calibration(cfg.data_dir),
    ]
    return checks


def report(checks: list[Check]) -> int:
    for c in checks:
        print(f"[{c.status}] {c.name}: {c.detail}")
    failed = [c for c in checks if c.status == FAIL]
    print("\nReady." if not failed else f"\n{len(failed)} problem(s) to fix.")
    return 1 if failed else 0
