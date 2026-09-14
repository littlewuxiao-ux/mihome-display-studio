from __future__ import annotations

import unittest

from app.models import PageModel, ProjectModel, WidgetModel


class ProjectModelTests(unittest.TestCase):
    def test_legacy_project_gets_schema_version(self) -> None:
        project = ProjectModel.from_dict({"name": "旧项目", "wifi_ssid": "wifi", "widgets": []})
        self.assertEqual(project.schema_version, 30)
        self.assertEqual(project.to_dict()["schema_version"], 30)
        self.assertEqual(project.battery_capacity_mwh, 11100)
        self.assertEqual(WidgetModel(id="defaults").battery_display, "percent")
        self.assertEqual(WidgetModel(id="defaults").trend_axis_color, "#AEB7C2")

    def test_missing_parent_is_detached_during_load(self) -> None:
        project = ProjectModel.from_dict({
            "pages": [{"id": "main_page"}],
            "widgets": [{
                "id": "orphan",
                "kind": "label",
                "text": "orphan",
                "parent_id": "deleted_container",
            }],
        })

        self.assertEqual(project.widgets[0].parent_id, "")
        self.assertEqual(project.firmware_version, "1.0.0")

    def test_export_removes_sensitive_values(self) -> None:
        project = ProjectModel(wifi_ssid="wifi", wifi_password="secret", api_key="api", ota_password="ota")
        exported = project.to_dict(include_secrets=False)
        self.assertEqual(exported["wifi_password"], "")
        self.assertEqual(exported["api_key"], "")
        self.assertEqual(exported["ota_password"], "")

    def test_duplicate_ids_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ProjectModel.from_dict({
                "pages": [PageModel(id="main").__dict__, PageModel(id="main").__dict__],
                "widgets": [WidgetModel(id="same", page="main").__dict__, WidgetModel(id="same", page="main").__dict__],
            })

    def test_rejects_invalid_firmware_version(self) -> None:
        project = ProjectModel(wifi_ssid="wifi", firmware_version="bad version")
        self.assertIn("固件版本", "\n".join(project.validate()))

        project = ProjectModel.from_dict({"wifi_ssid": "wifi", "future_setting": True})
        self.assertEqual(project.wifi_ssid, "wifi")

    def test_legacy_state_wifi_signal_migrates_to_wifi_status(self) -> None:
        project = ProjectModel.from_dict({"wifi_ssid": "wifi", "widgets": [{"id": "wifi", "binding": "device:wifi_signal", "binding_type": "state"}]})
        self.assertEqual(project.widgets[0].binding, "device:wifi_status")


    def test_transparent_shape_and_gradient_defaults(self) -> None:
        project = ProjectModel.from_dict({"wifi_ssid": "wifi", "pages": [{"id": "main", "background_color": "#112233", "background_color_2": "#445566", "background_gradient": "horizontal"}], "widgets": [{"id": "line", "kind": "shape", "shape_type": "line", "text": "", "background_opacity": 0, "page": "main"}]})
        self.assertEqual(project.widgets[0].background_opacity, 0)
        self.assertEqual(project.pages[0].background_gradient, "horizontal")

    def test_full_battery_widget_keeps_readable_size(self) -> None:
        widget = WidgetModel(id="battery", kind="battery", battery_display="full", width=56, height=20, x=744)
        widget.clamp()
        self.assertGreaterEqual(widget.width, 280)
        self.assertGreaterEqual(widget.height, 60)
        self.assertLessEqual(widget.x + widget.width, 800)

    def test_percent_battery_keeps_canvas_size(self) -> None:
        widget = WidgetModel(id="battery", kind="battery", battery_display="percent", width=58, height=22, x=722)
        widget.clamp()
        self.assertEqual((widget.width, widget.height, widget.x), (58, 22, 722))

    def test_widget_can_belong_to_multiple_pages(self) -> None:
        raw = ProjectModel().to_dict()
        raw["pages"].append({"id": "second", "name": "第二页"})
        raw["widgets"] = [{"id": "shared", "pages": ["main_page", "second"]}]
        project = ProjectModel.from_dict(raw)
        self.assertEqual(project.validate(), ["请填写WiFi名称"])
        self.assertEqual(project.widgets[0].pages, ["main_page", "second"])

    def test_editor_state_migrates_and_default_page_is_validated(self) -> None:
        project = ProjectModel.from_dict({
            "pages": [{"id": "first"}, {"id": "second"}],
            "default_page": "missing",
            "widgets": [{"id": "item", "page": "first"}],
        })
        self.assertEqual(project.default_page, "first")
        self.assertFalse(project.widgets[0].locked)
        self.assertFalse(project.widgets[0].hidden)
        self.assertEqual(project.widgets[0].opacity, 100)

        project.default_page = "missing"
        self.assertIn("默认启动界面不存在", project.validate_project_structure())

    def test_recovers_default_question_mark_placeholders(self) -> None:
        project = ProjectModel.from_dict({
            "name": "????",
            "pages": [{"id": "main_page", "name": "???"}],
            "widgets": [{"id": "people_1", "text": "????"}],
        })
        self.assertEqual(project.name, "米家中枢触控屏")
        self.assertEqual(project.pages[0].name, "主界面")
        self.assertEqual(project.widgets[0].text, "在家人数1")


if __name__ == "__main__":
    unittest.main()
