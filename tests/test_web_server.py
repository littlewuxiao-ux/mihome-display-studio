from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import time
import unittest
from unittest import mock
import json
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from app.serial_monitor import SerialMonitorState
from app.network_monitor import NetworkLogMonitorState
from app.web_server import StudioServer, StudioState, TaskState, classify_task_error, parse_device_info, validate_ota_target, verify_ota_upload


class StudioStateBackupTests(unittest.TestCase):
    def test_updated_generator_requires_restart_before_overwriting_yaml(self) -> None:
        with TemporaryDirectory() as directory:
            state = StudioState(Path(directory))
            target = state.yaml_path()
            target.write_text("existing firmware config", encoding="utf-8")
            with mock.patch("app.web_server.GENERATOR_SOURCE_AT_START", b"old generator"), \
                 mock.patch.object(state.generator, "generate") as generate:
                with self.assertRaisesRegex(ValueError, "重新启动"):
                    state.generate()
            generate.assert_not_called()
            self.assertEqual(target.read_text(encoding="utf-8"), "existing firmware config")

    def test_unchanged_generator_can_generate(self) -> None:
        with TemporaryDirectory() as directory:
            state = StudioState(Path(directory))
            with mock.patch.object(state.generator, "generate") as generate:
                self.assertEqual(state.generate(), state.yaml_path())
            generate.assert_called_once_with(state.project, state.yaml_path())

    def test_legacy_project_storage_is_migrated_to_projects_directory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "build" / "project.json"
            legacy.parent.mkdir()
            legacy.write_text(json.dumps({"name": "旧项目", "wifi_ssid": "wifi", "widgets": []}, ensure_ascii=False), encoding="utf-8")
            state = StudioState(root)
            self.assertEqual(state.project.name, "旧项目")
            self.assertEqual(state.project_path, root / "projects" / "current-project.json")
            self.assertTrue(state.project_path.is_file())
            self.assertTrue(legacy.is_file())

    def test_discovered_devices_are_persisted_and_updated_by_mac(self) -> None:
        with TemporaryDirectory() as directory:
            state = StudioState(Path(directory))
            state.remember_devices([{"name": "panel", "address": "192.168.1.20", "mac": "AA:BB"}])
            state.remember_devices([{"name": "panel", "address": "192.168.1.21", "mac": "AA:BB"}])
            self.assertEqual(len(state.known_devices), 1)
            self.assertEqual(state.known_devices[0]["address"], "192.168.1.21")
            reloaded = StudioState(Path(directory))
            self.assertEqual(reloaded.known_devices[0]["mac"], "AA:BB")

    def test_ota_target_validation_and_version_verification(self) -> None:
        self.assertEqual(validate_ota_target("panel.local"), "panel.local")
        self.assertEqual(validate_ota_target("192.168.1.25"), "192.168.1.25")
        for target in ("", "http://panel.local", "--help", "panel local"):
            with self.assertRaises(ValueError):
                validate_ota_target(target)
        with TemporaryDirectory() as directory:
            state = StudioState(Path(directory))
            with mock.patch("app.web_server.inspect_runtime_device", return_value={"name": "panel", "mac": "AA:BB", "project_version": state.project.firmware_version}) as inspect:
                result = verify_ota_upload(state, "192.168.1.25")
            inspect.assert_called_once_with(state.project, address="192.168.1.25")
            self.assertIn(state.project.firmware_version, result)

    def test_serial_monitor_filters_and_rejects_invalid_baudrate(self) -> None:
        monitor = SerialMonitorState()
        with monitor.lock:
            monitor.lines = ["INFO boot\n", "ERROR failed\n"]
        monitor.configure(level="error")
        self.assertEqual(monitor.snapshot()["log"], "ERROR failed\n")
        with self.assertRaises(ValueError):
            monitor.start("COM1", 12345)

    def test_network_monitor_filters_logs(self) -> None:
        monitor = NetworkLogMonitorState()
        with monitor.lock:
            monitor.lines = ["INFO Connected\\n", "ERROR API unavailable\\n"]
        monitor.configure(search="api", level="error")
        self.assertEqual(monitor.snapshot()["log"], "ERROR API unavailable\\n")

    def test_upload_verification_stops_monitor_on_same_port(self) -> None:
        with TemporaryDirectory() as directory:
            state = StudioState(Path(directory))
            state.serial_monitor.running = True
            state.serial_monitor.port = "COM7"
            with mock.patch("app.web_server.inspect_serial_device", return_value={"mac": "未知", "chip": "ESP32-S3", "flash": "16MB"}), \
                 mock.patch("app.web_server.inspect_runtime_device", return_value={"project_version": state.project.firmware_version}):
                from app.web_server import verify_uploaded_device
                result = verify_uploaded_device(state, "COM7", "未知")
            self.assertFalse(state.serial_monitor.running)
            self.assertIn("ESP32-S3", result)

    def test_diagnostic_error_classification_does_not_include_secrets(self) -> None:
        self.assertEqual(classify_task_error("串口 COM7 被占用")["category"], "port")
        with TemporaryDirectory() as directory:
            state = StudioState(Path(directory))
            state.project.api_key = "secret-key"
            state.project.wifi_password = "secret-password"
            report = state.diagnostic_report()
            encoded = json.dumps(report, ensure_ascii=False)
            self.assertNotIn("secret-key", encoded)
            self.assertNotIn("secret-password", encoded)

    def test_api_export_is_redacted_and_invalid_requests_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            state = StudioState(Path(directory))
            project = state.project.to_dict()
            project.update({"wifi_ssid": "ssid", "wifi_password": "secret", "api_key": "key", "ota_password": "ota"})
            state.set_project(project)
            server = StudioServer(("127.0.0.1", 0), state)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                exported = json.loads(urlopen(f"{base}/api/project/export").read())
                self.assertEqual(exported["wifi_password"], "")
                self.assertEqual(exported["api_key"], "")
                self.assertEqual(exported["ota_password"], "")
                request = Request(f"{base}/api/project/import", data=b"{}", headers={"Content-Type": "application/json"})
                with self.assertRaises(HTTPError) as context:
                    urlopen(request)
                self.assertEqual(context.exception.code, 400)
                request = Request(f"{base}/api/serial-monitor", data=b'{"action":"bad"}', headers={"Content-Type": "application/json"})
                with self.assertRaises(HTTPError):
                    urlopen(request)
            finally:
                server.shutdown()
                server.server_close()

    def test_parses_esptool_device_output(self) -> None:
        info = parse_device_info("Chip is ESP32-S3 (revision v0.2)\nMAC: AA:BB:CC:DD:EE:FF\nDetected flash size: 16MB\nCrystal is 40MHz", "COM7")
        self.assertEqual(info["port"], "COM7")
        self.assertEqual(info["chip"], "ESP32-S3 (revision v0.2)")
        self.assertEqual(info["mac"], "AA:BB:CC:DD:EE:FF")
        self.assertEqual(info["flash"], "16MB")

    def test_saving_project_creates_restorable_backup(self) -> None:
        with TemporaryDirectory() as directory:
            state = StudioState(Path(directory))
            first = state.project.to_dict()
            first["name"] = "第一版"
            state.set_project(first)
            second = dict(first)
            second["name"] = "第二版"
            state.set_project(second)

            backups = state.list_backups()
            self.assertEqual(len(backups), 1)
            restored = state.restore_backup(backups[0]["name"])
            self.assertEqual(restored.name, "第一版")

    def test_restore_rejects_path_traversal(self) -> None:
        with TemporaryDirectory() as directory:
            state = StudioState(Path(directory))
            with self.assertRaises(ValueError):
                state.restore_backup("../project.json")


    def test_resource_report_tracks_generated_assets(self) -> None:
        with TemporaryDirectory() as directory:
            state = StudioState(Path(directory))
            project = state.project.to_dict()
            project["wifi_ssid"] = "test"
            project["widgets"] = [{**project["widgets"][0], "kind": "shape", "shape_type": "line", "text": "", "binding": ""}]
            state.set_project(project)
            report = state.resource_report()
            self.assertEqual(report["images"]["count"], 0)
            self.assertGreater(report["yaml"]["bytes"], 0)
            self.assertEqual(report["firmware"]["bytes"], 0)
            self.assertEqual(report["status"], "ok")

    def test_successful_task_runs_post_upload_verification(self) -> None:
        with TemporaryDirectory() as directory:
            task = TaskState()
            started = task.start([sys.executable, "-c", "print('uploaded')"], Path(directory), "烧录", lambda: "ESP32-S3，MAC AA:BB:CC:DD:EE:FF")
            self.assertTrue(started)
            deadline = time.monotonic() + 5
            while task.snapshot()["running"] and time.monotonic() < deadline:
                time.sleep(0.02)
            snapshot = task.snapshot()
            self.assertEqual(snapshot["exit_code"], 0)
            self.assertIn("设备验证通过", snapshot["log"])

    def test_task_rejects_conflicting_second_task(self) -> None:
        task = TaskState()
        self.assertTrue(task.start([sys.executable, "-c", "import time; time.sleep(0.2)"], Path.cwd(), "编译"))
        self.assertFalse(task.start([sys.executable, "-c", "print('no')"], Path.cwd(), "校验"))
        deadline = time.monotonic() + 5
        while task.snapshot()["running"] and time.monotonic() < deadline:
            time.sleep(0.02)


if __name__ == "__main__":
    unittest.main()
