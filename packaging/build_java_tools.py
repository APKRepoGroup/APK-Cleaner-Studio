"""Compile the two small Java adapters before packaging a new release.

This does not build the Android/Windows/Termux application packages. It keeps
the bundled adapters in sync with their checked-in Java sources.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


# Keep the short SUBST path supplied by build-android.ps1. Resolving it back
# to the long physical path triggers JDK 21 zipfs AccessDenied on Windows.
ROOT = Path(__file__).absolute().parents[1]
TOOLS = ROOT / "studio" / "tools"


def javac_path() -> str:
    java_home = os.environ.get("JAVA_HOME")
    executable = "javac.exe" if os.name == "nt" else "javac"
    if java_home:
        candidate = Path(java_home) / "bin" / executable
        if candidate.is_file():
            return str(candidate)
    command = shutil.which("javac")
    if command:
        return command
    raise RuntimeError("JDK javac bulunamadı; JAVA_HOME değerini ayarla.")


def compile_adapter(name: str, source_dir: Path, dependencies: tuple[str, ...]) -> None:
    sources = sorted(source_dir.rglob("*.java"))
    if not sources:
        raise RuntimeError(f"Java kaynakları bulunamadı: {source_dir}")
    with tempfile.TemporaryDirectory(prefix="apkcleaner-java-") as temp_name:
        classes = Path(temp_name) / "classes"
        classes.mkdir()
        command = [javac_path(), "--release", "8", "-encoding", "UTF-8", "-d", str(classes)]
        if dependencies:
            # javac's ZIP file manager may fail while closing dependencies on
            # long Windows workspace paths. Compile against private short-path
            # copies, never rename or modify the bundled dependency JARs.
            dependency_dir = Path(temp_name) / "dependencies"
            dependency_dir.mkdir()
            for item in dependencies:
                shutil.copy2(TOOLS / item, dependency_dir / item)
            command.extend(("-classpath", os.pathsep.join(str(dependency_dir / item) for item in dependencies)))
        command.extend(str(source) for source in sources)
        subprocess.run(command, check=True, cwd=ROOT)

        target = TOOLS / name
        staged = Path(temp_name) / name
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            def add_file(entry_name: str, payload: bytes) -> None:
                info = zipfile.ZipInfo(entry_name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, payload)

            add_file("META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\r\nCreated-By: APK Cleaner Studio\r\n\r\n")
            for compiled in sorted(classes.rglob("*.class")):
                add_file(compiled.relative_to(classes).as_posix(), compiled.read_bytes())
        shutil.copy2(staged, target.with_suffix(".jar.new"))
        target.with_suffix(".jar.new").replace(target)


def main() -> None:
    compile_adapter("direct-dex-patcher.jar", ROOT / "direct-patcher" / "src", ("dexlib2-runtime.jar",))
    compile_adapter("binary-xml-patcher.jar", ROOT / "binary-xml-patcher" / "src", ("APKEditor.jar",))


if __name__ == "__main__":
    main()
