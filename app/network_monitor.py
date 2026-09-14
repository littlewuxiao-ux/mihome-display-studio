from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any


class NetworkLogMonitorState:
    """Runs ``esphome logs`` for a device reachable through the local network."""

    def __init__(self, max_lines: int = 4000) -> None:
        self.lock = threading.RLock()
        self.max_lines = max_lines
        self.target = ""
        self.running = False
        self.paused = False
        self.level = "all"
        self.search = ""
        self.lines: list[str] = []
        self.error = ""
        self._process: subprocess.Popen[str] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "running": self.running,
                "target": self.target,
                "paused": self.paused,
                "level": self.level,
                "search": self.search,
                "log": "".join(self.filtered_lines()),
                "line_count": len(self.lines),
                "error": self.error,
            }

    def filtered_lines(self) -> list[str]:
        search = self.search.casefold()
        return [
            line
            for line in self.lines
            if (not search or search in line.casefold()) and self._level_matches(line)
        ][-1200:]

    def _level_matches(self, line: str) -> bool:
        return self.level == "all" or self.level.upper() in line.upper()

    def start(self, yaml_path: Path, target: str, cwd: Path) -> None:
        with self.lock:
            if self.running:
                if self.target == target:
                    raise ValueError("无线日志监视已经在运行")
                raise ValueError(f"无线日志监视正在连接 {self.target}")
            self.target = target
            self.running = True
            self.paused = False
            self.error = ""
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, args=(yaml_path, target, cwd), daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self.lock:
            self.running = False
            self._stop.set()
            process = self._process
            thread = self._thread
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
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

    def _append(self, line: str) -> None:
        with self.lock:
            if not self.paused:
                self.lines.append(line)
                del self.lines[:-self.max_lines]

    def _run(self, yaml_path: Path, target: str, cwd: Path) -> None:
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", "esphome", "logs", str(yaml_path), "--device", target],
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            with self.lock:
                self._process = process
            assert process.stdout is not None
            for line in process.stdout:
                self._append(line)
            process.stdout.close()
            code = process.wait()
            if code and not self._stop.is_set():
                with self.lock:
                    self.error = f"无线日志连接已结束（退出码 {code}）"
        except Exception as exc:
            if not self._stop.is_set():
                with self.lock:
                    self.error = str(exc)
        finally:
            with self.lock:
                self._process = None
                self.running = False
