from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from build_java_tools import main as build_java_tools

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "APK-Cleaner-Studio-v0.6.3-dev.7-Termux.zip"
ROOT_FILES = (
    "install-termux.sh",
    "README-TERMUX.md",
    "README-TR.md",
    "README.md",
    "RELEASE-NOTES-v0.6.3-dev.7.md",
    "start-termux.sh",
    "THIRD-PARTY-NOTICES.md",
    "VERSION.txt",
)
WINDOWS_SHELL_FILES = frozenset({
    "desktop.py", "desktop_network.py", "desktop_output.py", "desktop_pairing.py",
    "desktop_preferences.py", "windows_shell.py",
})


def should_include(relative: Path) -> bool:
    runtime_job = relative.parts[:2] == ("studio", "jobs")
    runtime_tls = relative.parts[:2] == ("studio", "tls")
    runtime_updates = relative.parts[:2] == ("studio", "updates")
    runtime_state = relative.as_posix() in {
        "studio/blocked-clients.json",
        "studio/client-labels.json",
    }
    generated_cache = "__pycache__" in relative.parts or relative.suffix == ".pyc"
    transient = relative.suffix.casefold() in {".part", ".tmp", ".new"}
    desktop_shell = relative.parts[:2] == ("studio", "desktop") or (
        len(relative.parts) == 2 and relative.name in WINDOWS_SHELL_FILES
    )
    return not any((runtime_job, runtime_tls, runtime_updates, runtime_state, generated_cache, transient, desktop_shell))


def main(output: Path = OUTPUT) -> None:
    build_java_tools()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".zip.part")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in ROOT_FILES:
            path = ROOT / name
            if not path.is_file():
                raise FileNotFoundError(f"Termux paket dosyası bulunamadı: {path}")
            archive.write(path, name)

        for path in sorted((ROOT / "studio").rglob("*")):
            relative = path.relative_to(ROOT)
            if path.is_file() and should_include(relative):
                archive.write(path, relative.as_posix())
    temporary.replace(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Termux ZIP dosyasının yolu")
    main(parser.parse_args().output)
