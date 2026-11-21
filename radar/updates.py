"""Versioned application files. User data lives outside the version directory."""
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
HOME = Path(os.environ.get("RADAR_DATA_HOME", ROOT))
REPO = "MarcosKern/Radar_Vagas"
CHECK_LOCK = threading.Lock()
APPLY_LOCK = threading.Lock()
MANIFEST = "desktop-release.json"


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r"V\d{1,4}(?:\.\d{1,4}){1,3}", value):
        raise ValueError("Versão inválida.")
    return tuple(map(int, value[1:].split(".")))


def fetch(url, limit):
    req = Request(url, headers={"User-Agent": "Radar-de-Vagas-Updater"})
    with urlopen(req, timeout=12) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Arquivo de atualização excede o limite.")
    return data


def history():
    text = (ROOT / "README.md").read_text("utf8")
    parts = re.split(r"^### (V\d+(?:\.\d+)+) — ([^\n]+)\n", text, flags=re.M)
    records = []
    for i in range(1, len(parts), 3):
        changes = [line[2:].strip() for line in parts[i+2].splitlines() if line.startswith("- ")]
        records.append({"version": parts[i], "title": parts[i+1], "changes": changes})
    return records[::-1]


def validate(manifest):
    version(manifest["version"])
    files = manifest["files"]
    required = {"README.md", "monitor.py", "web/index.html", "radar/updates.py",
                "web/assets/app.js", "templates/Vagas_template.xlsx"}
    if not isinstance(files, dict) or not required.issubset(files) or len(files) > 512:
        raise ValueError("Manifesto incompleto.")
    for path, digest in files.items():
        if not re.fullmatch(r"(?:README\.md|monitor\.py|radar/[a-z0-9_]+\.py|web/index\.html|web/assets/[a-z0-9_-]+(?:\.[a-z0-9_-]+)*\.(?:css|js|svg)|templates/Vagas_template\.xlsx)", path):
            raise ValueError("Caminho inválido no manifesto.")
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("Checksum inválido.")
    return manifest


class Updates:
    def __init__(self):
        self.local = json.loads((ROOT / MANIFEST).read_text("utf8"))
        self.pending = None
        self.message = "Verificação pendente."
        self.history = history()

    def status(self):
        target = self.pending
        return {"installed": self.local["version"], "latest": target[1]["version"] if target else None,
                "managed": bool(os.getenv("RADAR_SUPERVISED")), "message": self.message,
                "history": self.history}

    def check(self):
        with CHECK_LOCK:
            try:
                head = json.loads(fetch(f"https://api.github.com/repos/{REPO}/git/ref/heads/main", 64_000))["object"]["sha"]
                if not re.fullmatch("[a-f0-9]{40}", head):
                    raise ValueError("Revisão inválida.")
                base = f"https://raw.githubusercontent.com/{REPO}/{head}/"
                try:
                    remote = validate(json.loads(fetch(base + MANIFEST, 200_000)))
                except HTTPError as exc:
                    if exc.code != 404:
                        raise
                    # V0.14 and earlier predate the desktop manifest.
                    old = json.loads(fetch(base + "package.json", 32_000))
                    if version("V" + old["version"]) >= version(self.local["version"]):
                        raise ValueError("Manifesto ausente na versão publicada.")
                    remote = self.local
                self.pending = (base, remote) if version(remote["version"]) > version(self.local["version"]) else None
                self.message = "Atualização disponível." if self.pending else "Você está usando a versão mais recente disponível para esta instalação."
            except (OSError, ValueError, KeyError, TypeError):
                self.pending = None
                self.message = "Não foi possível verificar o GitHub. Tente novamente."
            return self.status()

    def stage(self):
        target = self.pending
        if not os.getenv("RADAR_SUPERVISED") or not target:
            raise ValueError("Nenhuma atualização disponível para esta instalação.")
        base, remote = target
        versions = HOME / "versions"
        versions.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix="app-", dir=versions))
        try:
            for name, digest in remote["files"].items():
                old, new = ROOT / name, stage / name
                new.parent.mkdir(parents=True, exist_ok=True)
                if old.is_file() and hashlib.sha256(old.read_bytes()).hexdigest() == digest:
                    shutil.copyfile(old, new)
                    continue
                data = fetch(base + name, 16_000_000)
                if hashlib.sha256(data).hexdigest() != digest:
                    raise ValueError("Falha ao verificar " + name)
                new.write_bytes(data)
            (stage / MANIFEST).write_text(json.dumps(remote), "utf8")
            pending = HOME / "pending.tmp"
            pending.write_text(stage.name, "utf8")
            pending.replace(HOME / "pending")
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
