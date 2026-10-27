"""Bounded, owner-scoped progress for in-flight uploads; never persisted as jobs."""
from __future__ import annotations

import re
import threading
import time


class AnalysisCancelled(ValueError):
    def __init__(self):
        super().__init__("Analiz iptal edildi.")


class AnalysisSessions:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = {}
        self.cancelled = {}

    def _prune(self):
        now = time.monotonic()
        self.cancelled = {key: value for key, value in self.cancelled.items() if now - value[1] < 60}

    def begin(self, token, owner):
        if not re.fullmatch(r"[a-f0-9]{32}", token):
            raise ValueError("Geçersiz analiz kimliği.")
        with self.lock:
            self._prune()
            if token in self.active:
                raise ValueError("Bu analiz kimliği zaten kullanılıyor.")
            previous = self.cancelled.get(token)
            if previous:
                if previous[0] != owner:
                    raise PermissionError("Bu analiz bu cihaza ait değil.")
                raise AnalysisCancelled()
            if len(self.active) >= 2:
                raise ValueError("Devam eden analizin tamamlanmasını bekle.")
            session = {"owner": owner, "cancel": threading.Event(),
                       "message": "Paket cihaza aktarılıyor", "progress": None}
            self.active[token] = session
            return session

    def update(self, session, message, progress):
        self.check(session)
        with self.lock:
            session.update(message=str(message)[:400], progress=max(0, min(100, int(progress))))

    @staticmethod
    def check(session):
        if session["cancel"].is_set():
            raise AnalysisCancelled()

    def snapshot(self, token, owner):
        with self.lock:
            session = self.active.get(token)
            if not session or session["owner"] != owner:
                return None
            return {"message": session["message"], "progress": session["progress"],
                    "cancel_requested": session["cancel"].is_set()}

    def cancel(self, token, owner):
        if not re.fullmatch(r"[a-f0-9]{32}", token):
            return False
        with self.lock:
            self._prune()
            session = self.active.get(token)
            if session:
                if session["owner"] != owner:
                    return False
                session["cancel"].set()
                return True
            previous = self.cancelled.get(token)
            if previous and previous[0] != owner:
                return False
            # Cancellation can beat the upload's request thread. A short-lived,
            # bounded tombstone prevents that late upload from starting a scan.
            if len(self.cancelled) >= 64 and token not in self.cancelled:
                return False
            self.cancelled[token] = (owner, time.monotonic())
            return True

    def finish(self, token, session):
        with self.lock:
            if self.active.get(token) is session:
                del self.active[token]
