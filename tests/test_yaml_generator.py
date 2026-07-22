from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.models import PageModel, ProjectModel, WidgetModel
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

    def test_generates_image_component(self) -> None:
        from PIL import Image
        with TemporaryDirectory() as directory:
            image_path = Path(directory) / "sample.png"
            Image.new("RGBA", (64, 48), (47, 125, 246, 180)).save(image_path)
            project = self.make_project()
            project.widgets.append(WidgetModel(id="logo", kind="image", text="标志", width=64, height=48, asset_path=str(image_path)))
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
            self.assertIn("image:\n  - platform: file", text)
            self.assertIn("id: logo_asset", text)
            self.assertIn("logo_asset_64x48.png", text)
            self.assertIn("src: logo_asset", text)

    def test_generates_pages_shapes_layers_and_content_image(self) -> None:
        from PIL import Image
        with TemporaryDirectory() as directory:
            image_path = Path(directory) / "button.png"
            Image.new("RGB", (120, 80), (47, 125, 246)).save(image_path)
            project = self.make_project()
            project.pages.append(PageModel(id="settings_page", name="设置"))
            project.widgets.extend([
                WidgetModel(id="back", kind="page_button", text="返回", page="settings_page", target_page="main_page", z_index=4),
                WidgetModel(id="line", kind="shape", page="settings_page", shape_type="line", border_color="#FF0000", z_index=1),
                WidgetModel(id="tile", kind="button", text="图标按钮", page="settings_page", content_asset_path=str(image_path), image_fit="cover", z_index=2),
            ])
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
            self.assertIn("id: settings_page", text)
            self.assertIn("- lvgl.page.show:", text)
            self.assertIn("id: main_page", text)
            self.assertIn("- line:", text)
            self.assertIn("line_color: 0xFF0000", text)
            self.assertIn("id: tile_content_asset", text)
            self.assertLess(text.index("id: line_root"), text.index("id: tile_root"))
            self.assertLess(text.index("id: tile_root"), text.index("id: back_root"))

    def test_generates_progress_geometry_and_button_feedback(self) -> None:
        project = self.make_project()
        project.widgets.extend([
            WidgetModel(id="ellipse", kind="shape", shape_type="ellipse", text="CPU", ellipse_radius_x=90, ellipse_radius_y=45),
            WidgetModel(id="direction", kind="shape", shape_type="line", text="方向", line_length=200, line_angle=-30),
            WidgetModel(id="cpu", kind="progress_circle", binding="sensor.cpu_use", progress_min=0, progress_max=100),
            WidgetModel(id="gpu", kind="progress_bar", binding="sensor.gpu_use", show_value="value"),
        ])
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
            self.assertIn("width: 180", text)
            self.assertIn("id: direction_line", text)
            self.assertIn("- arc:", text)
            self.assertIn("- bar:", text)
            self.assertIn("- lvgl.arc.update:", text)
            self.assertIn("- lvgl.bar.update:", text)
            self.assertIn("pressed:", text)

    def test_generates_device_state_binding(self) -> None:
        project = self.make_project()
        project.widgets.append(WidgetModel(id="aircon", kind="shape", text="空调", binding="climate.living_room", binding_type="state"))
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
            self.assertIn("text_sensor:", text)
            self.assertIn("entity_id: climate.living_room", text)
            self.assertIn("std::string(\"空调 \") + x", text)

    def test_rejects_invalid_entity(self) -> None:
        project = self.make_project()
        project.widgets[0].binding = "not an entity"
        with TemporaryDirectory() as directory, self.assertRaises(ValueError):
            YamlGenerator().generate(project, Path(directory) / "panel.yaml")


if __name__ == "__main__":
    unittest.main()
