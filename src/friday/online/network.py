"""
Network state machine (§8.1) for detecting connectivity.
"""
from __future__ import annotations

import enum
import threading
import time
import urllib.request
import urllib.error
from dataclasses import dataclass

class NetworkState(enum.Enum):
    UNKNOWN = "UNKNOWN"
    PROBING = "PROBING"
    OFFLINE = "OFFLINE"
    ONLINE = "ONLINE"

class NetworkMonitor:
    def __init__(self, check_urls: list[str] | None = None, interval: int = 60):
        self._check_urls = check_urls or ["https://1.1.1.1", "https://8.8.8.8"]
        self._interval = interval
        self._state = NetworkState.UNKNOWN
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def check(self) -> NetworkState:
        """Perform actual HTTP probe."""
        with self._lock:
            self._state = NetworkState.PROBING
            
        for url in self._check_urls:
            try:
                # 2 second timeout for probe
                urllib.request.urlopen(url, timeout=2.0)
                with self._lock:
                    self._state = NetworkState.ONLINE
                return self._state
            except (urllib.error.URLError, OSError):
                continue
                
        with self._lock:
            self._state = NetworkState.OFFLINE
        return self._state

    def is_online(self) -> bool:
        """Return True if currently known to be online."""
        with self._lock:
            # If unknown, trigger synchronous check
            if self._state == NetworkState.UNKNOWN:
                self._lock.release()
                return self.check() == NetworkState.ONLINE
            return self._state == NetworkState.ONLINE

    def start_background_probing(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._probe_loop, daemon=True)
        self._thread.start()

    def stop_background_probing(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _probe_loop(self) -> None:
        while not self._stop_event.is_set():
            self.check()
            # Wait for interval or stop event
            self._stop_event.wait(self._interval)
