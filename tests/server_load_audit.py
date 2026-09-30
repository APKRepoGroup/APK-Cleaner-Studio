"""HTTP/HTTPS concurrency and shutdown audit for the local manager server."""

from __future__ import annotations

import json
import os
import socket
import ssl
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def fetch(url: str) -> tuple[int, float, dict]:
    started = time.perf_counter()
    context = ssl._create_unverified_context() if url.startswith("https:") else None
    request = urllib.request.Request(url, headers={"Accept": "application/json", "X-Client-ID": "a" * 24})
    with urllib.request.urlopen(request, timeout=5, context=context) as response:
        payload = json.loads(response.read())
        return response.status, (time.perf_counter() - started) * 1000, payload


def main() -> int:
    port = free_port()
    command = [
        sys.executable,
        str(ROOT / "studio" / "server.py"),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--no-open",
        "--no-trust-prompt",
    ]
    audit_data = tempfile.TemporaryDirectory(prefix="apk-cleaner-load-audit-")
    environment = os.environ.copy()
    environment["APK_CLEANER_DATA_ROOT"] = audit_data.name
    try:
        process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except Exception:
        audit_data.cleanup()
        raise
    urls = [f"http://127.0.0.1:{port}/api/status", f"https://127.0.0.1:{port}/api/status"]
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                fetch(urls[0])
                break
            except Exception:
                if process.poll() is not None:
                    raise RuntimeError(process.stdout.read() if process.stdout else "Sunucu erken kapandı.")
                if time.monotonic() > deadline:
                    raise RuntimeError("Sunucu zamanında hazır olmadı.")
                time.sleep(0.1)

        targets = [urls[index % 2] for index in range(400)]
        with ThreadPoolExecutor(max_workers=40) as pool:
            results = list(pool.map(fetch, targets))
        failures = [row for row in results if row[0] != 200 or row[2].get("version") != "0.6.3-dev.3"]
        if failures:
            raise RuntimeError(f"Yük testinde {len(failures)} hatalı yanıt alındı.")
        latencies = sorted(row[1] for row in results)
        summary = {
            "requests": len(results),
            "concurrency": 40,
            "http_requests": 200,
            "https_requests": 200,
            "failures": 0,
            "latency_ms": {
                "average": round(statistics.mean(latencies), 2),
                "p50": round(latencies[len(latencies) // 2], 2),
                "p95": round(latencies[int(len(latencies) * 0.95) - 1], 2),
                "max": round(max(latencies), 2),
            },
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if process.poll() is None:
            raise RuntimeError("Sunucu süreci kapanmadı.")
        audit_data.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
