# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

project = Path.cwd()

a = Analysis(
    [str(project / "studio" / "desktop.py")],
    pathex=[str(project / "studio")],
    binaries=[],
    datas=collect_data_files("webview", subdir="js") + [
        (str(project / "studio" / "web"), "web"),
        (str(project / "studio" / "desktop"), "desktop"),
        (str(project / "public" / "favicon.ico"), "desktop"),
        (str(project / "studio" / "profiles.json"), "."),
        (str(project / "studio" / "update-channel.json"), "."),
        (str(project / "studio" / "device-catalog.json"), "."),
        (str(project / "studio" / "tools" / "APKEditor.jar"), "tools"),
        (str(project / "studio" / "tools" / "dexlib2-runtime.jar"), "tools"),
        (str(project / "studio" / "tools" / "direct-dex-patcher.jar"), "tools"),
        (str(project / "studio" / "tools" / "binary-xml-patcher.jar"), "tools"),
        (str(project / "studio" / "tools" / "uber-apk-signer.jar"), "tools"),
        (str(project / "studio" / "tools" / "zipalign-win.exe"), "tools"),
        (str(project / "studio" / "tools" / "output-signing.p12"), "tools"),
    ],
    hiddenimports=["webview.platforms.winforms", "webview.platforms.edgechromium", "webview.platforms.win32", "clr", "clr_loader", "_cffi_backend"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "PySide6", "qtpy", "gi", "gtk", "webview.platforms.android", "webview.platforms.cocoa", "webview.platforms.gtk", "webview.platforms.qt"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="APK-Cleaner-Studio-v0.6.3-dev.6-Windows",
    icon=str(project / "public" / "favicon.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
