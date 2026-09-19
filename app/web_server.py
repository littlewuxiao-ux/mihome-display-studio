from __future__ import annotations

import asyncio
import base64

from datetime import datetime
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
import threading

import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from urllib.parse import unquote, urlparse

from serial.tools import list_ports

from .models import ProjectModel, WidgetModel
from .network_monitor import NetworkLogMonitorState
from .serial_monitor import SerialMonitorState
from .yaml_generator import YamlGenerator

MAX_BODY = 12 * 1024 * 1024
ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
# A running Python process keeps the imported generator after a source update.
def generator_source_snapshot() -> bytes:
    return b"\0".join(Path(__file__).with_name(name).read_bytes()
                       for name in ("yaml_generator.py", "lvgl_compiler.py", "models.py"))


GENERATOR_SOURCE_AT_START = generator_source_snapshot()


def parse_device_info(output: str, port: str) -> dict[str, str]:
    def find(pattern: str, fallback: str = "未知") -> str:
        match = re.search(pattern, output, re.IGNORECASE | re.MULTILINE)
        return match.group(1).strip() if match else fallback

    return {
        "port": port,
        "chip": find(r"(?:Chip is|Chip type:)\s*([^\r\n]+)", "未知芯片"),
        "mac": find(r"(?:MAC|MAC address):\s*([0-9A-Fa-f:]{17})"),
        "flash": find(r"(?:Detected flash size:|Flash size:|Size:)\s*([0-9]+\s*(?:MB|KB))"),
        "crystal": find(r"Crystal is\s+([^\r\n]+)"),
    }


def serial_port_label(item: Any) -> str:
    match = re.search(r"VID:PID=([0-9A-Fa-f]{4}:[0-9A-Fa-f]{4})", item.hwid or "")
    suffix = f" [{match.group(1)}]" if match else ""
    return f"{item.device} - {item.description}{suffix}"


def inspect_serial_device(root: Path, port: str) -> dict[str, str]:
    available = {item.device: item for item in list_ports.comports()}
    if port not in available:
        raise ValueError("串口不存在或设备已断开，请刷新串口列表")
    command = [sys.executable, "-m", "esptool", "--port", port, "flash-id"]
    try:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("读取设备信息超时，请确认设备已连接且没有被其他程序占用") from exc
    output = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0:
        details = " ".join(line.strip() for line in output.splitlines() if line.strip())
        raise ValueError(f"读取设备信息失败：{details[-300:]}")
    info = parse_device_info(output, port)
    item = available[port]
    info["label"] = serial_port_label(item)
    info["serial"] = item.serial_number or "未知"
    return info


async def _query_runtime_device(project: ProjectModel, expected_mac: str, address: str = "") -> dict[str, str]:
    from aioesphomeapi import APIClient

    address = address or f"{project.device_name}.local"
    expected = expected_mac.replace(":", "").replace("-", "").lower() or None
    client = APIClient(address, 6053, None, client_info="米家中枢屏幕工作台", noise_psk=project.api_key or None, expected_mac=expected)
    try:
        await client.connect(login=True, log_errors=False)
        info = await client.device_info()
        return {"address": client.connected_address or address, "name": str(info.name), "mac": str(info.mac_address), "project_name": str(info.project_name), "project_version": str(info.project_version), "esphome_version": str(info.esphome_version)}
    finally:
        await client.disconnect(force=True)


def inspect_runtime_device(project: ProjectModel, expected_mac: str = "", address: str = "") -> dict[str, str]:
    try:
        return asyncio.run(_query_runtime_device(project, expected_mac, address))
    except ImportError as exc:
        raise ValueError("当前Python环境缺少aioesphomeapi，无法查询运行中的固件版本") from exc
    except Exception as exc:
        target = address or f"{project.device_name}.local"
        raise ValueError(f"无法通过ESPHome API查询运行版本（{target}:6053）：{exc}") from exc


