from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

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

    def test_fallback_ap_ssid_is_ascii_and_within_wifi_limit(self) -> None:
        project = self.make_project()
        project.name = "这是一个非常长的中文项目名称会超过无线网络名称限制"
        project.device_name = "mijia-hub-panel-with-an-excessively-long-device-name"
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        ap_ssid = next(line.split('"')[1] for line in text.splitlines() if line.strip().startswith('ssid: "mijia-hub'))
        self.assertTrue(ap_ssid.isascii())
        self.assertLessEqual(len(ap_ssid.encode("utf-8")), 32)

    def test_dynamic_units_and_touch_diagnostics_are_generated(self) -> None:
        project = self.make_project()
        project.widgets[0].value_suffix = "°C"
        project.widgets[0].state_on_text = "已连接"
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        glyph_line = next(line for line in text.splitlines() if "glyphs:" in line)
        self.assertIn("°", glyph_line)
        self.assertIn("C", glyph_line)
        self.assertIn("(", glyph_line)
        self.assertIn(")", glyph_line)
        self.assertIn("|", glyph_line)
        for character in "onoffcoolheatunavailable":
            self.assertIn(character, glyph_line)
        for character in "已连接":
            self.assertIn(character, glyph_line)
        self.assertIn('ESP_LOGI("touch", "GT911 touch x=%d y=%d", touch.x, touch.y);', text)
        self.assertNotIn("interrupt_pin: GPIO18", text)
        self.assertIn("level: DEBUG", text)

    def test_climate_multistate_appearance_is_generated(self) -> None:
        project = self.make_project()
        project.widgets = [WidgetModel(
            id="bedroom_ac", kind="button", text="卧室空调",
            binding="climate.xiaomi_cn_940989462_m28", binding_type="state",
            state_mapping=True, action="climate.toggle",
            action_entity="climate.xiaomi_cn_940989462_m28", tap_mode="ha",
            state_variants=[
                {"value": value, "label": label, "background_color": color, "icon_glyph": ""}
                for value, label, color in [
                    ("off", "关闭", "#58616B"), ("cool", "制冷", "#2F7DF6"),
                    ("heat", "制热", "#E5534B"), ("dry", "除湿", "#F5A623"),
                    ("fan_only", "送风", "#45C46A"), ("auto", "自动", "#7B61A8"),
                ]
            ],
        )]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        for state in ("off", "cool", "heat", "dry", "fan_only"):
            self.assertIn(f'x == "{state}"', text)
        self.assertIn("action: climate.toggle", text)
        self.assertIn("shadow_width: !lambda |-", text)
        self.assertNotIn("shadow_width: !lambda return", text)

    def test_input_number_slider_syncs_both_directions(self) -> None:
        project = self.make_project()
        project.widgets = [WidgetModel(
            id="sleep_count", kind="slider", binding="input_number.sleep_count",
            binding_type="number", progress_min=0, progress_max=4,
        )]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("entity_id: input_number.sleep_count", text)
        self.assertIn("action: input_number.set_value", text)
        self.assertIn("- lvgl.slider.update:", text)

    def test_generates_material_icon_and_text_offsets(self) -> None:
        project = self.make_project()
        project.widgets.append(WidgetModel(id="wifi_icon", kind="icon", text="WiFi", icon_name="WiFi", icon_glyph="󰖩", font_size=40, text_offset_x=3, text_offset_y=-2))
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("id: mdi_font_40", text)
        self.assertIn("materialdesignicons-webfont.ttf", text)
        self.assertIn("x: 3", text)
        self.assertIn("y: -2", text)

    def test_state_icon_syncs_glyph_and_toggle_action(self) -> None:
        project = self.make_project()
        project.widgets = [WidgetModel(
            id="person_icon", kind="icon", text="男性", binding="input_boolean.man_home", binding_type="state",
            state_mapping=True, state_on_value="on", state_icon_enabled=True,
            state_icon_on_glyph="\U000F064D", state_icon_off_glyph="\U000F000D",
            tap_mode="ha", action="homeassistant.toggle", action_entity="input_boolean.man_home",
        )]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("return std::string(x == \"on\" ?", text)
        self.assertIn("󰙍", text)
        self.assertIn("homeassistant.action", text)

    def test_slider_geometry_matches_editor_preview(self) -> None:
        project = self.make_project()
        project.widgets = [WidgetModel(
            id="volume", kind="slider", binding="input_number.volume", binding_type="number",
            progress_min=0, progress_max=100, progress_value=0,
        )]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("entity_id: input_number.volume", text)
        self.assertIn("- lvgl.slider.update:", text)
        self.assertIn("id: volume_root", text)
        self.assertIn("x: 32", text)
        self.assertIn("width: 156", text)
        self.assertIn("height: 8", text)
        self.assertIn("width: 22", text)
        self.assertNotIn("pad_left: 12", text)
        self.assertIn("action: input_number.set_value", text)
        self.assertIn("value: !lambda return x;", text)

    def test_native_controls_use_binding_for_state_and_actions(self) -> None:
        project = self.make_project()
        project.widgets = [
            WidgetModel(id="presence", kind="switch", binding="input_boolean.person_home", binding_type="state"),
            WidgetModel(id="mode", kind="dropdown", binding="input_select.mode", binding_type="state", control_options="自动\n制冷"),
            WidgetModel(id="setpoint", kind="spinbox", binding="input_number.setpoint", binding_type="number"),
            WidgetModel(id="scene", kind="button", text="执行", binding="scene.movie", action="scene.turn_on", action_entity=""),
        ]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("action: input_boolean.turn_on", text)
        self.assertIn("action: input_boolean.turn_off", text)
        self.assertIn("- lvgl.dropdown.update:", text)
        self.assertIn("action: input_select.select_option", text)
        self.assertIn("- lvgl.spinbox.update:", text)
        self.assertIn("action: input_number.set_value", text)
        self.assertIn("entity_id: scene.movie", text)

    def test_icon_can_switch_pages_without_legacy_page_button(self) -> None:
        project = self.make_project()
        project.pages.append(PageModel(id="details", name="详情"))
        project.widgets.append(WidgetModel(id="next_icon", kind="icon", text="下一页", icon_name="主页", icon_glyph="󰋜", tap_mode="page", target_page="details"))
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("id: next_icon_root", text)
        self.assertIn("id: details", text)
        self.assertIn("lvgl.page.show:", text)
        self.assertIn("animation: NONE", text)
        self.assertIn("time: 0ms", text)
        self.assertIn("buffer_size: 100%", text)

    def test_runtime_text_uses_fitted_font_and_time_ignores_state_mapping(self) -> None:
        project = self.make_project()
        project.widgets.append(WidgetModel(id="clock", kind="shape", text="时间", binding="device:current_time", binding_type="state", state_mapping=True, state_off_text="关闭", width=180, height=50, font_size=40))
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        effective = YamlGenerator._effective_font_size(project.widgets[-1])
        self.assertLess(effective, 40)
        self.assertIn(f"text_font: ui_font_{effective}", text)
        self.assertIn("width: 100%", text)
        self.assertIn("long_mode: CLIP", text)
        self.assertIn('return std::string("时间 ") + x;', text)

    def test_shape_accessory_icon_and_exact_font_size(self) -> None:
        project = self.make_project()
        project.widgets.append(WidgetModel(id="plus_shape", kind="shape", text="+", font_size=72, auto_fit_text=False, icon_name="加", icon_glyph="󰐕", icon_size=64, icon_offset_x=0, icon_offset_y=0))
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("id: ui_font_72", text)
        self.assertIn("id: mdi_font_64", text)
        self.assertIn("id: plus_shape_icon", text)
        self.assertIn("text_font: mdi_font_64", text)

    def test_generates_board_and_lvgl_configuration(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "panel.yaml"; text = YamlGenerator().generate(self.make_project(), path); self.assertIn("project:\n    name: mijia.display_studio", text); self.assertIn('version: "1.0.0"', text)


            self.assertIn("model: RPI", text)
            self.assertIn("platform: gt911", text)
            expected_size = YamlGenerator._effective_font_size(self.make_project().widgets[0])
            self.assertIn(f"id: ui_font_{expected_size}", text)
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
            self.assertIn("id: direction_root", text)
            self.assertIn("- arc:", text)
            self.assertIn("- bar:", text)
            self.assertIn("- lvgl.arc.update:", text)
            self.assertIn("- lvgl.bar.update:", text)
            self.assertIn("pressed:", text)

    def test_progress_meter_can_include_an_accessory_icon(self) -> None:
        project = self.make_project()
        project.widgets.append(WidgetModel(id="temperature", kind="progress_circle", text="温度", binding="sensor.temperature", icon_name="温度计", icon_glyph="󰔏", icon_size=36, icon_offset_y=-28, text_offset_y=25))
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("id: temperature_icon", text)
        self.assertIn("text_font: mdi_font_36", text)
        self.assertIn("y: -28", text)

    def test_generates_native_lvgl_controls(self) -> None:
        project = self.make_project()
        project.widgets.extend([
            WidgetModel(id="volume", kind="slider", progress_min=0, progress_max=100, progress_value=35),
            WidgetModel(id="enabled", kind="switch", control_checked=True),
            WidgetModel(id="agree", kind="checkbox", text="启用自动模式", control_checked=True),
            WidgetModel(id="mode", kind="dropdown", control_options="普通\n观影\n晚安", control_selected=1),
            WidgetModel(id="roller", kind="roller", control_options="低\n中\n高", control_selected=1),
            WidgetModel(id="number", kind="spinbox", progress_value=25, control_digits=3),
            WidgetModel(id="loading", kind="spinner"),
            WidgetModel(id="status_led", kind="led", progress_value=80),
            WidgetModel(id="code", kind="qrcode", control_text="https://esphome.io"),
            WidgetModel(id="entry", kind="textarea", control_text="请输入"),
            WidgetModel(id="keys", kind="keyboard", control_target="entry"),
        ])
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("- slider:", text)
        self.assertIn("value: 35", text)
        self.assertIn("- switch:", text)
        self.assertIn("checked: true", text)
        self.assertIn("- checkbox:", text)
        self.assertIn('text: "启用自动模式"', text)
        self.assertIn("- dropdown:", text)
        self.assertIn('              - "观影"', text)
        self.assertIn("selected_index: 1", text)
        for kind in ("roller", "spinbox", "spinner", "led", "qrcode", "textarea", "keyboard"):
            self.assertIn(f"- {kind}:", text)
        self.assertIn("textarea: entry_root", text)

    def test_generates_sensor_trend_chart(self) -> None:
        project = self.make_project()
        project.widgets.append(WidgetModel(id="temperature_trend", kind="trend_chart", text="温度", binding="sensor.temperature", progress_min=-10, progress_max=50, value_suffix="°C", width=320, height=180, trend_time_labels="exact"))
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("type: std::array<float, 120>", text)
        self.assertIn("id: temperature_trend_samples", text)
        self.assertIn("- lvgl.line.update:", text)
        self.assertIn("id: temperature_trend_trend", text)
        self.assertIn("for (size_t i = 0; i < 119; i++)", text)
        self.assertIn("interval: 60s", text)
        self.assertIn("id: temperature_trend_x_tick_1", text)
        self.assertIn("localtime_r(&stamp, &value_time);", text)

    def test_generates_button_matrix_and_lightweight_table(self) -> None:
        project = self.make_project()
        project.widgets.extend([
            WidgetModel(id="modes", kind="buttonmatrix", control_options="普通|观影\n按摩|晚安"),
            WidgetModel(id="values", kind="table", control_options="名称|数值\n温度|25"),
        ])
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertEqual(text.count("- buttonmatrix:"), 2)
        self.assertIn("one_checked: true", text)
        self.assertIn("one_checked: false", text)
        self.assertIn("disabled: true", text)

    def test_generates_message_box_and_open_action(self) -> None:
        project = self.make_project()
        project.widgets.extend([
            WidgetModel(id="confirm", kind="msgbox", text="确认操作", control_text="是否继续？", control_options="确定\n取消"),
            WidgetModel(id="open_confirm", kind="button", text="打开提示", tap_mode="msgbox", target_page="confirm"),
        ])
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("msgboxes:", text)
        self.assertIn("id: confirm_root", text)
        self.assertIn("- lvgl.widget.show:", text)

    def test_generates_nested_flex_container(self) -> None:
        project = self.make_project()
        project.widgets.extend([
            WidgetModel(id="controls", kind="container", text="控制组", width=400, height=180, layout_type="flex", flex_flow="row_wrap"),
            WidgetModel(id="first", kind="button", text="第一项", parent_id="controls", width=120, height=50),
            WidgetModel(id="second", kind="switch", parent_id="controls", width=72, height=38),
        ])
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("type: flex", text)
        self.assertIn("flex_flow: row_wrap", text)
        self.assertEqual(text.count("id: first_root"), 1)
        self.assertGreater(text.index("id: first_root"), text.index("id: controls_root"))

    def test_generates_nested_grid_container(self) -> None:
        project = self.make_project()
        project.widgets.extend([
            WidgetModel(id="grid", kind="container", layout_type="grid", grid_rows=2, grid_columns=3),
            WidgetModel(id="cell", kind="button", text="单元格", parent_id="grid", grid_row=1, grid_column=2, grid_column_span=1),
        ])
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("type: grid", text)
        self.assertIn("grid_columns: 3", text)
        self.assertIn("grid_cell_row_pos: 1", text)
        self.assertIn("grid_cell_column_pos: 2", text)

    def test_generates_tabview_and_tileview_children(self) -> None:
        project = self.make_project()
        project.widgets.extend([
            WidgetModel(id="tabs", kind="tabview", view_items="主页\n设置"),
            WidgetModel(id="tab_child", kind="button", text="设置项", parent_id="tabs", view_index=1),
            WidgetModel(id="tiles", kind="tileview"),
            WidgetModel(id="tile_child", kind="shape", text="磁贴内容", parent_id="tiles", grid_row=0, grid_column=1),
        ])
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("- tabview:", text)
        self.assertIn('name: "设置"', text)
        self.assertIn("id: tab_child_root", text)
        self.assertIn("- tileview:", text)
        self.assertIn("column: 1", text)
        self.assertIn("id: tile_child_root", text)

    def test_generates_device_state_binding(self) -> None:
        project = self.make_project()
        project.widgets.append(WidgetModel(id="aircon", kind="shape", text="空调", binding="climate.living_room", binding_type="state"))
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
            self.assertIn("text_sensor:", text)
            self.assertIn("entity_id: climate.living_room", text)
            self.assertIn("std::string(\"空调 \") + x", text)

    def test_state_switch_can_follow_ha_with_color_and_depth(self) -> None:
        project = self.make_project()
        project.widgets.append(WidgetModel(id="light_switch", kind="button", text="灯光", binding="light.living_room", binding_type="state", state_mapping=True, state_visual="both", action="light.toggle", action_entity="light.living_room"))
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("entity_id: light.living_room", text)
        self.assertIn("bg_color: !lambda |-", text)
        self.assertNotIn('\n            opa: !lambda', text)
        self.assertNotIn('border_width: !lambda', text)
        self.assertIn('bg_opa: 100%', text)
        self.assertIn("action: light.toggle", text)

    def test_line_skips_font_and_supports_transparency_and_gradient(self) -> None:
        project = ProjectModel(wifi_ssid="wifi", pages=[PageModel(id="main", background_color="#112233", background_color_2="#445566", background_gradient="vertical")], widgets=[WidgetModel(id="line", kind="shape", shape_type="line", text="", page="main"), WidgetModel(id="panel", kind="shape", text="", page="main", background_opacity=0)])
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
            self.assertNotIn("font:\n", text)
            self.assertIn("bg_grad_color: 0x445566", text)
            self.assertIn("bg_grad_dir: VER", text)
            self.assertIn("- line:\n            id: line_root", text)
            self.assertNotIn("id: line_root\n            x: 20\n            y: 20\n            width", text)
            self.assertIn("bg_opa: 0%", text)

    def test_shared_widget_is_rendered_on_each_page(self) -> None:
        project = self.make_project()
        project.pages.append(PageModel(id="second", name="第二页"))
        project.widgets = [WidgetModel(id="shared", kind="shape", text="共享", pages=["main_page", "second"])]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("id: shared_main_page_root", text)
        self.assertIn("id: shared_second_root", text)

    def test_shared_dynamic_widget_updates_all_page_instances(self) -> None:
        project = self.make_project()
        project.pages.append(PageModel(id="settings", name="设置"))
        project.pages.append(PageModel(id="other", name="其他"))
        project.widgets = [
            WidgetModel(id="temperature", kind="label", binding="sensor.temperature", pages=["main_page", "settings"]),
            WidgetModel(id="mode", kind="button", binding="switch.mode", binding_type="state", state_mapping=True, pages=["main_page", "settings"]),
            WidgetModel(id="trend", kind="trend_chart", binding="sensor.temperature", pages=["main_page", "settings"]),
        ]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("id: [temperature_main_page_label, temperature_settings_label]", text)
        self.assertIn("id: [mode_main_page_root, mode_settings_root]", text)
        self.assertIn("id: [trend_main_page_trend, trend_settings_trend]", text)
        self.assertNotIn("id: temperature_label", text)

    def test_small_widget_shared_by_every_page_uses_top_layer_once(self) -> None:
        project = self.make_project()
        project.pages.append(PageModel(id="settings", name="设置"))
        project.widgets = [WidgetModel(id="clock", kind="label", binding="device:current_time", pages=["main_page", "settings"], width=160, height=40)]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("  top_layer:\n    widgets:\n      - obj:", text)
        self.assertEqual(text.count("id: clock_root"), 1)
        self.assertIn("id: clock_label", text)
        self.assertNotIn("clock_main_page", text)

    def test_scrollable_flex_container_uses_native_lvgl_scroll_flags(self) -> None:
        project = self.make_project()
        project.widgets = [WidgetModel(id="scroll", kind="container", layout_type="flex", flex_flow="column", container_scrollable=True, container_scroll_dir="VER", container_scrollbar="AUTO", container_scroll_momentum=True, container_scroll_elastic=True)]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("scrollable: true", text)
        self.assertIn("scroll_dir: VER", text)
        self.assertIn("scrollbar_mode: AUTO", text)
        self.assertIn("scroll_momentum: true", text)
        self.assertIn("scroll_elastic: true", text)

    def test_default_page_is_first_and_hidden_widget_is_omitted(self) -> None:
        project = self.make_project()
        project.pages.append(PageModel(id="startup", name="启动页"))
        project.default_page = "startup"
        project.widgets = [
            WidgetModel(id="visible", text="显示", page="startup", pages=["startup"]),
            WidgetModel(id="secret", text="隐藏", page="startup", pages=["startup"], hidden=True),
        ]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertLess(text.index("id: startup"), text.index("id: main_page"))
        self.assertIn("id: visible_root", text)
        self.assertNotIn("secret_root", text)

    def test_rejects_invalid_entity(self) -> None:
        project = self.make_project()
        project.widgets[0].binding = "not an entity"
        with TemporaryDirectory() as directory, self.assertRaises(ValueError):
            YamlGenerator().generate(project, Path(directory) / "panel.yaml")

    def test_generates_device_information_bindings_and_opacity(self) -> None:
        project = self.make_project()
        project.widgets = [
            WidgetModel(id="signal", kind="shape", text="信号", binding="device:wifi_signal", opacity=65),
            WidgetModel(id="ip", kind="shape", text="IP", binding="device:ip_address", binding_type="state"),
        ]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("platform: wifi_signal", text)
        self.assertIn("platform: wifi_info", text)
        self.assertIn("opa: 65%", text)

    def test_opaque_rgba_background_skips_alpha_and_scrolling(self) -> None:
        project = self.make_project()
        with TemporaryDirectory() as directory:
            source = Path(directory) / "background.png"
            Image.new("RGBA", (800, 480), (20, 30, 40, 255)).save(source)
            project.widgets = [WidgetModel(id="background", kind="shape", text="", content_asset_path=str(source), width=800, height=480)]
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertNotIn("transparency: alpha_channel", text)
        self.assertIn("scrollable: false", text)

    def test_firmware_and_wifi_status_use_compact_local_text(self) -> None:
        project = self.make_project()
        project.firmware_version = "2.4.1"
        project.widgets = [
            WidgetModel(id="firmware", kind="shape", text="固件", binding="device:firmware_version", binding_type="state"),
            WidgetModel(id="wifi", kind="shape", text="WiFi", binding="device:wifi_status", binding_type="state"),
        ]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn('return {"2.4.1"};', text)
        self.assertIn('wifi::global_wifi_component->is_connected()', text)
        self.assertNotIn("platform: version", text)

    def test_generates_ina_battery_component(self) -> None:
        project = self.make_project()
        project.battery_monitor = True
        project.battery_chip = "ina226"
        project.widgets = [WidgetModel(id="battery", kind="battery", text="电池", binding="device:battery_level", battery_display="full")]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("platform: ina226", text)
        self.assertIn("id: ina_battery_voltage", text)
        self.assertIn("充电", text)
        self.assertIn("id: battery_root", text)
        self.assertIn("id: battery_energy_wh", text)
        self.assertIn("restore_value: true", text)
        self.assertIn("battery_energy_wh) * 100.0f", text)
        self.assertIn("state <= 20.0f", text)
        self.assertIn("current > 0.005f", text)
        self.assertIn("id: battery_battery_status_icon", text)
        self.assertIn("\U000F0079", text)
        self.assertIn("\U000F0084", text)

    def test_percent_battery_has_no_default_text_prefix(self) -> None:
        project = self.make_project()
        project.battery_monitor = True
        project.widgets = [WidgetModel(id="battery", kind="battery", text="", binding="device:battery_level", battery_display="percent")]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("id: battery_battery_status_icon", text)
        self.assertNotIn('text: "电池', text)
        self.assertIn("border_width: 0", text)

    def test_battery_remaining_uses_yaml_block_lambda(self) -> None:
        project = self.make_project()
        project.battery_monitor = True
        project.widgets = [WidgetModel(id="remaining", kind="shape", text="剩余", binding="device:battery_remaining", value_suffix="h", value_decimals=2)]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("    lambda: |-\n      return (fabsf(", text)
        self.assertNotIn("    lambda: return (fabsf(", text)

    def test_settings_controls_generate_runtime_brightness_and_timeout(self) -> None:
        project = self.make_project()
        project.auto_screen_off = 300
        project.widgets = [
            WidgetModel(id="brightness", kind="slider", action="device.brightness", progress_min=10, progress_max=100),
            WidgetModel(id="timeout", kind="dropdown", action="device.screen_timeout", control_options="长亮\n30秒\n1分钟\n2分钟\n5分钟\n10分钟\n30分钟"),
        ]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("id: screen_timeout_seconds", text)
        self.assertIn("brightness: !lambda return x / 100.0f;", text)
        self.assertIn("static const int timeouts[]", text)
        self.assertIn("delay: !lambda return id(screen_timeout_seconds) * 1000;", text)

    def test_trend_chart_has_horizontal_grid_for_each_y_tick(self) -> None:
        project = self.make_project()
        project.widgets = [WidgetModel(id="trend", kind="trend_chart", binding="sensor.temperature", trend_y_ticks=5, trend_time_labels="exact", trend_axis_color="#123456")]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertEqual(text.count("id: trend_y_grid_"), 5)
        self.assertIn("line_dash_width: 4", text)
        self.assertIn('"%s%02d"', text)
        self.assertIn("line_color: 0xAEB7C2", text)
        self.assertIn("text_color: 0x123456", text)
        self.assertNotIn("现在 (", text)

    def test_buttonmatrix_buttons_have_independent_ha_actions(self) -> None:
        project = self.make_project()
        project.widgets = [WidgetModel(id="modes", kind="buttonmatrix", control_options="普通|观影", matrix_buttons=[
            {"text": "普通", "row": 0, "column": 0, "entity": "input_boolean.normal_mode", "action": "input_boolean.turn_on", "value": "", "disabled": False},
            {"text": "观影", "row": 0, "column": 1, "entity": "switch.movie_mode", "action": "switch.turn_on", "value": "", "disabled": False},
        ])]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("id: modes_cell_0_0", text)
        self.assertIn("action: input_boolean.turn_on", text)
        self.assertIn("entity_id: switch.movie_mode", text)

    def test_trend_chart_modes_generate_distinct_point_sets(self) -> None:
        counts = {}
        for mode in ("line", "step", "bar"):
            project = self.make_project()
            project.widgets = [WidgetModel(id="trend", kind="trend_chart", binding="sensor.temperature", trend_mode=mode)]
            with TemporaryDirectory() as directory:
                text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
            counts[mode] = text.count("              - x:")
        self.assertLess(counts["line"], counts["step"])
        self.assertLess(counts["step"], counts["bar"])

    def test_trend_chart_cpp_float_literals_are_valid_when_range_is_integer(self) -> None:
        project = self.make_project()
        project.widgets = [WidgetModel(id="trend", kind="trend_chart", binding="sensor.temperature", progress_min=20, progress_max=40)]
        with TemporaryDirectory() as directory:
            text = YamlGenerator().generate(project, Path(directory) / "panel.yaml")
        self.assertIn("(v - 20.0f) / 20.0f", text)
        self.assertNotIn("(v - 20f) / 20f", text)



if __name__ == "__main__":
    unittest.main()
