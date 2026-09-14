from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import yaml

from app.models import PageModel, ProjectModel, WidgetModel
from app.yaml_generator import YamlGenerator


class TouchInputTests(unittest.TestCase):
    def test_touch_polling_is_preserved_with_one_or_two_pages(self) -> None:
        for page_count in (1, 2):
            with self.subTest(page_count=page_count), TemporaryDirectory() as directory:
                project = ProjectModel(wifi_ssid="test-network")
                project.pages = [PageModel(id="main_page")]
                if page_count == 2:
                    project.pages.append(PageModel(id="device_settings"))
                project.widgets = [WidgetModel(id="title", text="Touch test")]
                generator = YamlGenerator()
                with patch.object(generator, "_prepare_font", return_value="font.ttf"), \
                     patch.object(generator, "_prepare_images", return_value={}):
                    text = generator.generate(project, Path(directory) / "panel.yaml")
                config = yaml.load(text, Loader=yaml.BaseLoader)
                self.assertEqual(len(config["touchscreen"]), 1)
                touch = config["touchscreen"][0]
                self.assertEqual(touch["platform"], "gt911")
                self.assertEqual(touch["i2c_id"], config["i2c"]["id"])
                self.assertEqual(touch["reset_pin"], "GPIO38")
                self.assertNotIn("interrupt_pin", touch)
                self.assertEqual(touch["update_interval"], "50ms")
                self.assertIn("GT911 touch", touch["on_touch"]["then"][0]["lambda"])
                self.assertEqual(config["lvgl"]["touchscreens"], [touch["id"]])
                self.assertEqual(len(config["lvgl"]["pages"]), page_count)


if __name__ == "__main__":
    unittest.main()