def discover_esphome_devices(timeout: float = 2.0) -> list[dict[str, str]]:
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    except ImportError as exc:
        raise ValueError("当前Python环境缺少zeroconf，无法发现局域网设备") from exc

    devices: dict[str, dict[str, str]] = {}

    class Listener(ServiceListener):
        def update_service(self, zeroconf: Any, service_type: str, name: str) -> None:
            self.add_service(zeroconf, service_type, name)

        def remove_service(self, zeroconf: Any, service_type: str, name: str) -> None:
            return

        def add_service(self, zeroconf: Any, service_type: str, name: str) -> None:
            info = zeroconf.get_service_info(service_type, name, timeout=1000)
            if not info:
                return
            properties = {
                key.decode("utf-8", "replace"): value.decode("utf-8", "replace")
                for key, value in info.properties.items()
            }
            addresses = info.parsed_addresses()
            if not addresses:
                return
            device_name = name.removesuffix(f".{service_type}").rstrip(".")
            mac = properties.get("mac", properties.get("mac_address", ""))
            key = mac.casefold() or device_name.casefold()
            devices[key] = {
                "name": device_name,
                "address": addresses[0],
                "hostname": (info.server or f"{device_name}.local.").rstrip("."),
                "mac": mac,
                "version": properties.get("version", ""),
                "platform": properties.get("platform", ""),
            }

    zeroconf = Zeroconf()
    browser = ServiceBrowser(zeroconf, "_esphomelib._tcp.local.", Listener())
    try:
        threading.Event().wait(max(0.2, min(float(timeout), 10.0)))
    finally:
        browser.cancel()
        zeroconf.close()
    return sorted(devices.values(), key=lambda item: item["name"].casefold())


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

    def start(self, command: list[str], cwd: Path, operation: str, verification: Callable[[], str] | None = None) -> bool:
        with self.lock:
            if self.running:
                return False
            self.running = True
            self.operation = operation
            self.log = [f"开始{operation}...\n"]
            self.exit_code = None
            self.progress = 3
        threading.Thread(target=self._run, args=(command, cwd, verification), daemon=True).start()
        return True

    def _run(self, command: list[str], cwd: Path, verification: Callable[[], str] | None = None) -> None:
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
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
            process.stdout.close()

        except Exception as exc:
            code = -1
            with self.lock:
                self.log.append(f"任务启动失败：{exc}\n")

        if code == 0 and verification:
            with self.lock:
                self.log.append("烧录完成，开始验证设备...\n")
            for attempt in range(1, 4):
                try:
                    result = verification()
                    with self.lock:
                        self.log.append(f"设备验证通过（第{attempt}次）：{result}\n")
                    break
                except Exception as exc:
                    if attempt == 3:
                        code = -2
                        with self.lock:
                            self.log.append(f"烧录后设备验证失败：{exc}\n")
                    else:
                        time.sleep(2)

        with self.lock:
            self.running = False
            self.exit_code = code
            self.progress = 100 if code == 0 else 0
            self.log.append(f"\n{self.operation}{'完成' if code == 0 else '失败'}（退出码 {code}）\n")


def classify_task_error(message: str) -> dict[str, str]:
    text = str(message)
    checks = [
        ("port", ("串口", "serial", "com"), "请检查串口是否存在、被占用或已断开"),
        ("network", ("dns", "mDNS", ".local", "连接"), "请检查设备网络、电源和局域网可达性"),
        ("auth", ("密码", "密钥", "认证", "unauthorized"), "请核对 API 密钥、OTA 密码和设备配置"),
        ("config", ("yaml", "配置", "invalid"), "请先执行配置校验并修正 YAML 错误"),
    ]
    lowered = text.casefold()
    for category, keywords, suggestion in checks:
        if any(keyword.casefold() in lowered for keyword in keywords):
            return {"category": category, "suggestion": suggestion}
    return {"category": "unknown", "suggestion": "请查看原始任务日志并确认设备连接状态"}


