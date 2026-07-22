from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, pyqtSignal


ERROR_TRANSLATIONS = (
    (re.compile(r"command not found|is not recognized", re.I), "未找到ESPHome命令，请确认已通过pip安装并重启本工具。"),
    (re.compile(r"Failed to connect|Could not open port", re.I), "无法连接串口，请检查端口、数据线，并按住BOOT键后重试。"),
    (re.compile(r"Invalid YAML|while parsing|Unable to load component", re.I), "配置校验失败，请查看下方原始日志定位具体字段。"),
    (re.compile(r"No module named", re.I), "Python环境缺少依赖，请在当前Python环境重新安装ESPHome。"),
)


class EsphomeProcess(QObject):
    output = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)
    started = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._finished)
        self._operation = ""

    @property
    def running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def compile(self, yaml_path: Path) -> None:
        self._start("编译", ["compile", str(yaml_path)])

    def upload(self, yaml_path: Path, port: str) -> None:
        self._start("烧录", ["upload", str(yaml_path), "--device", port])

    def validate(self, yaml_path: Path) -> None:
        self._start("校验", ["config", str(yaml_path)])

    def stop(self) -> None:
        if self.running:
            self.process.kill()

    def _start(self, operation: str, args: list[str]) -> None:
        if self.running:
            self.output.emit("已有任务正在执行。\n")
            return
        self._operation = operation
        command = shutil.which("esphome")
        if command:
            program, complete_args = command, args
        else:
            program, complete_args = sys.executable, ["-m", "esphome", *args]
        self.output.emit(f"开始{operation}...\n")
        self.progress.emit(2)
        self.process.setWorkingDirectory(str(Path(args[1]).parent))
        self.process.start(program, complete_args)
        self.started.emit()

    def _read(self) -> None:
        text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.output.emit(text)
        match = re.search(r"(?:Writing at|Progress:).*?([0-9]{1,3})%", text, re.I)
        if match:
            self.progress.emit(min(99, int(match.group(1))))
        elif "Linking" in text:
            self.progress.emit(75)
        elif "Compiling" in text:
            self.progress.emit(35)
        for pattern, translation in ERROR_TRANSLATIONS:
            if pattern.search(text):
                self.output.emit(f"\n中文提示：{translation}\n")
                break

    def _finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        success = exit_code == 0
        self.progress.emit(100 if success else 0)
        message = f"{self._operation}{'完成' if success else '失败'}（退出码 {exit_code}）"
        self.output.emit(f"\n{message}\n")
        self.finished.emit(success, message)
