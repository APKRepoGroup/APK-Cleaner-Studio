"""Generate valid nested DEX entries with equal basenames for local regression QA."""
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
AD_DEX = "assets/audience_network/classes.dex"
NESTED_AD_DEX = "assets/audience_network/cache/classes2.dex"
RETAINED_DEX = "assets/local/classes.dex"


def build_asset_fixture(folder: Path, java: str) -> Path:
    source = ROOT / "work/hello-with-ad-call.apk"
    payloads = {}
    for index, (entry, label) in enumerate(((AD_DEX, "AssetOne"), (NESTED_AD_DEX, "AssetNested"),
                                          (RETAINED_DEX, "AssetKept"))):
        tree = folder / f"smali-{index}"
        tree.mkdir(parents=True)
        marker = "Lcom/facebook/ads/AdView;" if entry != RETAINED_DEX else "Ljava/lang/String;"
        (tree / f"{label}.smali").write_text(
            f".class public Lfixture/{label};\n.super Ljava/lang/Object;\n"
            ".method public static run()V\n.registers 1\n"
            f"const-class v0, {marker}\nreturn-void\n.end method\n", encoding="utf-8")
        dex = folder / f"asset-{index}.dex"
        subprocess.run([java, "-cp", str(ROOT / "studio/tools/APKEditor.jar"), "org.jf.smali.Main",
                        "assemble", str(tree), "-o", str(dex)], check=True, capture_output=True, timeout=30)
        payloads[entry] = dex.read_bytes()
    target = folder / "asset-dex-regression.apk"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w") as output:
        for info in original.infolist():
            output.writestr(info, original.read(info))
        for entry, payload in payloads.items():
            output.writestr(entry, payload)
        output.writestr("assets/audience_network/config.json", b'{"fixture":true}')
    return target
