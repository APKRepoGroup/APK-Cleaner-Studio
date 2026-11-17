"""Real packaged Windows HTTPS update checks; no external requests or installs."""
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import ssl
import sys
import tempfile
import threading
from unittest.mock import patch
import uuid

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from local_artifact_runtime import local_open, local_package_server

ROOT = Path(__file__).resolve().parents[1]
EXE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'outputs/APK-Cleaner-Studio-v0.6.3-Windows.exe'


def certificates(folder, *, matching=True):
    folder.mkdir()
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Isolated HTTPS audit ' + uuid.uuid4().hex)])
    ca = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=60))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True).sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    names = [x509.IPAddress(ipaddress.ip_address('127.0.0.1'))] if matching else [x509.DNSName('wrong-host.invalid')]
    leaf_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Loopback HTTPS fixture')])
    cert = (x509.CertificateBuilder().subject_name(leaf_subject).issuer_name(ca.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=10))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName(names), critical=False).sign(ca_key, hashes.SHA256()))
    paths = (folder/'leaf.pem', folder/'key.pem', folder/'ca.pem')
    paths[0].write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    paths[1].write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    paths[2].write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    return paths


class ManifestHandler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_GET(self):
        filename = 'APK-Cleaner-Studio-v0.6.4-Windows.exe'
        payload = {'tag_name':'v0.6.4', 'draft':False, 'prerelease':False,
                   'body':'Yerel HTTPS doğrulaması; yükleme yapılmaz.',
                   'assets':[{'name':filename, 'state':'uploaded', 'size':10, 'digest':'sha256:'+'b'*64,
                              'browser_download_url':'https://github.com/APKRepoGroup/APK-Cleaner-Studio/releases/download/v0.6.4/'+filename}]}
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    before = hashlib.sha256(EXE.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='stable-https-package-', ignore_cleanup_errors=True) as name:
        folder = Path(name)
        valid = certificates(folder/'valid')
        untrusted = certificates(folder/'untrusted')
        wronghost = certificates(folder/'wronghost', matching=False)
        # Both CAs are process-local: Windows trust is never modified.
        (folder/'trust.pem').write_bytes(valid[2].read_bytes()+wronghost[2].read_bytes())
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(*valid[:2])
        server = ThreadingHTTPServer(('127.0.0.1',0), ManifestHandler)
        server.socket = context.wrap_socket(server.socket,server_side=True)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            (folder/'native').mkdir()
            fixture_env = dict(APK_CLEANER_UPDATE_URL=f'https://127.0.0.1:{server.server_port}/manifest',
                               SSL_CERT_FILE=str(folder/'trust.pem'), SSLKEYLOGFILE=str(folder/'missing/unused-keylog.txt'))
            with local_package_server([str(EXE.resolve())],folder/'native',native=True,update_fixture=fixture_env) as (base, status):
                    results = []
                    for label, certs, expected in (('verified_tls_missing_optional_log',valid,True),('untrusted_certificate',untrusted,False),
                                                   ('hostname_mismatch',wronghost,False),('successful_retry',valid,True)):
                        context.load_cert_chain(*certs[:2])
                        with local_open(base+'/api/update',timeout=15) as response:
                            payload=json.load(response)
                        assert payload['available'] is expected, (label,payload)
                        if expected:
                            assert payload['update']['latest_version']=='0.6.4' and payload['update']['automatic'], payload
                            assert payload['warning'] is None and payload['check_status']=='available',payload
                        else:
                            assert payload['check_status']=='failed' and 'güvenli bağlantısı' in payload['warning'],payload
                        results.append(label)
                    assert status['version']=='0.6.3' and status['channel']=='stable',status
                    assert not (folder/'missing').exists()
                    assert not (folder/'native/data/updates').exists(), 'No update download or install was requested.'
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
    assert hashlib.sha256(EXE.read_bytes()).hexdigest()==before
    print(json.dumps({'windows_version':'0.6.3','cases':results,'external_requests':False,'artifact_unchanged':True},indent=2))


if __name__=='__main__': main()
