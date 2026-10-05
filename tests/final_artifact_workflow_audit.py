"""Offline end-to-end tests against the actual Windows and extracted Termux packages.

Runs no update checks and never rebuilds or mutates distribution artifacts.
All input/output APKs and server state are disposable local test data.
"""
from __future__ import annotations

import hashlib
import argparse
import json
import os
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path
from deep_asset_fixture import AD_DEX, NESTED_AD_DEX, RETAINED_DEX, build_asset_fixture
from test_app_appearance import image

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.6.3-dev.4"
FIXTURE = ROOT / "work/hello-with-ad-call.apk"
OUTPUTS = ROOT / "outputs"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def http(base, route, body=None, content_type="application/json"):
    request = urllib.request.Request(base + route, data=body, headers={
        "X-Client-ID": "dev4-final-artifact-audit", "Content-Type": content_type,
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def wait_job(base, job_id):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        result = json.loads(http(base, f"/api/jobs/{job_id}/state"))
        if result["status"] in {"done", "error", "cancelled"}:
            return result
        time.sleep(0.1)
    raise RuntimeError("Packaged workflow timed out")


def packaged_server(label, command, folder, asset_fixture, user_fixture=None, selected_cases=None):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(folder / "appdata")
    environment["APK_CLEANER_DATA_ROOT"] = str(folder / "data")
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    with (folder / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command + ["--host", "127.0.0.1", "--port", str(port), "--no-open", "--no-trust-prompt"],
                                   env=environment, cwd=folder, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        try:
            deadline = time.monotonic() + 35
            while True:
                try:
                    status = json.loads(http(base, "/api/status"))
                    break
                except Exception:
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(f"{label}: packaged server did not start")
                    time.sleep(0.1)
            assert status["version"] == VERSION, status
            assert status["toolchain"]["fully_ready"], status
            boundary = "----FinalArtifactAudit" + uuid.uuid4().hex
            def upload_job(source=FIXTURE):
                prefix = (f'--{boundary}\r\nContent-Disposition: form-data; name="package"; filename="final-audit{source.suffix}"\r\n'
                          'Content-Type: application/vnd.android.package-archive\r\n\r\n').encode()
                body = prefix + source.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
                uploaded = json.loads(http(base, "/api/analyze", body, f"multipart/form-data; boundary={boundary}"))
                return uploaded["job_id"]
            cases = (
                ("version_only", {"patch_ads": False}),
                ("deep_clean_and_version", {"patch_ads": True, "profile": "deep"}),
                ("clone_clean_and_version", {"patch_ads": True, "operation": "clone", "clone_package_name": "com.example.finalaudit.clone"}),
                ("res_normalization_and_version", {"patch_ads": False, "normalize_dex": True, "deobfuscate_resources": True, "optimize_apk": True}),
                ("deep_asset_dex", {"_asset_fixture": True, "patch_ads": True, "profile": "deep", "restrict_store_updates": False}),
                ("balanced_asset_dex", {"_asset_fixture": True, "patch_ads": True, "profile": "balanced", "restrict_store_updates": False, "normalize_dex": True}),
                ("deep_asset_clone_and_version", {"_asset_fixture": True, "patch_ads": True, "profile": "deep", "operation": "clone", "clone_package_name": "com.example.finalaudit.clone"}),
                ("deep_asset_res_and_version", {"_asset_fixture": True, "patch_ads": True, "profile": "deep", "deobfuscate_resources": True, "optimize_apk": True}),
                ("appearance_name_only", {"patch_ads": False, "restrict_store_updates": False, "app_appearance": {"name": "Yeni uygulama adı"}}),
                ("appearance_icon_only", {"patch_ads": False, "restrict_store_updates": False, "app_appearance": {"icon": image()}}),
                ("appearance_clone_clean_version", {"patch_ads": True, "profile": "deep", "operation": "clone", "clone_package_name": "com.example.finalaudit.appearance", "app_appearance": {"name": "Özel klon", "icon": image()}}),
                ("appearance_resource_edits", {"patch_ads": False, "deobfuscate_resources": True, "optimize_apk": True, "app_appearance": {"name": "Kaynak düzenleme", "icon": image()}}),
                ("split_appearance_clone", {"_split_fixture": True, "patch_ads": False, "operation": "clone", "clone_package_name": "com.example.finalaudit.split", "app_appearance": {"name": "Split klon", "icon": image()}}),
            )
            if user_fixture:
                cases += (("original_user_deep_apk", {"_user_fixture": True, "patch_ads": True, "profile": "deep", "restrict_store_updates": False}),)
            if selected_cases:
                assert set(selected_cases).issubset({name for name, _ in cases}), selected_cases
                cases = tuple(row for row in cases if row[0] in selected_cases)
            results = []
            job_ids = []
            for name, options in cases:
                print(f"Starting {label}: {name}", flush=True)
                # Completed jobs are deliberately idempotent. Each choice needs a fresh analysis.
                options = dict(options)
                source = asset_fixture if options.pop("_asset_fixture", False) else FIXTURE
                if options.pop("_split_fixture", False):
                    source = ROOT / "work/ui-split-preview.apks"
                if options.pop("_user_fixture", False):
                    source = user_fixture
                job_id = upload_job(source)
                job_ids.append(job_id)
                payload = {"job_id": job_id, "operation": "patch", "profile": "balanced", "restrict_store_updates": True, **options}
                accepted = json.loads(http(base, "/api/clean", json.dumps(payload).encode()))
                assert accepted["job_id"] == job_id, accepted
                finished = wait_job(base, job_id)
                if finished["status"] != "done":
                    diagnostic_path = folder / "data" / "jobs" / job_id / "diagnostic.json"
                    if diagnostic_path.exists():
                        print(json.dumps(json.loads(diagnostic_path.read_text(encoding="utf-8")), ensure_ascii=True), flush=True)
                assert finished["status"] == "done", finished
                result = finished["result"]
                assert result["signed"] and result["verification"]["passed"], result
                if payload["restrict_store_updates"]:
                    assert result["store_updates"]["version_code_after"] >= 2100000000, result
                else:
                    assert result["store_updates"] is None, result
                assert result["source_size_bytes"] == source.stat().st_size, result
                apk_bytes = http(base, f"/api/jobs/{job_id}/download")
                assert len(apk_bytes) == result["output_size_bytes"], result
                target = folder / (name + ".apk")
                target.write_bytes(apk_bytes)
                sys.path.insert(0, str(ROOT / "studio"))
                from package_info import inspect_package_info
                from package_icon import extract_apk_icon
                metadata = inspect_package_info(target)
                assert "permissions" in metadata and "signature_schemes" in metadata, metadata
                appearance = payload.get("app_appearance")
                if appearance:
                    assert result["app_appearance"]["name"] == appearance.get("name"), result
                    assert result["app_appearance"]["icon_changed"] == bool(appearance.get("icon")), result
                    if appearance.get("name"):
                        assert metadata["app_name"] == appearance["name"], metadata
                    if appearance.get("icon"):
                        assert extract_apk_icon(target) == appearance["icon"]
                with zipfile.ZipFile(target) as archive:
                    assert archive.testzip() is None
                    assert "AndroidManifest.xml" in archive.namelist()
                    assert "classes.dex" in archive.namelist()
                    if source == asset_fixture:
                        assert b"AssetKept" in archive.read(RETAINED_DEX)
                        assert b"AssetOne" not in archive.read("classes.dex")
                        rows = {row["file"]: row for row in result["changes"]["dex"]}
                        for entry in (AD_DEX, NESTED_AD_DEX):
                            if payload["profile"] == "deep":
                                assert entry not in archive.namelist()
                                assert rows[entry]["removed"] and rows[entry]["after"] is None
                            else:
                                assert entry in archive.namelist()
                                assert not rows[entry].get("removed", False)
                    if source == user_fixture:
                        assert AD_DEX not in archive.namelist()
                        removed = next(row for row in result["changes"]["dex"] if row["file"] == AD_DEX)
                        assert removed["removed"] and removed["after"] is None
                report = http(base, f"/api/jobs/{job_id}/report").decode("utf-8")
                if payload["restrict_store_updates"]:
                    assert "2100000000" in report and "Play Store" in report, report
                if (source == asset_fixture or source == user_fixture) and payload["profile"] == "deep":
                    assert f"{AD_DEX}: kaldırıldı" in report, report
                if payload["operation"] == "clone":
                    assert result["clone"]["new_package"] == options["clone_package_name"]
                expected_package = options.get("clone_package_name", result["package_name"])
                assert result["identity_comparison"]["after"]["package_name"] == expected_package, result
                if name == "version_only":
                    with zipfile.ZipFile(FIXTURE) as source, zipfile.ZipFile(target) as output:
                        assert source.read("classes.dex") == output.read("classes.dex")
                results.append({"case": name, "signed": True, "verified": True, "report": True,
                                "appearance_checked": bool(appearance), "compatibility_metadata": True,
                                "download_size_matches": True, "asset_dex_fixture": source == asset_fixture,
                                "version_code": result["store_updates"]["version_code_after"] if result["store_updates"] else None})
            # A malformed opt-in must produce a useful diagnostic, not a silent success.
            job_id = upload_job()
            job_ids.append(job_id)
            http(base, "/api/clean", json.dumps({"job_id": job_id, "patch_ads": False, "restrict_store_updates": "true"}).encode())
            failed = wait_job(base, job_id)
            assert failed["status"] == "error" and "Play Store" in failed["message"], failed
            diagnostic = http(base, f"/api/jobs/{job_id}/diagnostic").decode("utf-8")
            assert "Play Store" in diagnostic and "geçersiz" in diagnostic, diagnostic
            for job_id in job_ids:
                deleted = json.loads(http(base, f"/api/jobs/{job_id}/delete", b""))
                assert deleted["ok"], deleted
            return {"package": label, "cases": results, "safe_diagnostic": True, "history_delete": True}
        except Exception:
            log.flush()
            diagnostic_log = (folder / "server.log").read_bytes()[-14000:].decode("utf-8", errors="replace")
            print(diagnostic_log.encode("ascii", errors="backslashreplace").decode("ascii"), flush=True)
            raise
        finally:
            if process.poll() is None:
                if hasattr(signal, "CTRL_BREAK_EVENT"):
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            with socket.socket() as probe:
                assert probe.connect_ex(("127.0.0.1", port)) != 0, "Packaged child server remained alive"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-apk", type=Path)
    parser.add_argument("--case", action="append", dest="selected_cases")
    args = parser.parse_args()
    user_fixture = args.user_apk
    user_digest = digest(user_fixture) if user_fixture else None
    artifacts = [OUTPUTS / f"APK-Cleaner-Studio-v{VERSION}-{platform}.{extension}"
                 for platform, extension in (("Android", "apk"), ("Windows", "exe"), ("Termux", "zip"))]
    before = {str(path): digest(path) for path in artifacts}
    fixture_digest = digest(FIXTURE)
    with tempfile.TemporaryDirectory(prefix="apkcleaner-final-artifacts-") as temporary:
        root = Path(temporary)
        fixture_folder = root / "fixture"
        asset_fixture = build_asset_fixture(fixture_folder, shutil.which("java"))
        asset_digest = digest(asset_fixture)
        windows = root / "windows"
        windows.mkdir()
        summaries = [packaged_server("Windows EXE", [str(artifacts[1])], windows, asset_fixture, user_fixture, args.selected_cases)]
        termux = root / "termux"
        termux.mkdir()
        with zipfile.ZipFile(artifacts[2]) as archive:
            # Archive content already passed package_audit's path/credential checks.
            for entry in archive.namelist():
                resolved = (termux / entry).resolve()
                assert resolved.is_relative_to(termux.resolve()), entry
            archive.extractall(termux)
        summaries.append(packaged_server("Extracted Termux engine on Windows host", [sys.executable, str(termux / "studio/server.py")], termux, asset_fixture, user_fixture, args.selected_cases))
        assert digest(asset_fixture) == asset_digest, "Asset DEX fixture changed"
    assert digest(FIXTURE) == fixture_digest, "Original APK fixture changed"
    assert not user_fixture or digest(user_fixture) == user_digest, "Original user APK changed"
    assert {str(path): digest(path) for path in artifacts} == before, "Distribution artifacts changed during testing"
    print(json.dumps({"artifacts_unchanged": True, "source_unchanged": True, "results": summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
