"""Launch packaged smoke tests in an isolated, loopback-only session."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import urllib.request
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_open(request, timeout=5):
    url = request.full_url if isinstance(request, urllib.request.Request) else request
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.username is not None:
        raise ValueError('Paket testi yalnızca yerel HTTP adresine bağlanabilir.')
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=timeout)


def launch_arguments(command, port, native):
    if native:
        return [*command, '--port', '0']
    return [*command, '--host', '127.0.0.1', '--port', str(port), '--no-open', '--no-trust-prompt']


def _free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def _native_ready_address(path):
    try:
        session = json.loads(path.read_text(encoding='utf-8'))
        address = urlsplit(session['url'])
        if (session['state'] == 'ready' and address.scheme == 'http'
                and address.hostname == '127.0.0.1' and address.port
                and address.netloc == f'127.0.0.1:{address.port}'):
            return f'http://{address.netloc}'
    except (OSError, KeyError, TypeError, ValueError):
        pass
    return None


def _stop_process(process, native):
    if process.poll() is not None:
        return
    if native:
        # PyInstaller's windowed one-file application has no console to signal.
        # Stop only the process tree created by this fixture.
        subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                       capture_output=True, timeout=10, check=False)
    elif os.name == 'nt':
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _wait_port_closed(port):
    deadline = time.monotonic() + 4
    while True:
        with socket.socket() as probe:
            probe.settimeout(0.3)
            if probe.connect_ex(('127.0.0.1', port)) != 0:
                return
        if time.monotonic() >= deadline:
            raise RuntimeError('Test süreci kapandıktan sonra yerel port açık kaldı.')
        time.sleep(0.12)


@contextmanager
def local_package_server(command, folder, *, native=False, update_fixture=None):
    folder = Path(folder).resolve()
    data = folder / 'data'
    block_proxy = 'http://127.0.0.1:1'
    environment = dict(os.environ, LOCALAPPDATA=str(folder / 'appdata'), APK_CLEANER_DATA_ROOT=str(data),
                       HTTP_PROXY=block_proxy, HTTPS_PROXY=block_proxy, ALL_PROXY=block_proxy,
                       NO_PROXY='127.0.0.1,localhost', WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=f'--proxy-server={block_proxy}')
    if update_fixture:
        if set(update_fixture) - {'APK_CLEANER_UPDATE_URL', 'SSL_CERT_FILE', 'SSLKEYLOGFILE'}:
            raise ValueError('Only local HTTPS fixture settings may override the child environment.')
        address = urlsplit(update_fixture.get('APK_CLEANER_UPDATE_URL', ''))
        if address.scheme != 'https' or address.hostname != '127.0.0.1' or address.username is not None:
            raise ValueError('Update fixture must use loopback HTTPS.')
        # Fault injection belongs to the child, not to this test client's TLS.
        environment.update(update_fixture)
    base = None if native else f'http://127.0.0.1:{_free_port()}'
    port = urlsplit(base).port if base else 0
    session_path = data / 'logs/desktop-session.json'
    log_path = folder / 'server.log'
    with log_path.open('w', encoding='utf-8') as log:
        process = subprocess.Popen(launch_arguments(command, port, native), cwd=folder, env=environment,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
        try:
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline and process.poll() is None:
                if native:
                    base = _native_ready_address(session_path)
                if base:
                    try:
                        with local_open(base + '/api/status', timeout=1) as reply:
                            status = json.load(reply)
                    except (OSError, ValueError):
                        pass
                    else:
                        port = urlsplit(base).port
                        break
                time.sleep(0.12)
            else:
                raise RuntimeError('Paketin yerel sunucusu hazır duruma gelmedi.')
            yield base, status
        except Exception:
            log.flush()
            app_log = data / 'logs/desktop.log' if native else log_path
            if app_log.is_file():
                tail = app_log.read_bytes()[-12000:].decode('utf-8', errors='replace')
                print(tail.encode('ascii', errors='backslashreplace').decode('ascii'), flush=True)
            raise
        finally:
            _stop_process(process, native)
            if port:
                _wait_port_closed(port)
