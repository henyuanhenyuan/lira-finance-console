"""Inbox ingestion: file events first, a timer as the fallback.

A merchant drops an export into ``data/inbox``. A watcher reacts as soon as the
file appears; the timer still runs so a missed event, a network share, or a
platform where the watcher is unavailable is picked up eventually. No broker:
a single-machine product does not need Kafka to watch one directory.
"""

from __future__ import annotations

import logging
import os
import threading

from . import imports

_log = logging.getLogger("lira.sync")

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    _HAS_WATCHDOG = True
except ImportError:  # pragma: no cover - exercised only on a bare install
    _HAS_WATCHDOG = False

if os.environ.get("LIRA_DISABLE_WATCH") == "1":
    _HAS_WATCHDOG = False


if _HAS_WATCHDOG:

    class _InboxHandler(FileSystemEventHandler):
        def __init__(self, event: threading.Event) -> None:
            self.event = event

        def on_created(self, event) -> None:  # noqa: ANN001 - watchdog event
            if not event.is_directory:
                self.event.set()

        def on_moved(self, event) -> None:  # noqa: ANN001 - watchdog event
            if not event.is_directory:
                self.event.set()


class SyncScheduler:
    def __init__(self) -> None:
        self.interval = max(15, int(os.environ.get("LIRA_SYNC_SECONDS", "300")))
        self.mode = "event+poll" if _HAS_WATCHDOG else "poll"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._watch_thread: threading.Thread | None = None
        self._wake = threading.Event()
        self._observer = None

    def start(self) -> None:
        imports.ensure_inbox()
        self._thread = threading.Thread(target=self._run, daemon=True, name="lira-sync")
        self._thread.start()
        if _HAS_WATCHDOG:
            self._observer = Observer()
            self._observer.schedule(
                _InboxHandler(self._wake), str(imports.INBOX), recursive=False
            )
            self._observer.start()
            self._watch_thread = threading.Thread(
                target=self._watch, daemon=True, name="lira-watch"
            )
            self._watch_thread.start()

    def _scan(self) -> None:
        try:
            results = imports.scan_inbox()
            if results:
                _log.info("inbox scan: %s", results)
        except Exception:  # noqa: BLE001 - a bad file must not kill the poller
            _log.exception("inbox scan failed")

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self._scan()

    def _watch(self) -> None:
        while not self._stop.is_set():
            if self._wake.wait(1):
                self._wake.clear()
                # Debounce the two events a single copy can emit.
                self._stop.wait(0.4)
                if not self._stop.is_set():
                    self._scan()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2)
        for thread in (self._thread, self._watch_thread):
            if thread is not None:
                thread.join(timeout=2)
