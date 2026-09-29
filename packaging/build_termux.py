from __future__ import annotations

import zipfile
from pathlib import Path

from build_java_tools import main as build_java_tools

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "APK-Cleaner-Studio-v0.6.3-dev.2-Termux.zip"
ROOT_FILES = (
    "install-termux.sh",
    "README-TERMUX.md",
    "README-TR.md",
    "README.md",
    "RELEASE-NOTES-v0.6.3-dev.2.md",
    "start-termux.sh",
    "THIRD-PARTY-NOTICES.md",
    "VERSION.txt",
)


def should_include(relative: Path) -> bool:
    runtime_job = relative.parts[:2] == ("studio", "jobs")
    runtime_tls = relative.parts[:2] == ("studio", "tls")
    runtime_updates = relative.parts[:2] == ("studio", "updates")
    runtime_state = relative.as_posix() in {
        "studio/blocked-clients.json",
        "studio/client-labels.json",
    }
    generated_cache = "__pycache__" in relative.parts or relative.suffix == ".pyc"
    transient = relative.suffix in {".part", ".tmp"}
    return not any((runtime_job, runtime_tls, runtime_updates, runtime_state, generated_cache, transient))


def main() -> None:
    build_java_tools()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".zip.part")
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
    temporary.replace(OUTPUT)


if __name__ == "__main__":
    main()
