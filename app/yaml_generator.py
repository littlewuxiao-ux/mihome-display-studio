from __future__ import annotations

from pathlib import Path
import json
import math
import shutil

from .models import ProjectModel, WidgetModel


def q(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def color(value: str) -> str:
    return "0x" + value.lstrip("#").upper()


class YamlGenerator:
    """Generate ESPHome 2025.10+ configuration for the VIEWE 7-inch board."""

    def generate(self, project: ProjectModel, output_path: Path) -> str:
        errors = project.validate()
        if errors:
            raise ValueError("\n".join(errors))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        font_file = self._prepare_font(project, output_path.parent)
        assets = self._prepare_images(project)
        text = self._render(project, font_file, assets)
        output_path.write_text(text, encoding="utf-8")
        return text

    def _prepare_font(self, project: ProjectModel, _output_dir: Path) -> str:
        if project.font_path:
            source = Path(project.font_path)
        else:
            candidates = (
                Path("C:/Windows/Fonts/simhei.ttf"),
                Path("C:/Windows/Fonts/simsunb.ttf"),
            )
            source = next((path for path in candidates if path.is_file()), Path())
        if not source.is_file():
            raise ValueError("未找到可用的系统中文字体，请点击“导入字体”选择TTF或OTF文件")
        # FreeType on Windows can fail when the project path contains Chinese characters.
        # Stage fonts in an ASCII-only per-user cache and reference them absolutely.
        font_dir = Path.home() / ".mijia-panel" / "fonts"
        font_dir.mkdir(parents=True, exist_ok=True)
        target = font_dir / source.name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        return target.as_posix()

    def _prepare_images(self, project: ProjectModel) -> dict[str, tuple[str, bool]]:
        from PIL import Image

        image_dir = Path.home() / ".mijia-panel" / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        assets: dict[str, tuple[str, bool]] = {}
        for widget in project.widgets:
            sources = []
            if widget.kind == "image" and widget.asset_path:
                sources.append((f"{widget.id}_asset", widget.asset_path))
            if widget.content_asset_path:
                sources.append((f"{widget.id}_content_asset", widget.content_asset_path))
            for asset_id, source_path in sources:
                with Image.open(source_path) as source:
                    source.load()
                    has_alpha = source.mode in {"RGBA", "LA"} or "transparency" in source.info
                    if widget.image_fit == "cover":
                        scale = max(widget.width / source.width, widget.height / source.height)
                        resized = source.resize((max(1, round(source.width * scale)), max(1, round(source.height * scale))))
                        left = round((resized.width - widget.width) * widget.image_offset_x / 100)
                        top = round((resized.height - widget.height) * widget.image_offset_y / 100)
                        rendered = resized.crop((left, top, left + widget.width, top + widget.height))
                    elif widget.image_fit == "contain":
                        scale = min(widget.width / source.width, widget.height / source.height)
                        resized = source.resize((max(1, round(source.width * scale)), max(1, round(source.height * scale))))
                        rendered = Image.new("RGBA", (widget.width, widget.height), (0, 0, 0, 0))
                        left = round((widget.width - resized.width) * widget.image_offset_x / 100)
                        top = round((widget.height - resized.height) * widget.image_offset_y / 100)
                        rendered.alpha_composite(resized.convert("RGBA"), (left, top))
                        has_alpha = True
                    else:
                        rendered = source.resize((widget.width, widget.height))
                    target = image_dir / f"{asset_id}_{widget.width}x{widget.height}.png"
                    rendered.convert("RGBA" if has_alpha else "RGB").save(target)
                    assets[asset_id] = (target.as_posix(), has_alpha)
        return assets

    def _render(self, p: ProjectModel, font_file: str, assets: dict[str, tuple[str, bool]]) -> str:
        glyphs = "".join(sorted(set("0123456789.-+ 人在家" + "".join(w.text for w in p.widgets))))
        font_sizes = sorted({w.font_size for w in p.widgets} or {28})
        default_font_id = f"ui_font_{font_sizes[0]}"
        entity_widgets: dict[str, list[WidgetModel]] = {}
        text_entity_widgets: dict[str, list[WidgetModel]] = {}
        for w in p.widgets:
            if w.binding:
                target = text_entity_widgets if w.binding_type == "state" and w.kind not in {"progress_circle", "progress_bar"} else entity_widgets
                target.setdefault(w.binding, []).append(w)
        for entity in (p.people_entity_1, p.people_entity_2):
            if entity:
                entity_widgets.setdefault(entity, [])

        lines = [
            "# 由米家中枢屏幕工作台生成，请勿在工具外直接修改。",
            "esphome:", f"  name: {p.device_name}", f"  friendly_name: {q(p.name)}",
            "  platformio_options:", "    board_build.flash_mode: qio",
            "",
            "esp32:", "  board: esp32-s3-devkitc-1", "  variant: esp32s3",
            "  flash_size: 16MB", "  framework:", "    type: esp-idf",
            "",
            "psram:", "  mode: octal", "  speed: 80MHz", "",
            "logger:", "  level: INFO", "  hardware_uart: UART0", "",
            "api:", "  reboot_timeout: 0s",
        ]
        if p.api_key:
            lines += ["  encryption:", f"    key: {q(p.api_key)}"]
        lines += ["", "ota:", "  - platform: esphome"]
        if p.ota_password:
            lines.append(f"    password: {q(p.ota_password)}")
        lines += [
            "", "wifi:", f"  ssid: {q(p.wifi_ssid)}", f"  password: {q(p.wifi_password)}",
            "  ap:", f"    ssid: {q(p.name + ' 配网热点')}", "", "captive_portal:", "",
            "i2c:", "  id: touch_i2c", "  sda: GPIO19", "  scl: GPIO20", "  frequency: 400kHz", "  scan: true", "",
            "output:", "  - platform: ledc", "    id: backlight_pwm", "    pin: GPIO2", "    frequency: 1000Hz", "",
            "light:", "  - platform: monochromatic", "    id: backlight", f"    name: {q('屏幕背光')}",
            "    output: backlight_pwm", "    restore_mode: ALWAYS_ON", "",
            "display:", "  - platform: mipi_rgb", "    model: RPI", "    id: main_display",
            "    update_interval: never", "    auto_clear_enabled: false", "    color_order: RGB",
            "    pclk_frequency: 16MHz", "    pclk_inverted: true", "    dimensions:", "      width: 800", "      height: 480",
            "    de_pin: GPIO40", "    vsync_pin: GPIO41", "    hsync_pin: GPIO39", "    pclk_pin: GPIO42",
            "    hsync_pulse_width: 4", "    hsync_back_porch: 40", "    hsync_front_porch: 40",
            "    vsync_pulse_width: 4", "    vsync_back_porch: 8", "    vsync_front_porch: 8",
            "    data_pins:", "      red: [GPIO45, GPIO48, GPIO47, GPIO21, GPIO14]",
            "      green: [GPIO5, GPIO6, GPIO7, GPIO15, GPIO16, GPIO4]",
            "      blue: [GPIO8, GPIO3, GPIO46, GPIO9, GPIO1]", "",
            "touchscreen:", "  - platform: gt911", "    id: touch_panel", "    interrupt_pin: GPIO18", "    reset_pin: GPIO38", "",
            "font:",
        ]
        for size in font_sizes:
            lines += [f"  - file: {q(font_file)}", f"    id: ui_font_{size}", f"    size: {size}", "    bpp: 4", f"    glyphs: {q(glyphs)}"]
        lines.append("")
        if assets:
            lines.append("image:")
            for asset_id, (asset_path, has_alpha) in assets.items():
                lines += ["  - platform: file", f"    file: {q(asset_path)}", f"    id: {asset_id}", "    type: RGB565"]
                if has_alpha:
                    lines.append("    transparency: alpha_channel")
            lines.append("")
        if entity_widgets:
            lines.append("sensor:")
            for index, (entity, widgets) in enumerate(entity_widgets.items(), 1):
                sid = f"ha_value_{index}"
                lines += ["  - platform: homeassistant", f"    id: {sid}", f"    entity_id: {entity}", "    internal: true"]
                if widgets:
                    lines += ["    on_value:", "      then:"]
                    for w in widgets:
                        if w.kind in {"progress_circle", "progress_bar"}:
                            update = "arc" if w.kind == "progress_circle" else "bar"
                            lines += [f"        - lvgl.{update}.update:", f"            id: {w.id}_root", f"            value: !lambda return id({sid}).state;"]
                            value_expression = f"(id({sid}).state - {w.progress_min}) * 100.0 / {w.progress_max - w.progress_min}" if w.show_value == "percent" else f"id({sid}).state"
                            value_format = f"{w.text.replace('%', '%%')} %.0f%%" if w.show_value == "percent" else f"{w.text.replace('%', '%%')} %.0f"
                            lines += ["        - lvgl.label.update:", f"            id: {w.id}_label", "            text:",
                                      f"              format: {q(value_format)}", f"              args: [{value_expression}]", "              if_nan: \"--\""]
                        else:
                            lines += ["        - lvgl.label.update:", f"            id: {w.id}_label", "            text:",
                                      "              format: \"%.0f\"", f"              args: [id({sid}).state]", "              if_nan: \"--\""]
            lines.append("")
        if text_entity_widgets:
            lines.append("text_sensor:")
            for index, (entity, widgets) in enumerate(text_entity_widgets.items(), 1):
                sid = f"ha_text_{index}"
                lines += ["  - platform: homeassistant", f"    id: {sid}", f"    entity_id: {entity}", "    internal: true", "    on_value:", "      then:"]
                for w in widgets:
                    prefix = w.text.replace("\\", "\\\\").replace('"', '\\"')
                    expression = f"std::string(\"{prefix} \") + x" if prefix else "x"
                    lines += ["        - lvgl.label.update:", f"            id: {w.id}_label", f"            text: !lambda return {expression};"]
            lines.append("")
        lines += ["lvgl:", "  displays: [main_display]", "  touchscreens: [touch_panel]", f"  default_font: {default_font_id}",
                  "  buffer_size: 25%", "  page_wrap: true", "  pages:"]
        for page in p.pages:
            page_widgets = sorted((widget for widget in p.widgets if widget.page == page.id), key=lambda widget: widget.z_index)
            lines += [f"    - id: {page.id}", f"      bg_color: {color(page.background_color)}", "      pad_all: 0", "      widgets:"]
            if not page_widgets:
                lines += ["        - label:", "            align: CENTER", f"            text: {q('空界面')}", "            text_color: 0xFFFFFF"]
            for widget in page_widgets:
                lines.extend(self._widget_lines(widget, p.page_animation))
        animations = [w for w in p.widgets if w.animation != "无"]
        if animations:
            lines += ["  animations:"]
            for w in animations:
                prop = "x" if w.animation == "滚动" else "opa"
                start, end = (w.x, max(0, 800 - w.width)) if prop == "x" else (0, 255)
                lines += [f"    - id: {w.id}_animation", "      duration: 2s", "      auto_start: true", "      loop: true",
                          "      timing: round_trip", "      widgets:", f"        - id: {w.id}_root", f"          {prop}:", f"            from: {start}", f"            to: {end}"]
        return "\n".join(lines) + "\n"

    def _label_lines(self, w: WidgetModel, indent: str = "              ") -> list[str]:
        align = {"left": "LEFT_MID", "right": "RIGHT_MID"}.get(w.text_align, "CENTER")
        text = self._progress_text(w) if w.kind in {"progress_circle", "progress_bar"} else ("--" if w.binding else w.text)
        return [f"{indent}- label:", f"{indent}    id: {w.id}_label", f"{indent}    align: {align}",
                f"{indent}    text: {q(text)}", f"{indent}    text_color: {color(w.text_color)}",
                f"{indent}    text_font: ui_font_{w.font_size}"]

    @staticmethod
    def _progress_text(w: WidgetModel) -> str:
        if w.binding:
            return f"{w.text} --" if w.text else "--"
        if w.show_value == "percent":
            percent = (w.progress_value - w.progress_min) * 100 / (w.progress_max - w.progress_min)
            return f"{w.text} {percent:.0f}%" if w.text else f"{percent:.0f}%"
        return f"{w.text} {w.progress_value:.0f}" if w.text else f"{w.progress_value:.0f}"

    def _widget_lines(self, w: WidgetModel, page_animation: str) -> list[str]:
        common = [f"            id: {w.id}_root", f"            x: {w.x}", f"            y: {w.y}",
                  f"            width: {w.width}", f"            height: {w.height}", f"            radius: {w.radius}", "            pad_all: 0"]
        if w.kind in {"progress_circle", "progress_bar"}:
            component = "arc" if w.kind == "progress_circle" else "bar"
            result = [f"        - {component}:", *common[:-2], f"            min_value: {w.progress_min}",
                      f"            max_value: {w.progress_max}", f"            value: {w.progress_value}"]
            if component == "arc":
                result += ["            start_angle: 135", "            end_angle: 45", "            adjustable: false",
                           f"            arc_color: {color(w.background_color)}", f"            arc_width: {max(3, w.border_width)}",
                           "            indicator:", f"              arc_color: {color(w.progress_color)}", f"              arc_width: {max(3, w.border_width)}",
                           "            knob:", "              bg_opa: TRANSP"]
            else:
                result += [f"            bg_color: {color(w.background_color)}", "            indicator:", f"              bg_color: {color(w.progress_color)}"]
            result += ["            widgets:", *self._label_lines(w)]
            return result

        visual = w.kind in {"image", "shape"}
        button = w.kind in {"button", "page_button"}
        result = [f"        - {'button' if button else 'obj'}:", *common]
        if visual and w.shape_type == "line":
            angle = math.radians(w.line_angle)
            dx, dy = round(math.cos(angle) * w.line_length), round(math.sin(angle) * w.line_length)
            x1, y1 = max(0, -dx), max(0, -dy)
            result += ["            bg_opa: TRANSP", "            border_width: 0", "            widgets:", "              - line:",
                       f"                  id: {w.id}_line", "                  points:", f"                    - {x1}, {y1}",
                       f"                    - {x1 + dx}, {y1 + dy}", f"                  line_width: {max(1, w.border_width)}",
                       f"                  line_color: {color(w.border_color)}"]
        else:
            radius = 200 if visual and w.shape_type in {"ellipse", "circle"} else w.radius
            result[6] = f"            radius: {radius}"
            result += [f"            bg_color: {color(w.background_color)}", f"            border_color: {color(w.border_color)}",
                       f"            border_width: {w.border_width}", "            widgets:"]
            asset_id = f"{w.id}_asset" if w.kind == "image" else f"{w.id}_content_asset"
            if (w.kind == "image" and w.asset_path) or w.content_asset_path:
                result += ["              - image:", f"                  id: {w.id}_content", "                  align: CENTER",
                           f"                  width: {w.width}", f"                  height: {w.height}", f"                  src: {asset_id}"]
        result += self._label_lines(w)
        if button and w.click_effect == "scale":
            result += ["            pressed:", "              transform_width: -4", "              transform_height: -4"]
        elif button and w.click_effect == "darken":
            result += ["            pressed:", "              bg_opa: 70%"]
        animation = page_animation if page_animation in {"FADE_IN", "FADE_OUT", "MOVE_LEFT", "MOVE_RIGHT", "MOVE_TOP", "MOVE_BOTTOM"} else "FADE_IN"
        if w.kind == "page_button":
            result += ["            on_click:", "              then:", "                - lvgl.page.show:", f"                    id: {w.target_page}",
                       f"                    animation: {animation}", "                    time: 300ms"]
        elif w.action and w.action_entity:
            result += ["            on_click:", "              then:", "                - homeassistant.action:",
                       f"                    action: {w.action}", "                    data:", f"                      entity_id: {w.action_entity}"]
            if w.action == "input_number.set_value":
                result += [f"                      value: {q(str(w.action_value))}"]
        return result

