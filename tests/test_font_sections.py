from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import yaml

from app.models import ProjectModel, WidgetModel
from app.yaml_generator import YamlGenerator


class FontSectionTests(unittest.TestCase):
    def test_device_actions_keep_fonts_in_their_own_section(self) -> None:
        for actions in (
            (),
            ("device.restart",),
            ("device.safe_mode",),
            ("device.restart", "device.safe_mode", "device.screen_off"),
        ):
            with self.subTest(actions=actions), TemporaryDirectory() as directory:
                project = ProjectModel(wifi_ssid="test-network", widgets=[
                    WidgetModel(id="title", text="测试", font_size=20),
                    WidgetModel(id="icon", kind="icon", text="WiFi", font_size=28,
                                icon_glyph="\U000f05a9", icon_size=32),
                    *(WidgetModel(id=f"action_{index}", kind="button", text="操作",
                                  action=action, font_size=28)
                      for index, action in enumerate(actions)),
                ])
                generator = YamlGenerator()
                target = Path(directory) / "panel.yaml"
                # Asset staging is independent of YAML section construction.
                with patch.object(generator, "_prepare_font", return_value="font.ttf"), \
                     patch.object(generator, "_prepare_images", return_value={}):
                    generator.generate(project, target)
                config = yaml.load(target.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
                fonts = config["font"]
                self.assertIsInstance(fonts, list)
                self.assertEqual({font["id"] for font in fonts},
                                 {"ui_font_20", "ui_font_28", "mdi_font_32"})
                for font in fonts:
                    self.assertTrue(font["file"])
                    self.assertTrue(font["glyphs"])
                    self.assertGreater(int(font["size"]), 0)
                    self.assertNotIn("platform", font)

                platforms = {button["platform"] for button in config.get("button", [])}
                self.assertEqual(platforms, {action.removeprefix("device.") for action in actions
                                             if action != "device.screen_off"})
                if "device.safe_mode" in actions:
                    self.assertNotIsInstance(config["safe_mode"], (list, dict))
                widgets = config["lvgl"]["pages"][0]["widgets"]
                for index, action in enumerate(actions):
                    widget = next(item["button"] for item in widgets
                                  if item.get("button", {}).get("id") == f"action_{index}_root")
                    expected = {"light.turn_off": "backlight"} if action == "device.screen_off" else {
                        "button.press": action.removeprefix("device.") + "_button"}
                    self.assertEqual(widget["on_click"]["then"], [expected])


if __name__ == "__main__":
    unittest.main()
