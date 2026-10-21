"""Ephemeral LAN pairing: no code, token or peer identity is written to disk."""
from __future__ import annotations

from collections import deque
import hashlib
import secrets
import threading
import time

COOKIE = "apk_cleaner_lan_session"


class Pairing:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.code = ""
        self.sessions = {}
        self.attempts = deque(maxlen=512)

    def reset(self, enabled=False):
        with self.lock:
            self.code = f"{secrets.randbelow(1_000_000):06d}" if enabled else ""
            self.sessions.clear()
            self.attempts.clear()

    def current_code(self):
        with self.lock:
            return self.code

    @staticmethod
    def fingerprint(address, agent):
        return hashlib.sha256(f"{address}\0{agent[:512]}".encode()).digest()

    def authorize(self, token, address, agent):
        if not isinstance(token, str) or not 20 <= len(token) <= 128:
            return False
        with self.lock:
            key = hashlib.sha256(token.encode()).digest()
            entry = self.sessions.get(key)
            if not entry:
                return False
            expires, peer = entry
            if expires <= self.clock():
                self.sessions.pop(key, None)
                return False
            return bool(self.code and secrets.compare_digest(peer, self.fingerprint(address, agent)))

    def pair(self, code, address, agent):
        with self.lock:
            now = self.clock()
            while self.attempts and now - self.attempts[0][0] >= 300:
                self.attempts.popleft()
            if (sum(peer == address for _, peer in self.attempts) >= 5
                    or sum(now - timestamp < 60 for timestamp, _ in self.attempts) >= 60):
                return "limited", ""
            self.attempts.append((now, address))
            if (not self.code or not isinstance(code, str) or len(code) != 6 or not code.isascii()
                    or not code.isdigit() or not secrets.compare_digest(code, self.code)):
                return "invalid", ""
            self.sessions = {key: entry for key, entry in self.sessions.items() if entry[0] > now}
            if len(self.sessions) >= 64:
                return "full", ""
            token = secrets.token_urlsafe(32)
            self.sessions[hashlib.sha256(token.encode()).digest()] = (now + 8 * 3600, self.fingerprint(address, agent))
            return "ok", token
