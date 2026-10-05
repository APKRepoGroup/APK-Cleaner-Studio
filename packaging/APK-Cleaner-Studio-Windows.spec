# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project = Path.cwd()

a = Analysis(
    [str(project / "studio" / "server.py")],
    pathex=[str(project / "studio")],
    binaries=[],
    datas=[
        (str(project / "studio" / "web"), "web"),
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
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="APK-Cleaner-Studio-v0.6.3-dev.4-Windows",
    icon=str(project / "public" / "favicon.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
