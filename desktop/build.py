"""python desktop/build.py --manifest or --exe OUTPUT (Go on PATH)."""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import uuid
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
VERSION = "V" + json.loads((ROOT / "package.json").read_text())["version"].removesuffix(".0")
RUNTIME_URL = "https://www.python.org/ftp/python/3.13.9/python-3.13.9-embed-amd64.zip"
RUNTIME_SHA = "91d828c2da3a029b41699e918674a0cb379c02cf20dab9c501306885f837402a"


def manifest():
    files = [ROOT / name for name in ("README.md", "monitor.py", "web/index.html", "templates/Vagas_template.xlsx")]
    files += list((ROOT / "radar").glob("*.py")) + list((ROOT / "web/assets").glob("*"))
    return {"version": VERSION, "files": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files) if p.is_file()}}


def shortcut(target):
    # MS-SHLLINK. Only RelativePath and IsUnicode are set. Explorer resolves
    # the target relative to the .lnk even after the extracted folder moves.
    clsid = uuid.UUID("00021401-0000-0000-C000-000000000046").bytes_le
    header = struct.pack("<I16sIIQQQIiIHHII", 76, clsid, 0x88, 0x20,
                         0, 0, 0, 0, 0, 1, 0, 0, 0, 0)
    path = target.encode("utf-16le")
    return header + struct.pack("<H", len(path)//2) + path + bytes(4)


def build(dest, runtime, package=False):
    info = manifest()
    if info != json.loads((ROOT / "desktop-release.json").read_text()):
        raise SystemExit("Atualize desktop-release.json com --manifest.")
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        if runtime is None:
            runtime = work / "python.zip"
            with urlopen(RUNTIME_URL, timeout=60) as response:
                runtime.write_bytes(response.read())
        if hashlib.sha256(runtime.read_bytes()).hexdigest() != RUNTIME_SHA:
            raise SystemExit("Checksum do Python incompatível.")
        dest = dest.resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        # The legacy --exe mode embeds the runtime. The ZIP ships it next to
        # the executable so the project and its dependencies are accessible.
        with zipfile.ZipFile(work/"bundle.zip", "w", zipfile.ZIP_DEFLATED) as out, zipfile.ZipFile(runtime) as source:
            if not package:
                for member in source.namelist():
                    out.writestr("python/" + member, source.read(member))
                for name in [*info["files"], "desktop-release.json"]:
                    out.write(ROOT / name, "app/" + name)
                out.write(ROOT / "desktop/start.py", "desktop/start.py")
        shutil.copy(ROOT / "desktop/launcher_windows.go", work)
        exe = work / "Radar de Vagas.exe" if package else dest
        flags = f"-s -w -H=windowsgui -X main.release={VERSION}"
        if package:
            flags += " -X main.layout=folder"
        subprocess.run(["go","build","-trimpath","-ldflags",flags,
                        "-o",str(exe),"launcher_windows.go"], cwd=work,
                       env={**os.environ,"GOOS":"windows","GOARCH":"amd64","CGO_ENABLED":"0"}, check=True)
        if package:
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as out, zipfile.ZipFile(runtime) as source:
                out.writestr("Radar de Vagas.lnk", shortcut(r".\Projeto\Radar de Vagas.exe"))
                out.write(exe, "Projeto/" + exe.name)
                for member in source.namelist():
                    out.writestr("Projeto/python/" + member, source.read(member))
                files = [*info["files"], "desktop-release.json", "desktop/start.py",
                         "desktop/build.py", "desktop/launcher_windows.go", "package.json",
                         "web/build_tailwind.js", "agendar_buscas.ps1", "buscar_vagas.bat",
                         "abrir_painel.bat", "data/.gitkeep"]
                for name in files:
                    out.write(ROOT / name, "Projeto/" + name)
                for test in sorted((ROOT / "tests").glob("*.py")):
                    out.write(test, "Projeto/tests/" + test.name)



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest", action="store_true")
    mode.add_argument("--exe", type=Path)
    mode.add_argument("--package", type=Path)
    parser.add_argument("--runtime", type=Path)
    args = parser.parse_args()
    if args.manifest:
        (ROOT / "desktop-release.json").write_text(json.dumps(manifest(), indent=2) + "\n", "utf8")
    else:
        build(args.exe or args.package, args.runtime, package=args.package is not None)
