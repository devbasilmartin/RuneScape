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


def check_os(os_release=Path("/etc/os-release")) -> Check:
    try:
        info = dict(line.split("=", 1) for line in os_release.read_text().splitlines()
                    if "=" in line)
    except OSError:
        return Check("ubuntu", WARN, "no /etc/os-release; is this the VM?")
    distro, version = info.get("ID", "").strip('"'), info.get("VERSION_ID", "").strip('"')
    if distro == "ubuntu" and version == "24.04":
        return Check("ubuntu", PASS, "24.04")
    return Check("ubuntu", FAIL, f"{distro} {version}: the bot needs Ubuntu 24.04 (later "
                                 "versions have no Xorg session; docs/vm-setup.md)")


PACKAGES = (("numpy", "numpy"), ("cv2", "opencv-python"), ("mss", "mss"),
            ("pyautogui", "pyautogui"), ("yaml", "pyyaml"), ("discord", "discord.py"))


def check_packages(mouse_enabled: bool = False, find=None) -> Check:
    import importlib.util
    find = find or importlib.util.find_spec
    missing = [pip for mod, pip in PACKAGES if find(mod) is None]
    if mouse_enabled and find("humanized_input") is None:
        from .mouse import INSTALL
        missing.append(f"humanized_input (mouse A/B testing is on: {INSTALL})")
    if missing:
        return Check("python packages", FAIL, "missing: " + ", ".join(missing)
                     + " (pip install -r requirements.txt)")
    return Check("python packages", PASS, "all installed")


def check_tools(which=shutil.which) -> Check:
    missing = [t for t in ("xdotool",) if not which(t)]
    if missing:
        return Check("tools", FAIL, f"missing {', '.join(missing)}: run scripts/vm/setup.sh")
    return Check("tools", PASS, "xdotool")


def check_login(profile: str | None, env=os.environ) -> Check:
    """Credentials present (never printed)."""
    where = f"profiles/{profile}.env in ~/.config/skillbot/" if profile else \
        "~/.config/skillbot/env"
    missing = [k for k in ("SKILLBOT_USERNAME", "SKILLBOT_PASSWORD") if not env.get(k)]
    if missing:
        return Check("login", WARN, f"{' and '.join(missing)} not set ({where}); the bot "
                                    "can't log back in after a disconnect")
    return Check("login", PASS, "username and password set" + (f" for {profile}" if profile
                                                               else ""))


def check_client(window_name: str, run=subprocess.run) -> Check:
    try:
        found = run(["xdotool", "search", "--name", window_name], capture_output=True,
                    timeout=5).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return Check("client window", WARN, "can't look for it without xdotool")
    if not found:
        return Check("client window", WARN, f"no {window_name!r} window open (fine if the "
                                            "supervisor starts it)")
    return Check("client window", PASS, f"{window_name} is open")


def check_runelite_profile(repo_dir: Path) -> Check:
    if not (repo_dir / "bot-profile.properties").exists():
        return Check("runelite profile", WARN, "not generated yet: python -m skillbot "
                                               "runelite-profile, then import it in RuneLite "
                                               "(docs/runelite-profile.md)")
    return Check("runelite profile", PASS, "bot-profile.properties generated (imported? "
                                           "debug.png shows the highlights)")


def check_rotation(profiles) -> Check | None:
    if profiles is None or not (profiles.root / "rotation.yaml").exists():
        return None
    from .rotation import load_rotation
    try:
        load_rotation(profiles)
    except ValueError as e:
        return Check("rotation.yaml", FAIL, str(e))
    return Check("rotation.yaml", PASS, "valid")


def run_checks(cfg, profile: str | None = None, profiles=None,
               repo_dir: Path | None = None) -> list[Check]:
    from .supervisor import SupervisorConfig
    repo_dir = repo_dir or Path(__file__).resolve().parent.parent
    try:
        window = SupervisorConfig.from_dict(cfg.supervisor).window_name
    except (TypeError, ValueError):
        window = "RuneLite"
    checks = [check_os(), check_packages(bool(cfg.mouse.get("enabled"))), check_tools(),
              check_session()]
    if checks[-1].status != FAIL:
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
        check_client(window),
        check_login(profile),
        check_runelite_profile(repo_dir),
        check_calibration(cfg.data_dir),
        check_rotation(profiles),
    ]
    return [c for c in checks if c is not None]


def report(checks: list[Check]) -> int:
    for c in checks:
        print(f"[{c.status}] {c.name}: {c.detail}")
    failed = [c for c in checks if c.status == FAIL]
    print("\nReady." if not failed else f"\n{len(failed)} problem(s) to fix.")
    return 1 if failed else 0
