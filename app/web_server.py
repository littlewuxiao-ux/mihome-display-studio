from __future__ import annotations

import base64
import json
import mimetypes
import re
import subprocess
import sys
import threading
import webbrowser
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from serial.tools import list_ports

from .models import ProjectModel, WidgetModel
from .yaml_generator import YamlGenerator

MAX_BODY = 12 * 1024 * 1024
ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


class TaskState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running = False
        self.operation = ""
        self.log: list[str] = []
        self.exit_code: int | None = None
        self.progress = 0

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "running": self.running,
                "operation": self.operation,
                "log": "".join(self.log[-1200:]),
                "exit_code": self.exit_code,
                "progress": self.progress,
            }

    def start(self, command: list[str], cwd: Path, operation: str) -> bool:
        with self.lock:
            if self.running:
                return False
            self.running = True
            self.operation = operation
            self.log = [f"开始{operation}...\n"]
            self.exit_code = None
            self.progress = 3
        threading.Thread(target=self._run, args=(command, cwd), daemon=True).start()
        return True

    def _run(self, command: list[str], cwd: Path) -> None:
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            assert process.stdout is not None
            for line in process.stdout:
                with self.lock:
                    self.log.append(line)
                    match = re.search(r"([0-9]{1,3})%", line)
                    if match:
                        self.progress = min(99, int(match.group(1)))
                    elif "Compiling" in line:
                        self.progress = max(self.progress, 35)
                    elif "Linking" in line:
                        self.progress = max(self.progress, 75)
            code = process.wait()
        except Exception as exc:
            code = -1
            with self.lock:
                self.log.append(f"任务启动失败：{exc}\n")
        with self.lock:
            self.running = False
            self.exit_code = code
            self.progress = 100 if code == 0 else 0
            self.log.append(f"\n{self.operation}{'完成' if code == 0 else '失败'}（退出码 {code}）\n")


class StudioState:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.web_root = root / "web"
        self.build_dir = root / "build"
        self.build_dir.mkdir(exist_ok=True)
        self.project_path = self.build_dir / "project.json"
        self.asset_dir = Path.home() / ".mijia-panel" / "assets"
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        self.generator = YamlGenerator()
        self.task = TaskState()
        self.project = self._load_project()

    def _load_project(self) -> ProjectModel:
        if self.project_path.is_file():
            try:
                return ProjectModel.load(self.project_path)
            except (OSError, ValueError, TypeError):
                pass
        return ProjectModel(
            widgets=[WidgetModel(id="people_1", kind="shape", shape_type="rectangle", text="在家人数1", x=80, y=80, width=260, height=90, binding="sensor.people_home_1")]
        )

    @property
    def yaml_path(self) -> Path:
        return self.build_dir / f"{self.project.device_name}.yaml"

    def set_project(self, payload: dict[str, Any]) -> None:
        self.project = ProjectModel.from_dict(payload)
        self.project.save(self.project_path)

    def generate(self) -> Path:
        self.project.save(self.project_path)
        self.generator.generate(self.project, self.yaml_path)
        return self.yaml_path

    def save_asset(self, filename: str, encoded: str) -> dict[str, Any]:
        suffix = Path(filename).suffix.lower()
        if suffix not in ASSET_EXTENSIONS:
            raise ValueError("仅支持PNG、JPEG、BMP或WebP静态图片")
        data = base64.b64decode(encoded, validate=True)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError("图片不能超过8MB")
        stem = re.sub(r"[^a-zA-Z0-9_-]", "_", Path(filename).stem)[:48] or "image"
        target = self.asset_dir / f"{stem}_{len(data):x}{suffix}"
        target.write_bytes(data)
        width = height = 0
        try:
            from PIL import Image
            with Image.open(target) as image:
                width, height = image.size
        except Exception as exc:
            target.unlink(missing_ok=True)
            raise ValueError("图片文件无法解析") from exc
        return {"path": target.as_posix(), "url": f"/asset/{target.name}", "width": width, "height": height}


class StudioHandler(BaseHTTPRequestHandler):
    server: "StudioServer"

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path == "/api/project":
            self._json(asdict(self.server.state.project))
        elif path == "/api/ports":
            ports = [{"device": item.device, "label": f"{item.device} - {item.description}"} for item in list_ports.comports()]
            self._json(ports)
        elif path == "/api/task":
            self._json(self.server.state.task.snapshot())
        elif path.startswith("/asset/"):
            self._asset(path.removeprefix("/asset/"))
        else:
            self._static("index.html" if path == "/" else path.lstrip("/"))

    def do_POST(self) -> None:
        try:
            payload = self._body()
            if self.path == "/api/project":
                self.server.state.set_project(payload)
                self._json({"ok": True})
            elif self.path == "/api/generate":
                self.server.state.set_project(payload)
                path = self.server.state.generate()
                self._json({"ok": True, "path": str(path)})
            elif self.path == "/api/upload":
                self._json(self.server.state.save_asset(payload.get("filename", ""), payload.get("data", "")))
            elif self.path == "/api/task":
                self._start_task(payload)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._json({"ok": False, "error": f"服务器错误：{exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _start_task(self, payload: dict[str, Any]) -> None:
        project = payload.get("project")
        if project:
            self.server.state.set_project(project)
        yaml_path = self.server.state.generate()
        operation = payload.get("operation")
        commands = {
            "validate": [sys.executable, "-m", "esphome", "config", str(yaml_path)],
            "compile": [sys.executable, "-m", "esphome", "compile", str(yaml_path)],
        }
        if operation == "upload":
            port = str(payload.get("port", "")).strip()
            if not port:
                raise ValueError("请选择烧录串口")
            command = [sys.executable, "-m", "esphome", "upload", str(yaml_path), "--device", port]
            label = "烧录"
        elif operation in commands:
            command = commands[operation]
            label = "校验" if operation == "validate" else "编译"
        else:
            raise ValueError("未知任务")
        if not self.server.state.task.start(command, self.server.state.build_dir, label):
            raise ValueError("已有任务正在执行")
        self._json({"ok": True})

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY:
            raise ValueError("请求内容为空或过大")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _static(self, relative: str) -> None:
        target = (self.server.state.web_root / relative).resolve()
        if self.server.state.web_root.resolve() not in target.parents or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = target.read_bytes()
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime}; charset=utf-8" if mime.startswith("text/") or mime == "application/javascript" else mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _asset(self, filename: str) -> None:
        target = (self.server.state.asset_dir / Path(filename).name).resolve()
        if target.parent != self.server.state.asset_dir.resolve() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class StudioServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], state: StudioState) -> None:
        super().__init__(address, StudioHandler)
        self.state = state


def run_server(root: Path, port: int = 8765, open_browser: bool = True) -> None:
    state = StudioState(root)
    for candidate in range(port, port + 20):
        try:
            server = StudioServer(("127.0.0.1", candidate), state)
            break
        except OSError:
            continue
    else:
        raise RuntimeError("找不到可用的本地端口")
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"米家中枢屏幕工作台：{url}")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
