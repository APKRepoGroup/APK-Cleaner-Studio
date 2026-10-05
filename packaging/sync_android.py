from __future__ import annotations

import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android" / "app"
PYTHON = ANDROID / "src" / "main" / "python"
LIBS = ANDROID / "libs"
RES = ANDROID / "src" / "main" / "res"
ASSETS = ANDROID / "src" / "main" / "assets"
STUDIO = ROOT / "studio"

PYTHON_FILES = (
    "engine.py",
    "package_icon.py",
    "app_appearance.py",
    "package_info.py",
    "server.py",
    "setup_tools.py",
    "updater.py",
    "device_catalog.py",
    "profiles.json",
    "device-catalog.json",
    "update-channel.json",
)


def copy_engine() -> None:
    PYTHON.mkdir(parents=True, exist_ok=True)
    # Yerel testler kaynak klasöründe __pycache__ bırakabilir. Chaquopy bunları
    # kullanmaz; senkronizasyondan önce temizlemek kaynak ağacını ve olası
    # gelecekteki paketleme girdilerini gereksiz derleme artıklarından arındırır.
    for cache_dir in PYTHON.rglob("__pycache__"):
        shutil.rmtree(cache_dir)
    for bytecode in PYTHON.rglob("*.py[co]"):
        bytecode.unlink()
    for name in PYTHON_FILES:
        shutil.copy2(STUDIO / name, PYTHON / name)
    target_web = PYTHON / "web"
    if target_web.exists():
        shutil.rmtree(target_web)
    shutil.copytree(STUDIO / "web", target_web)


def filtered_jar(source: Path, destination: Path, excluded_prefixes: tuple[str, ...]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            name = info.filename
            upper = name.upper()
            if name.endswith("/"):
                continue
            if any(name.startswith(prefix) for prefix in excluded_prefixes):
                continue
            if upper.startswith("META-INF/") and upper.endswith((".SF", ".RSA", ".DSA")):
                continue
            dst.writestr(info, src.read(name))


def copy_tools() -> None:
    tools = STUDIO / "tools"
    LIBS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tools / "direct-dex-patcher.jar", LIBS / "direct-dex-patcher.jar")
    shutil.copy2(tools / "binary-xml-patcher.jar", LIBS / "binary-xml-patcher.jar")
    filtered_jar(
        tools / "dexlib2-runtime.jar",
        LIBS / "dexlib2-runtime-android.jar",
        ("javax/annotation/Nonnull.class", "javax/annotation/Nullable.class"),
    )
    filtered_jar(
        tools / "APKEditor.jar",
        LIBS / "APKEditor-android.jar",
        (
            "android/",
            "META-INF/versions/",
            "module-info.class",
            "org/xmlpull/v1/",
            "strings/strings-ar.properties",
            "strings/strings-fr.properties",
        ),
    )
    ASSETS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tools / "output-signing.p12", ASSETS / "output-signing.p12")


def copy_icons() -> None:
    source = STUDIO / "web" / "favicon.png"
    for density in ("xhdpi", "xxhdpi"):
        folder = RES / f"mipmap-{density}"
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, folder / "ic_launcher.png")
        shutil.copy2(source, folder / "ic_launcher_round.png")


def main() -> None:
    if ROOT not in ANDROID.parents:
        raise RuntimeError("Android hedefi çalışma alanının dışında.")
    copy_engine()
    copy_tools()
    copy_icons()
    print("Android motoru, web arayüzü ve gömülü araçlar eşitlendi.")


if __name__ == "__main__":
    main()
