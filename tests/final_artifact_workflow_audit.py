"""Offline end-to-end tests against the actual Windows and extracted Termux packages.

Runs no update checks and never rebuilds or mutates distribution artifacts.
All input/output APKs and server state are disposable local test data.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.6.3-dev.3"
FIXTURE = ROOT / "work/hello-with-ad-call.apk"
OUTPUTS = ROOT / "outputs"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def http(base, route, body=None, content_type="application/json"):
    request = urllib.request.Request(base + route, data=body, headers={
        "X-Client-ID": "dev3-final-artifact-audit", "Content-Type": content_type,
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


def packaged_server(label, command, folder):
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
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="package"; filename="final-audit.apk"\r\n'
                    'Content-Type: application/vnd.android.package-archive\r\n\r\n').encode()
            body += FIXTURE.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
            def upload_job():
                uploaded = json.loads(http(base, "/api/analyze", body, f"multipart/form-data; boundary={boundary}"))
                return uploaded["job_id"]
            cases = (
                ("version_only", {"patch_ads": False}),
                ("deep_clean_and_version", {"patch_ads": True, "profile": "deep"}),
                ("clone_clean_and_version", {"patch_ads": True, "operation": "clone", "clone_package_name": "com.example.finalaudit.clone"}),
                ("res_normalization_and_version", {"patch_ads": False, "normalize_dex": True, "deobfuscate_resources": True, "optimize_apk": True}),
            )
            results = []
            job_ids = []
            for name, options in cases:
                # Completed jobs are deliberately idempotent. Each choice needs a fresh analysis.
                job_id = upload_job()
                job_ids.append(job_id)
                payload = {"job_id": job_id, "operation": "patch", "profile": "balanced", "restrict_store_updates": True, **options}
                accepted = json.loads(http(base, "/api/clean", json.dumps(payload).encode()))
                assert accepted["job_id"] == job_id, accepted
                finished = wait_job(base, job_id)
                assert finished["status"] == "done", finished
                result = finished["result"]
                assert result["signed"] and result["verification"]["passed"], result
                assert result["store_updates"]["version_code_after"] >= 2100000000, result
                assert result["source_size_bytes"] == FIXTURE.stat().st_size, result
                apk_bytes = http(base, f"/api/jobs/{job_id}/download")
                assert len(apk_bytes) == result["output_size_bytes"], result
                target = folder / (name + ".apk")
                target.write_bytes(apk_bytes)
                with zipfile.ZipFile(target) as archive:
                    assert archive.testzip() is None
                    assert "AndroidManifest.xml" in archive.namelist()
                    assert "classes.dex" in archive.namelist()
                report = http(base, f"/api/jobs/{job_id}/report").decode("utf-8")
                assert "2100000000" in report and "Play Store" in report, report
                if name == "clone_clean_and_version":
                    assert result["clone"]["new_package"] == options["clone_package_name"]
                if name == "version_only":
                    with zipfile.ZipFile(FIXTURE) as source, zipfile.ZipFile(target) as output:
                        assert source.read("classes.dex") == output.read("classes.dex")
                results.append({"case": name, "signed": True, "verified": True, "report": True,
                                "download_size_matches": True, "version_code": result["store_updates"]["version_code_after"]})
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
    artifacts = [OUTPUTS / f"APK-Cleaner-Studio-v{VERSION}-{platform}.{extension}"
                 for platform, extension in (("Android", "apk"), ("Windows", "exe"), ("Termux", "zip"))]
    before = {str(path): digest(path) for path in artifacts}
    fixture_digest = digest(FIXTURE)
    with tempfile.TemporaryDirectory(prefix="apkcleaner-final-artifacts-") as temporary:
        root = Path(temporary)
        windows = root / "windows"
        windows.mkdir()
        summaries = [packaged_server("Windows EXE", [str(artifacts[1])], windows)]
        termux = root / "termux"
        termux.mkdir()
        with zipfile.ZipFile(artifacts[2]) as archive:
            # Archive content already passed package_audit's path/credential checks.
            for entry in archive.namelist():
                resolved = (termux / entry).resolve()
                assert resolved.is_relative_to(termux.resolve()), entry
            archive.extractall(termux)
        summaries.append(packaged_server("Extracted Termux engine on Windows host", [sys.executable, str(termux / "studio/server.py")], termux))
    assert digest(FIXTURE) == fixture_digest, "Original APK fixture changed"
    assert {str(path): digest(path) for path in artifacts} == before, "Distribution artifacts changed during testing"
    print(json.dumps({"artifacts_unchanged": True, "source_unchanged": True, "results": summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
