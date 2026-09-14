from __future__ import annotations

from pathlib import Path
import threading
import time
from typing import Any


class SerialMonitorState:
    """Owns the long-lived serial monitor connection and its bounded log."""

    def __init__(self, max_lines: int = 4000) -> None:
        self.lock = threading.RLock()
        self.max_lines = max_lines
        self.port = ""
        self.baudrate = 115200
        self.running = False
        self.paused = False
        self.level = "all"
        self.search = ""
        self.lines: list[str] = []
        self.error = ""
        self.reconnect = True
        self._serial: Any = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "running": self.running,
                "port": self.port,
                "baudrate": self.baudrate,
                "paused": self.paused,
                "level": self.level,
                "search": self.search,
                "log": "".join(self.filtered_lines()),
                "line_count": len(self.lines),
                "error": self.error,
                "reconnect": self.reconnect,
            }

    def filtered_lines(self) -> list[str]:
        search = self.search.casefold()
        return [
            line
            for line in self.lines
            if (not search or search in line.casefold()) and self._level_matches(line)
        ][-1200:]

    def _level_matches(self, line: str) -> bool:
        if self.level == "all":
            return True
        upper = line.upper()
        return self.level.upper() in upper

    def start(self, port: str, baudrate: int = 115200) -> None:
        port = str(port).strip()
        if not port:
            raise ValueError("请选择串口")
        if baudrate not in {9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600}:
            raise ValueError("不支持的波特率")
        with self.lock:
            if self.running:
                if self.port == port:
                    raise ValueError("串口监视已经在运行")
                raise ValueError(f"串口监视正在占用 {self.port}")
            self.port = port
            self.baudrate = baudrate
            self.running = True
            self.paused = False
            self.error = ""
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self.lock:
            self.running = False
            self._stop.set()
            serial = self._serial
            self._serial = None
            thread = self._thread
        if serial is not None:
            try:
                serial.close()
            except Exception:
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        with self.lock:
            if self._thread is thread and (thread is None or not thread.is_alive()):
                self._thread = None

    def pause(self, value: bool | None = None) -> None:
        with self.lock:
            self.paused = not self.paused if value is None else bool(value)

    def clear(self) -> None:
        with self.lock:
            self.lines.clear()

    def configure(self, *, search: str | None = None, level: str | None = None) -> None:
        with self.lock:
            if search is not None:
                self.search = str(search)
            if level is not None:
                self.level = str(level).lower() or "all"

    def save(self, path: str | Path) -> Path:
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("".join(self.filtered_lines()), encoding="utf-8")
        return target

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                import serial

                connection = serial.Serial(self.port, self.baudrate, timeout=0.25)
                with self.lock:
                    self._serial = connection
                    self.error = ""
                while not self._stop.is_set():
                    raw = connection.readline()
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="replace")
                    with self.lock:
                        if not self.paused:
                            self.lines.append(line)
                            del self.lines[:-self.max_lines]
                connection.close()
            except Exception as exc:
                with self.lock:
                    self._serial = None
                    self.error = str(exc)
                if not self.reconnect or self._stop.wait(1.5):
                    break
            finally:
                with self.lock:
                    self._serial = None
        with self.lock:
            self.running = False
