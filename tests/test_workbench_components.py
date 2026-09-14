from pathlib import Path
import unittest

from app.models import PageModel, ProjectModel, WidgetModel
from app.lvgl_compiler import LvglCompiler, glyphs, icon_specs
from app.yaml_generator import YamlGenerator


def objects(tree):
    if isinstance(tree, dict):
        if "id" in tree:
            yield tree["id"], tree
        for value in tree.values():
            yield from objects(value)
    elif isinstance(tree, list):
        for value in tree:
            yield from objects(value)


class WorkbenchComponentsTests(unittest.TestCase):
    def compile(self, widgets, **kwargs):
        p = ProjectModel(wifi_ssid="test", widgets=widgets, **kwargs)
        self.assertEqual(p.validate(), [])
        return LvglCompiler(p, YamlGenerator()).sections()

    def test_read_only_number_and_explicit_navigation(self):
        data = self.compile([
            WidgetModel(id="count", kind="shape", binding="input_number.guests", value_decimals=2, value_suffix="人", target_page="details"),
            WidgetModel(id="next", kind="shape", tap_mode="page", target_page="details", action="light.toggle", action_entity="light.room"),
        ], pages=[PageModel(id="main_page"), PageModel(id="details")])
        nodes = dict(objects(data))
        self.assertNotIn("on_click", nodes["count_root"])
        self.assertFalse(nodes["count_root"]["clickable"])
        self.assertEqual(nodes["next_root"]["on_click"]["then"][0]["lvgl.page.show"]["id"], "details")
        self.assertIn("%.2f人", str(data["sensor"]))
        self.assertNotIn("homeassistant.action", str(data))

    def test_slider_reads_without_echo_and_sends_scaled_value_on_release(self):
        data = self.compile([WidgetModel(id="slider", kind="slider", binding="input_number.amount", value_decimals=2, progress_min=-1, progress_max=4, width=86, height=33)])
        nodes = dict(objects(data))
        rail = nodes["slider_control"]
        self.assertEqual((rail["min_value"], rail["max_value"]), (-100, 400))
        self.assertLess(rail["width"], 86)
        self.assertEqual(rail["height"], 8)
        self.assertNotIn("homeassistant.action", str(data["sensor"]))
        self.assertNotIn("homeassistant.action", str(rail["on_value"]))
        action = rail["on_release"][0]["homeassistant.action"]
        self.assertEqual(action["action"], "input_number.set_value")
        self.assertEqual(action["data"]["entity_id"], "input_number.amount")
        self.assertIn("100.0f", action["data"]["value"])

    def test_accessory_and_empty_initial_state_can_receive_icon_later(self):
        data = self.compile([
            WidgetModel(id="ring", kind="progress_circle", icon_glyph="\U000F0004", icon_offset_y=-20),
            WidgetModel(id="presence", kind="icon", binding="input_boolean.person", binding_type="state", show_fixed_icon=False,
                        state_variants=[dict(value="off", label="", icon_glyph="", depth="inset"), dict(value="on", label="在", icon_glyph="\U000F0004", icon_size=44, depth="raised")]),
        ])
        nodes = dict(objects(data))
        self.assertEqual(nodes["ring_icon"]["y"], -20)
        self.assertEqual(nodes["presence_icon"]["text"], "")
        callback = str(data["text_sensor"])
        for expected in ["presence_icon", "mdi_font_44", "presence_bevel_top", "lv_obj_set_style_shadow_width", "lv_obj_set_style_text_color"]:
            self.assertIn(expected, callback)
        self.assertFalse(nodes["presence_bevel_top"]["clickable"])
        self.assertNotIn("homeassistant.action", str(data))

    def test_battery_has_visual_and_measurement_and_missing_value_guard(self):
        data = self.compile([WidgetModel(id="battery", kind="battery", binding="device:battery_level", battery_display="full")], battery_monitor=True, battery_chip="ina226")
        nodes = dict(objects(data))
        self.assertIn("battery_control", nodes)
        self.assertIn("battery_battery_status_icon", nodes)
        self.assertTrue(nodes["battery_energy_wh"]["restore_value"])
        self.assertEqual(nodes["battery_meter"]["platform"], "ina226")
        self.assertIn("std::isfinite", nodes["battery_level"]["lambda"])
        self.assertIn("lv_bar_set_value", str(data["interval"]))

    def test_old_invisible_icon_migrates_once_and_respects_new_hide_setting(self):
        p = ProjectModel.from_dict(dict(schema_version=29, widgets=[dict(id="adult", kind="icon", icon_glyph="\U000F0004", show_fixed_title=False, show_fixed_icon=False)]))
        self.assertTrue(p.widgets[0].show_fixed_icon)
        p.widgets[0].show_fixed_icon = False
        self.assertFalse(ProjectModel.from_dict(p.to_dict()).widgets[0].show_fixed_icon)

    def test_named_state_survives_save_and_fonts_include_units_and_state_icons(self):
        w = WidgetModel(id="ac", kind="icon", state_preview="cool", value_suffix="°C", state_variants=[dict(value="cool", label="制冷", icon_glyph="\U000F0717", icon_size=48)])
        w.clamp()
        self.assertEqual(w.state_preview, "cool")
        self.assertIn(("\U000F0717", 48), icon_specs(w))
        self.assertIn("制", glyphs(ProjectModel(widgets=[w])))

    def test_shared_widgets_get_unique_instances_and_one_subscription(self):
        data = self.compile([WidgetModel(id="shared", kind="shape", binding="sensor.value", pages=["main_page", "details"])], pages=[PageModel(id="main_page"), PageModel(id="details")])
        nodes = dict(objects(data))
        self.assertIn("shared_details_root", nodes)
        self.assertIn("shared_root", nodes)
        self.assertEqual(len(data["sensor"]), 1)
        self.assertEqual(len(data["sensor"][0]["on_value"]), 2)

    def test_navigation_slider_cannot_send_an_entity_command(self):
        data = self.compile([WidgetModel(id="navigate", kind="slider", binding="input_number.level", tap_mode="page", target_page="details")],
                            pages=[PageModel(id="main_page"), PageModel(id="details")])
        nodes = dict(objects(data))
        self.assertFalse(nodes["navigate_control"]["clickable"])
        self.assertNotIn("on_release", nodes["navigate_control"])
        self.assertNotIn("homeassistant.action", str(data))
        self.assertTrue(nodes["navigate_root"]["clickable"])

    def test_dropdown_sends_selection_only_and_readonly_is_disabled(self):
        data = self.compile([
            WidgetModel(id="choice", kind="dropdown", binding="input_select.mode", binding_type="state", tap_mode="ha", action="input_select.select_option"),
            WidgetModel(id="readonly_choice", kind="dropdown", binding="input_select.mode", binding_type="state"),
        ])
        nodes = dict(objects(data["lvgl"]))
        self.assertNotIn("on_click", nodes["choice_root"])
        self.assertIn("on_change", nodes["choice_root"])
        self.assertFalse(nodes["readonly_choice_root"]["clickable"])
        self.assertNotIn("homeassistant.action", str(data["text_sensor"]))

    def test_action_only_state_mapping_does_not_override_configured_colour(self):
        data = self.compile([WidgetModel(id="plus", kind="shape", shape_type="circle",
                                         background_color="#FA9FC8", background_opacity=100,
                                         state_mapping=True, action="input_number.increment",
                                         action_entity="input_number.people", tap_mode="ha")])
        nodes = dict(objects(data))
        self.assertEqual(nodes["plus_root"]["bg_color"], int("FA9FC8", 16))
        self.assertEqual(nodes["plus_root"]["bg_opa"], "100%")
        self.assertNotIn("plus_bevel_top", nodes)

    def test_state_variant_keeps_shared_container_opacity(self):
        data = self.compile([WidgetModel(id="mode", kind="shape", binding="switch.mode", binding_type="state",
                                         background_color="#112233", background_opacity=0,
                                         state_variants=[dict(value="off", label="", background_color="#334455",
                                                               opacity=100, depth="inset"),
                                                         dict(value="on", label="", background_color="#556677",
                                                               opacity=100, depth="raised")])])
        nodes = dict(objects(data))
        self.assertEqual(nodes["mode_root"]["bg_opa"], "0%")
        self.assertNotIn("lv_obj_set_style_bg_opa", str(data["text_sensor"]))


if __name__ == "__main__":
    unittest.main()