class StudioState:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.web_root = root / "web"
        self.build_dir = root / "build"
        self.build_dir.mkdir(exist_ok=True)
        self.projects_dir = root / "projects"
        self.projects_dir.mkdir(exist_ok=True)
        self.project_path = self.projects_dir / "current-project.json"
        self.devices_path = self.build_dir / "devices.json"
        self.backup_dir = self.projects_dir / "backups"
        self.backup_dir.mkdir(exist_ok=True)
        self._migrate_legacy_project_storage()

        self.asset_dir = Path.home() / ".mijia-panel" / "assets"
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        self.generator = YamlGenerator()
        self.task = TaskState()
        self.serial_monitor = SerialMonitorState()
        self.network_monitor = NetworkLogMonitorState()
        self.display_test = {"mode": "off", "color": "#000000", "backlight": 100}
        self.touch_test = {"enabled": False, "points": []}
        self.project = self._load_project()
        self.known_devices = self._load_known_devices()

    def _migrate_legacy_project_storage(self) -> None:
        legacy_project = self.build_dir / "project.json"
        if not self.project_path.exists() and legacy_project.is_file():
            shutil.copy2(legacy_project, self.project_path)
        legacy_backups = self.build_dir / "backups"
        if legacy_backups.is_dir():
            for source in legacy_backups.glob("*.json"):
                target = self.backup_dir / source.name
                if not target.exists():
                    shutil.copy2(source, target)

    def _load_project(self) -> ProjectModel:
        if self.project_path.is_file():
            try:
                return ProjectModel.load(self.project_path)
            except (OSError, ValueError, TypeError):
                pass
        return ProjectModel(
            widgets=[WidgetModel(id="people_1", kind="shape", shape_type="rectangle", text="在家人数1", x=80, y=80, width=260, height=90, binding="sensor.people_home_1")]
        )


    def yaml_path(self) -> Path:
        return self.build_dir / f"{self.project.device_name}.yaml"

    def _backup_current_project(self) -> None:
        if not self.project_path.is_file():
            return
        target = self.backup_dir / f"project-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"
        shutil.copy2(self.project_path, target)
        backups = sorted(self.backup_dir.glob("project-*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        for stale in backups[20:]:
            stale.unlink(missing_ok=True)

    def list_backups(self) -> list[dict[str, str]]:
        backups = sorted(self.backup_dir.glob("project-*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        return [{"name": item.name, "label": datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")} for item in backups[:20]]





    def restore_backup(self, filename: str) -> ProjectModel:
        target = (self.backup_dir / Path(filename).name).resolve()
        if target.parent != self.backup_dir.resolve() or not target.is_file() or target.name != filename:
            raise ValueError("备份文件不存在")
        project = ProjectModel.load(target)
        self.set_project(project.to_dict())
        return self.project

    def inspect_device(self, port: str) -> dict[str, str]:
        if self.serial_monitor.running and self.serial_monitor.port == port:
            raise ValueError("串口正在被监视器占用，请先停止串口监视")
        return inspect_serial_device(self.root, port)


    def set_project(self, payload: dict[str, Any]) -> None:
        project = ProjectModel.from_dict(payload)
        if self.project_path.is_file():
            self._backup_current_project()
        self.project = project
        self.project.save(self.project_path)

    def generate(self) -> Path:
        if generator_source_snapshot() != GENERATOR_SOURCE_AT_START:
            raise ValueError("工作台生成器已更新，请退出并重新启动工作台程序后再生成、编译或烧录固件")
        self.project.save(self.project_path)
        self.generator.generate(self.project, self.yaml_path())
        return self.yaml_path()

    def resource_report(self) -> dict[str, Any]:


        image_sources = []

        for widget in self.project.widgets:
            if widget.kind == "image" and widget.asset_path:
                image_sources.append(widget.asset_path)
            if widget.content_asset_path:
                image_sources.append(widget.content_asset_path)
        image_sources = list(dict.fromkeys(image_sources))
        image_files = [{"name": Path(source).name, "path": str(Path(source)), "bytes": Path(source).stat().st_size} for source in image_sources if Path(source).is_file()]



        uses_font = any(self.generator._has_label(widget) for widget in self.project.widgets) or any(
            not any(page.id in (widget.pages or [widget.page]) for widget in self.project.widgets)
            for page in self.project.pages
        )

        font_path = (Path(self.project.font_path) if self.project.font_path else next((path for path in (Path("C:/Windows/Fonts/simhei.ttf"), Path("C:/Windows/Fonts/simsunb.ttf")) if path.is_file()), Path())) if uses_font else Path()

        font_bytes = font_path.stat().st_size if font_path.is_file() else 0
        binaries = []
        for path in self.build_dir.rglob("*.bin"):
            if path.is_file() and path.stat().st_size:
                binaries.append({"name": path.name, "path": str(path), "bytes": path.stat().st_size})
        firmware = max(binaries, key=lambda item: item["bytes"], default=None)
        capacity = 16 * 1024 * 1024
        warnings: list[str] = []
        if font_bytes >= 4 * 1024 * 1024:
            warnings.append("中文字体文件较大，建议使用精简字体或减少字形")

        if firmware and firmware["bytes"] >= capacity * 0.9:
            warnings.append("固件已接近16MB Flash容量，请减少图片或字体资源")
        elif firmware and firmware["bytes"] >= capacity * 0.75:
            warnings.append("固件Flash占用较高，编译后请确认仍有足够升级空间")
        image_bytes = sum(item["bytes"] for item in image_files)
        if image_bytes >= 4 * 1024 * 1024:
            warnings.append("原始图片资源超过4MB，RGB565转换后的固件占用会更高")
        return {
            "flash_capacity": capacity,
            "images": {"count": len(image_files), "bytes": image_bytes, "files": image_files},
            "fonts": {"count": 1 if font_bytes else 0, "bytes": font_bytes, "file": font_path.name if font_bytes else ""},
            "yaml": {"bytes": self.generate().stat().st_size, "file": self.yaml_path().name},
            "firmware": firmware or {"name": "", "path": "", "bytes": 0},
            "firmware_candidates": binaries,
            "flash_percent": round((firmware["bytes"] / capacity) * 100, 1) if firmware else 0,
            "status": "critical" if any("接近" in warning for warning in warnings) else "warning" if warnings else "ok",
            "warnings": warnings,
        }

    def _load_known_devices(self) -> list[dict[str, str]]:
        try:
            raw = json.loads(self.devices_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, list) else []
        except (OSError, ValueError, TypeError):
            return []

    def remember_devices(self, devices: list[dict[str, str]]) -> list[dict[str, str]]:
        known = {(item.get("mac") or item.get("name", "")).casefold(): dict(item) for item in self.known_devices}
        now = datetime.now().isoformat(timespec="seconds")
        for device in devices:
            key = (device.get("mac") or device.get("name", "")).casefold()
            if not key:
                continue
            known[key] = {**known.get(key, {}), **device, "last_seen": now}
        self.known_devices = sorted(known.values(), key=lambda item: item.get("name", "").casefold())
        self.devices_path.write_text(json.dumps(self.known_devices, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.known_devices

    def discover_devices(self) -> list[dict[str, str]]:
        return self.remember_devices(discover_esphome_devices())

    def diagnostic_report(self) -> dict[str, Any]:
        task = self.task.snapshot()
        monitor = self.serial_monitor.snapshot()
        network_monitor = self.network_monitor.snapshot()
        try:
            resources = self.resource_report()
        except (OSError, ValueError) as exc:
            resources = {"status": "unavailable", "error": str(exc)}
        return {
            "project": {
                "name": self.project.name,
                "device_name": self.project.device_name,
                "firmware_version": self.project.firmware_version,
                "schema_version": self.project.schema_version,
                "pages": len(self.project.pages),
                "widgets": len(self.project.widgets),
            },
            "ports": [
                {"device": item.device, "label": serial_port_label(item), "serial": item.serial_number or ""}
                for item in list_ports.comports()
            ],
            "task": {
                "operation": task["operation"],
                "running": task["running"],
                "exit_code": task["exit_code"],
                "progress": task["progress"],
                "error": classify_task_error(task["log"]) if task["exit_code"] not in (None, 0) else None,
            },
            "serial_monitor": {
                "running": monitor["running"],
                "port": monitor["port"],
                "baudrate": monitor["baudrate"],
                "line_count": monitor["line_count"],
                "error": monitor["error"],
            },
            "network_monitor": {
                "running": network_monitor["running"],
                "target": network_monitor["target"],
                "line_count": network_monitor["line_count"],
                "error": network_monitor["error"],
            },
            "display_test": dict(self.display_test),
            "touch_test": {"enabled": self.touch_test["enabled"], "points": len(self.touch_test["points"])},
            "resources": resources,
        }

    def set_display_test(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = str(payload.get("mode", "off"))
        if mode not in {"off", "solid", "checker", "gradient", "edges"}:
            raise ValueError("不支持的显示测试模式")
        color_value = str(payload.get("color", "#000000"))
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color_value):
            raise ValueError("显示测试颜色格式不正确")
        self.display_test = {"mode": mode, "color": color_value, "backlight": max(0, min(100, int(payload.get("backlight", 100))))}
        return dict(self.display_test)

    def set_touch_test(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("clear"):
            self.touch_test["points"] = []
        if "enabled" in payload:
            self.touch_test["enabled"] = bool(payload["enabled"])
        point = payload.get("point")
        if isinstance(point, dict):
            x, y = int(point.get("x", -1)), int(point.get("y", -1))
            if 0 <= x < 800 and 0 <= y < 480:
                self.touch_test["points"].append({"x": x, "y": y})
                self.touch_test["points"] = self.touch_test["points"][-500:]
        return {"enabled": self.touch_test["enabled"], "points": list(self.touch_test["points"])}





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


def verify_uploaded_device(state: StudioState, port: str, expected_mac: str) -> str:
    # The monitor and esptool cannot own the same serial port. The monitor may
    # have been restarted while upload was running, so verification takes it
    # back before probing the device.
    if state.serial_monitor.running:
        if state.serial_monitor.port != port:
            raise ValueError(f"串口监视正在占用 {state.serial_monitor.port}，无法验证 {port}")
        state.serial_monitor.stop()
    info = state.inspect_device(port)
    if expected_mac != "未知" and info.get("mac") != expected_mac:
        raise ValueError(f"MAC不一致：期望{expected_mac}，实际{info.get('mac', '未知')}")
    runtime = inspect_runtime_device(state.project, expected_mac)
    expected_version = state.project.firmware_version
    actual_version = runtime.get("project_version", "")
    if actual_version and actual_version != expected_version:
        raise ValueError(f"固件版本不一致：期望{expected_version}，实际{actual_version or '未知'}")
    return f"{info.get('chip', '未知芯片')}，MAC {info.get('mac', '未知')}，Flash {info.get('flash', '未知')}，固件 {actual_version}"


def validate_ota_target(target: str) -> str:
    target = target.strip()
    if not target:
        raise ValueError("请填写无线设备IP或主机名")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", target):
        raise ValueError("无线设备地址格式不正确，请填写IP或设备名.local")
    return target


def verify_ota_upload(state: StudioState, target: str) -> str:
    runtime = inspect_runtime_device(state.project, address=target)
    state.remember_devices([{"name": runtime.get("name", state.project.device_name), "address": runtime.get("address", target), "hostname": f"{state.project.device_name}.local", "mac": runtime.get("mac", ""), "version": runtime.get("project_version", "")}])
    expected_version = state.project.firmware_version
    actual_version = runtime.get("project_version", "")
    if actual_version and actual_version != expected_version:
        raise ValueError(f"固件版本不一致：期望{expected_version}，实际{actual_version or '未知'}")
    return f"{runtime.get('name', target)}，MAC {runtime.get('mac', '未知')}，固件 {actual_version}"


def _start_task(handler: BaseHTTPRequestHandler, payload: dict[str, Any]) -> None:
    state = handler.server.state
    project = payload.get("project")
    if project:
        state.set_project(project)
    yaml_path = state.generate()
    operation = payload.get("operation")
    commands = {
        "validate": [sys.executable, "-m", "esphome", "config", str(yaml_path)],
        "compile": [sys.executable, "-m", "esphome", "compile", str(yaml_path)],
    }
    verification: Callable[[], str] | None = None
    if operation == "upload":
        upload_mode = str(payload.get("upload_mode", "serial")).strip()
        if upload_mode == "ota":
            target = validate_ota_target(str(payload.get("ota_target", "")))
            if str(payload.get("confirmed_target", "")).strip() != target:
                raise ValueError("无线烧录前必须确认目标设备地址")
            verification = lambda: verify_ota_upload(state, target)
        elif upload_mode == "serial":
            target = str(payload.get("port", "")).strip()
            if not target:
                raise ValueError("请选择烧录串口")
            if str(payload.get("confirmed_port", "")).strip() != target:
                raise ValueError("烧录前必须先识别并确认目标设备")
            if state.serial_monitor.running:
                if state.serial_monitor.port != target:
                    raise ValueError(f"串口监视正在占用 {state.serial_monitor.port}，无法烧录 {target}")
                state.serial_monitor.stop()
            confirmed_info = state.inspect_device(target)
            expected_mac = confirmed_info.get("mac", "未知")
            verification = lambda: verify_uploaded_device(state, target, expected_mac)
        else:
            raise ValueError("未知烧录方式")
        # `upload` only writes the last binary and can silently flash stale
        # firmware after YAML changes. `run` performs an incremental build
        # first, then uploads the binary selected for this exact config.
        command = [sys.executable, "-m", "esphome", "run", str(yaml_path), "--device", target, "--no-logs"]
        label = "无线烧录" if upload_mode == "ota" else "烧录"
    elif operation in commands:
        command = commands[operation]
        label = "校验" if operation == "validate" else "编译"

    else:
        raise ValueError("未知任务")
    if not state.task.start(command, state.build_dir, label, verification):
        raise ValueError("已有任务正在执行")

    handler._json({"ok": True})


def _handle_get(handler: BaseHTTPRequestHandler) -> None:
    path = unquote(urlparse(handler.path).path)
    if path == "/api/project":
        handler._json(handler.server.state.project.to_dict())
    elif path == "/api/project/export":
        handler._json(handler.server.state.project.to_dict(include_secrets=False))
    elif path == "/api/backups":
        handler._json(handler.server.state.list_backups())
    elif path == "/api/ports":
        ports = [{"device": item.device, "label": serial_port_label(item), "serial": item.serial_number or ""} for item in list_ports.comports()]
        handler._json(ports)
    elif path == "/api/devices":
        handler._json(handler.server.state.known_devices)
    elif path == "/api/task":
        handler._json(handler.server.state.task.snapshot())
    elif path == "/api/serial-monitor":
        handler._json(handler.server.state.serial_monitor.snapshot())
    elif path == "/api/network-monitor":
        handler._json(handler.server.state.network_monitor.snapshot())
    elif path == "/api/resources":
        handler._json(handler.server.state.resource_report())
    elif path == "/api/diagnostics":
        handler._json(handler.server.state.diagnostic_report())
    elif path == "/api/display-test":
        handler._json(handler.server.state.display_test)
    elif path == "/api/touch-test":
        handler._json(handler.server.state.touch_test)
    elif path.startswith("/asset/"):
        handler._asset(path.removeprefix("/asset/"))
    else:
        handler._static("index.html" if path == "/" else path.lstrip("/"))



class StudioHandler(BaseHTTPRequestHandler):
    server: "StudioServer"
    do_GET = _handle_get





    def do_POST(self) -> None:
        try:
            payload = self._body()
            if self.path == "/api/exit":
                origin = self.headers.get("Origin")
                if origin and origin != f"http://{self.headers.get('Host')}":
                    raise ValueError("退出请求必须来自工作台页面")
                if payload.get("exit") is not True:
                    raise ValueError("缺少退出指令")
                self._json({"ok": True})
                self.server.request_exit()
            elif self.path == "/api/project":
                self.server.state.set_project(payload)
                self._json({"ok": True})
            elif self.path == "/api/project/import":
                project = payload.get("project")
                if not isinstance(project, dict):
                    raise ValueError("导入文件缺少项目数据")
                self.server.state.set_project(project)
                self._json({"ok": True, "project": self.server.state.project.to_dict()})
            elif self.path == "/api/project/restore":
                project = self.server.state.restore_backup(str(payload.get("name", "")))
                self._json({"ok": True, "project": project.to_dict()})
            elif self.path == "/api/device/info": self._json(self.server.state.inspect_device(str(payload.get("port", "")).strip()))
            elif self.path == "/api/device/runtime":
                runtime = inspect_runtime_device(self.server.state.project, address=str(payload.get("address", "")).strip())
                self.server.state.remember_devices([{"name": runtime.get("name", ""), "address": runtime.get("address", ""), "hostname": f"{self.server.state.project.device_name}.local", "mac": runtime.get("mac", ""), "version": runtime.get("project_version", "")}])
                self._json(runtime)
            elif self.path == "/api/devices/discover": self._json(self.server.state.discover_devices())



            elif self.path == "/api/generate":
                self.server.state.set_project(payload)
                path = self.server.state.generate()
                self._json({"ok": True, "path": str(path)})
            elif self.path == "/api/upload":
                self._json(self.server.state.save_asset(payload.get("filename", ""), payload.get("data", "")))
            elif self.path == "/api/task":
                    _start_task(self, payload)
            elif self.path == "/api/serial-monitor":
                monitor = self.server.state.serial_monitor
                action = str(payload.get("action", "")).lower()
                if action == "start":
                    monitor.start(str(payload.get("port", "")), int(payload.get("baudrate", 115200)))
                elif action == "stop":
                    monitor.stop()
                elif action == "pause":
                    monitor.pause(payload.get("value"))
                elif action == "clear":
                    monitor.clear()
                elif action == "configure":
                    monitor.configure(search=payload.get("search"), level=payload.get("level"))
                elif action == "save":
                    self._json({"path": str(monitor.save(str(payload.get("path", ""))))})
                    return
                else:
                    raise ValueError("未知串口监视操作")
                self._json(monitor.snapshot())
            elif self.path == "/api/network-monitor":
                monitor = self.server.state.network_monitor
                action = str(payload.get("action", "")).lower()
                if action == "start":
                    target = validate_ota_target(str(payload.get("target", "")))
                    monitor.start(self.server.state.generate(), target, self.server.state.build_dir)
                elif action == "stop":
                    monitor.stop()
                elif action == "pause":
                    monitor.pause(payload.get("value"))
                elif action == "clear":
                    monitor.clear()
                elif action == "configure":
                    monitor.configure(search=payload.get("search"), level=payload.get("level"))
                else:
                    raise ValueError("未知无线日志监视操作")
                self._json(monitor.snapshot())
            elif self.path == "/api/display-test":
                self._json(self.server.state.set_display_test(payload))
            elif self.path == "/api/touch-test":
                self._json(self.server.state.set_touch_test(payload))

            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._json({"ok": False, "error": f"服务器错误：{exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)









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
        if target.suffix.lower() in {".html", ".js", ".css"}:
            self.send_header("Cache-Control", "no-store, max-age=0")
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
    daemon_threads = True

    def __init__(self, address: tuple[str, int], state: StudioState) -> None:
        super().__init__(address, StudioHandler)
        self.state = state
        self.exit_requested = threading.Event()

    def request_exit(self) -> None:
        if self.exit_requested.is_set():
            return
        self.exit_requested.set()
        threading.Thread(target=self.shutdown, daemon=True).start()


def _start_tray(server: StudioServer, url: str):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        print("系统托盘不可用：请安装 pystray")
        return None

    image = Image.new("RGBA", (64, 64), "#111820")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((6, 10, 58, 49), radius=5, fill="#2F7DF6", outline="#DDEBFF", width=3)
    draw.rectangle((13, 17, 51, 42), fill="#0B1118")
    draw.rectangle((25, 52, 39, 56), fill="#DDEBFF")

    def open_studio(_icon=None, _item=None) -> None:
        webbrowser.open(url)

    def exit_studio(icon, _item=None) -> None:
        server.request_exit()

    tray = pystray.Icon(
        "mihome-display-studio",
        image,
        "米家中枢屏幕工作台",
        menu=pystray.Menu(
            pystray.MenuItem("打开工作台", open_studio, default=True),
            pystray.MenuItem("退出", exit_studio),
        ),
    )
    tray.run_detached()
    return tray


def run_server(root: Path, port: int = 8765, open_browser: bool = True) -> None:
    state = StudioState(root)
    try:
        server = StudioServer(("127.0.0.1", port), state)
    except OSError as exc:
        if exc.errno not in {48, 98, 10048} and getattr(exc, "winerror", None) != 10048:
            raise
        if open_browser:
            webbrowser.open(f"http://127.0.0.1:{port}")
        print(f"端口 {port} 已有服务，未启动重复工作台")
        return
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"米家中枢屏幕工作台：{url}")
    tray = _start_tray(server, url)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        # A detached watchdog reaps this instance and all its build children,
        # even if a monitor or tray shutdown blocks. Never kill all Pythons.
        if sys.platform == "win32":
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 f"Start-Sleep -Seconds 3; taskkill /PID {os.getpid()} /T /F"],
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        server.state.serial_monitor.stop()
        server.state.network_monitor.stop()
        if tray is not None:
            tray.stop()
        server.server_close()
        if sys.platform == "win32":
            # Keep the parent alive until its tree has been terminated.
            threading.Event().wait(6)
