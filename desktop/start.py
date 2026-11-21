"""Stable supervisor shared by source installations and the Windows launcher."""
import json
import os
import secrets
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen


def supervise(base, home, port, browser=False):
    home.mkdir(parents=True, exist_ok=True)
    base = base.resolve()
    env = dict(os.environ, RADAR_DATA_HOME=str(home), RADAR_SUPERVISED="1")
    addr = f"http://127.0.0.1:{port}"
    def health():
        try:
            with urlopen(addr + "/api/updates/health", timeout=.5) as response:
                return json.load(response)
        except (OSError, ValueError):
            return {}
    def selected(marker):
        if marker.is_file():
            name = marker.read_text("utf8").strip()
            if name.startswith("app-") and name.isascii() and name.replace("-", "").replace("_", "").isalnum():
                folder = home / "versions" / name
                if (folder / "monitor.py").is_file():
                    return folder
        return base
    def release(folder):
        value = json.loads((folder / "desktop-release.json").read_text("utf8"))["version"]
        return tuple(map(int, value.lstrip("V").split(".")))
    if health().get("app") == "Radar_Vagas":
        if browser:
            webbrowser.open(addr)
        return 0
    active, pending = home / "active", home / "pending"
    while True:
        current = selected(active)
        if release(current) < release(base):
            current = base
        candidate = selected(pending) if pending.exists() else current
        if release(candidate) < release(current):
            candidate = current
        env["RADAR_INSTANCE"] = secrets.token_hex(16)
        proc = subprocess.Popen([sys.executable, str(candidate / "monitor.py"), "serve", "--port", str(port)], env=env)
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    break
                if health().get("instance") == env["RADAR_INSTANCE"]:
                    if pending.exists() and candidate != base:
                        pending.replace(active)
                    else:
                        pending.unlink(missing_ok=True)
                    if browser:
                        webbrowser.open(addr)
                        browser = False
                    break
                time.sleep(.1)
            else:
                proc.terminate()
            code = proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            proc.wait()
            return 0
        if pending.exists() and candidate != current and code != 75:
            pending.unlink()
            continue
        if code != 75:
            return code


if __name__ == "__main__":
    sys.exit(supervise(Path(sys.argv[1]), Path(sys.argv[2]), 8765, True))
