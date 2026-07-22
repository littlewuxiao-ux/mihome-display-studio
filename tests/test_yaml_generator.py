from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.models import ProjectModel, WidgetModel
from app.yaml_generator import YamlGenerator


class YamlGeneratorTests(unittest.TestCase):
    def make_project(self) -> ProjectModel:
        return ProjectModel(
            wifi_ssid="测试网络",
            wifi_password="secret:with#chars",
            widgets=[
                WidgetModel(id="count", text="在家人数", binding="sensor.people_home_1", font_size=36),
                WidgetModel(id="plus", kind="button", text="人数+1", x=400, y=300,
                            action="input_number.set_value", action_entity="input_number.people_home_1", action_value=1),
            ],
        )

    def test_generates_board_and_lvgl_configuration(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "panel.yaml"
            text = YamlGenerator().generate(self.make_project(), path)
            self.assertIn("platform: mipi_rgb", text)
            self.assertIn("model: RPI", text)
            self.assertIn("platform: gt911", text)
            self.assertIn("id: ui_font_36", text)
            self.assertIn("entity_id: sensor.people_home_1", text)
            self.assertIn("action: input_number.set_value", text)
            self.assertEqual(path.read_text(encoding="utf-8"), text)

    def test_rejects_invalid_entity(self) -> None:
        project = self.make_project()
        project.widgets[0].binding = "not an entity"
        with TemporaryDirectory() as directory, self.assertRaises(ValueError):
            YamlGenerator().generate(project, Path(directory) / "panel.yaml")


if __name__ == "__main__":
    unittest.main()
