from __future__ import annotations

from pathlib import Path
import json
import math
import shutil

from .models import ProjectModel, WidgetModel
from .lvgl_compiler import LvglCompiler, dump, font_size, glyphs as project_glyphs, icon_specs


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
        glyphs = project_glyphs(p)
        font_sizes = sorted({font_size(w) for w in p.widgets} | {w.font_size for w in p.widgets} or {28})
        lines = [
            "# 由米家中枢屏幕工作台生成，请勿在工具外直接修改。",
            "esphome:", f"  name: {p.device_name}", f"  friendly_name: {q(p.name)}",
            "  project:", "    name: mijia.display_studio", f"    version: {q(p.firmware_version)}",
            "  platformio_options:", "    board_build.flash_mode: qio",
            "",
            "esp32:", "  board: esp32-s3-devkitc-1", "  variant: esp32s3",
            "  flash_size: 16MB", "  framework:", "    type: esp-idf",
            "",
            "psram:", "  mode: octal", "  speed: 80MHz", "",
            "logger:", "  level: DEBUG", "  hardware_uart: UART0", "",
            "api:", "  id: native_api", "  reboot_timeout: 0s",
        ]
        if p.api_key:
            lines += ["  encryption:", f"    key: {q(p.api_key)}"]
        lines += ["", "ota:", "  - platform: esphome"]
        if p.ota_password:
            lines.append(f"    password: {q(p.ota_password)}")
        lines += [
            "", "wifi:", f"  ssid: {q(p.wifi_ssid)}", f"  password: {q(p.wifi_password)}",
            "  ap:", f"    ssid: {q(p.device_name[:28] + '-AP')}", "", "captive_portal:", "",
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
            # Polling keeps touch input independent of the board's INT signal.
            "touchscreen:", "  - platform: gt911", "    id: touch_panel", "    i2c_id: touch_i2c", "    address: 0x5D", "    reset_pin: GPIO38", "    update_interval: 50ms",
            "    on_touch:", "      then:", '        - lambda: ESP_LOGI("touch", "GT911 touch x=%d y=%d", touch.x, touch.y);', "",
        ]
        # Device utility buttons are generated by the settings template and
        # do not have a Home Assistant entity.  Declare the native ESPHome
        # restart button when such an action is present so the generated
        # LVGL button can invoke it instead of silently doing nothing.
        device_actions = {str(w.action) for w in p.widgets}
        if {"device.restart", "device.safe_mode"} & device_actions:
            lines.append("button:")
            if "device.restart" in device_actions:
                lines += ["  - platform: restart", "    id: restart_button", "    name: \"设备重启\"", "    internal: true"]
            if "device.safe_mode" in device_actions:
                lines += ["  - platform: safe_mode", "    id: safe_mode_button", "    name: \"安全模式\"", "    internal: true"]
            lines.append("")
        if "device.safe_mode" in device_actions:
            lines += ["safe_mode:", ""]
        lines.append("font:")
        for size in font_sizes:
            lines += [f"  - file: {q(font_file)}", f"    id: ui_font_{size}", f"    size: {size}", "    bpp: 4", f"    glyphs: {q(glyphs)}"]
        icon_fonts: dict[int, set[str]] = {}
        for w in p.widgets:
            specs = icon_specs(w)
            for glyph, size in specs:
                icon_fonts.setdefault(size, set()).update(glyph)
            if specs:
                # An empty initial state still needs a font for its label.
                for variant in w.state_variants:
                    size = int(variant.get("icon_size") or w.icon_size)
                    icon_fonts.setdefault(size, set()).update(specs[0][0])
        icon_sizes = sorted(icon_fonts)
        mdi_font = (Path(__file__).resolve().parent.parent / "web" / "materialdesignicons-webfont.ttf").as_posix()
        for size in icon_sizes:
            # The MDI font does not contain every codepoint in the private-use
            # range.  Request only the glyphs actually used by this project;
            # broad ranges make ESPHome reject the configuration.
            icon_glyphs = "".join(sorted(icon_fonts[size]))
            lines += [f"  - file: {q(mdi_font)}", f"    id: mdi_font_{size}", f"    size: {size}", "    bpp: 4", f"    glyphs: {q(icon_glyphs)}"]
        lines.append("")
        if assets:
            lines.append("image:")
            for asset_id, (asset_path, has_alpha) in assets.items():
                lines += ["  - platform: file", f"    file: {q(asset_path)}", f"    id: {asset_id}", "    type: RGB565"]
                if has_alpha:
                    lines.append("    transparency: alpha_channel")
            lines.append("")
        return "\n".join(lines) + dump(LvglCompiler(p, self).sections())

    _effective_font_size = staticmethod(font_size)

    def _label_lines(self, w: WidgetModel, indent: str = "              ") -> list[str]:
        align = {"left": "LEFT_MID", "right": "RIGHT_MID"}.get(w.text_align, "CENTER")
        if w.kind in {"progress_circle", "progress_bar"}:
            text = self._progress_text(w)
        elif w.binding and w.show_fixed_title:
            # Keep a visible placeholder only when the fixed title is enabled;
            # otherwise the HA callback owns the label and it must start empty.
            text = w.text or "--"
        else:
            text = w.text if w.show_fixed_title else ""
        return [f"{indent}- label:", f"{indent}    id: {w.id}_label", f"{indent}    align: {align}",
                f"{indent}    x: {int(w.text_offset_x or 0)}", f"{indent}    y: {int(w.text_offset_y or 0)}",
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
        if w.kind == "trend_chart":
            # Keep the trend card independent from ordinary buttons.  The
            # device receives the numeric entity through the normal sensor
            # subscription; the line object is a stable drawable that can be
            # updated without changing the card layout.
            points = []
            count = max(2, min(int(w.trend_point_count or 120), 120))
            for index in range(count):
                ratio = index / max(1, count - 1)
                px = round(ratio * max(1, w.width - 12)); py = round((1 - (0.5 + 0.35 * math.sin(ratio * math.pi * 4))) * max(1, w.height - 40))
                points += ["                    - x: %d" % px, "                      y: %d" % py]
            result = ["        - obj:", *common, f"            bg_color: {color(w.background_color)}", f"            bg_opa: {max(0, min(100, int(w.background_opacity)))}%", "            widgets:"]
            result += ["              - line:", f"                  id: {w.id}_trend", "                  points:", *points,
                       f"                  line_color: {color(w.progress_color)}", "                  line_width: 3"]
            result += self._label_lines(w)
            return result
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
        if w.kind == "slider":
            result = ["        - slider:", *common, f"            min_value: {w.progress_min}", f"            max_value: {w.progress_max}", f"            value: {w.progress_value}",
                      f"            bg_color: {color(w.background_color)}", f"            indicator: ", f"              bg_color: {color(w.progress_color)}", "            widgets:", *self._label_lines(w)]
            if w.action_entity and w.action:
                result += ["            on_value:", "              then:", "                - homeassistant.action:", f"                    action: {w.action}", "                    data:", f"                      entity_id: {w.action_entity}", "                      value: !lambda return x;"]
            return result
        # LVGL objects with on_click are the original, proven touch path for
        # HA-bound shapes and icons. Keep their component type unchanged.
        result = [f"        - {'button' if button else 'obj'}:", *common]
        # LVGL obj widgets do not receive touch events unless explicitly made
        # clickable.  Keep the visual component type while enabling input for
        # every widget that has an action (including shape/image controls).
        navigates = bool(w.target_page and w.target_page != w.page and not w.action and w.kind in {"icon", "button", "page_button"})
        if (w.action and w.action_entity) or w.kind == "page_button" or w.action in {"device.restart", "device.safe_mode", "device.screen_off"} or navigates:
            result += ["            clickable: true", "            scrollable: false"]
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
            # Apply the selected state variant to the initial LVGL object so
            # the first frame matches the workbench preview before HA sends a
            # state update.
            initial_variant = next((item for item in (w.state_variants or []) if item.get("value") == w.state_preview), None)
            initial_bg = (initial_variant or {}).get("background_color", w.background_color)
            initial_opa = (initial_variant or {}).get("opacity", w.background_opacity)
            result += [f"            bg_color: {color(initial_bg)}", f"            bg_opa: {max(0, min(100, int(initial_opa)))}%",
                       f"            border_color: {color(w.border_color)}", f"            border_width: {w.border_width}", "            widgets:"]
            if initial_variant and initial_variant.get("depth") == "raised":
                result.insert(-1, "            shadow_width: 8")
                result.insert(-1, "            shadow_opa: 60%")
            elif initial_variant and initial_variant.get("depth") == "inset":
                result.insert(-1, "            shadow_width: 4")
                result.insert(-1, "            shadow_opa: 35%")
            asset_id = f"{w.id}_asset" if w.kind == "image" else f"{w.id}_content_asset"
            if (w.kind == "image" and w.asset_path) or w.content_asset_path:
                result += ["              - image:", f"                  id: {w.id}_content", "                  align: CENTER",
                           f"                  width: {w.width}", f"                  height: {w.height}", f"                  src: {asset_id}"]
        result += self._label_lines(w)
        initial_variant = next((item for item in (w.state_variants or []) if item.get("value") == w.state_preview), None)
        variant_glyph = initial_variant.get("icon_glyph") if initial_variant else ""
        if variant_glyph:
            icon_size = int(initial_variant.get("icon_size") or w.icon_size or 32)
            result += ["              - label:", f"                  id: {w.id}_state_icon", "                  align: CENTER",
                       f"                  x: {int(initial_variant.get('icon_offset_x') or 0)}", f"                  y: {int(initial_variant.get('icon_offset_y') or 0)}",
                       f"                  text: {q(variant_glyph)}",
                       f"                  text_color: {color(initial_variant.get('text_color') or w.text_color)}",
                       f"                  text_font: mdi_font_{icon_size}"]
        elif w.icon_glyph and getattr(w, "show_fixed_icon", True) is not False:
            result += ["              - label:", "                  align: CENTER",
                       f"                  x: {int(w.icon_offset_x or 0)}", f"                  y: {int(w.icon_offset_y or 0)}",
                       f"                  text: {q(w.icon_glyph)}",
                       f"                  text_color: {color(w.text_color)}", f"                  text_font: mdi_font_{int(w.icon_size or 32)}"]
        else:
            # State-only widgets still need a visible icon on the device.
            if initial_variant and initial_variant.get("icon_glyph"):
                icon_size = int(initial_variant.get("icon_size") or w.icon_size or 32)
                result += ["              - label:", "                  align: CENTER",
                           f"                  x: {int(initial_variant.get('icon_offset_x') or 0)}",
                           f"                  y: {int(initial_variant.get('icon_offset_y') or 0)}",
                           f"                  text: {q(initial_variant['icon_glyph'])}",
                           f"                  text_color: {color(initial_variant.get('text_color') or w.text_color)}",
                           f"                  text_font: mdi_font_{icon_size}"]
        if button and w.click_effect == "scale":
            result += ["            pressed:", "              transform_width: -4", "              transform_height: -4"]
        elif button and w.click_effect == "darken":
            result += ["            pressed:", "              bg_opa: 70%"]
        if initial_variant and initial_variant.get("depth") in {"raised", "inset"} and w.click_effect not in {"scale", "darken"}:
            result += ["            pressed:", "              shadow_width: 2", "              shadow_opa: 80%"]
        animation = page_animation if page_animation in {"FADE_IN", "FADE_OUT", "MOVE_LEFT", "MOVE_RIGHT", "MOVE_TOP", "MOVE_BOTTOM"} else "FADE_IN"
        if w.kind == "page_button" or navigates:
            result += ["            on_click:", "              then:", "                - lvgl.page.show:", f"                    id: {w.target_page}",
                       f"                    animation: {animation}", "                    time: 300ms"]
        elif w.action == "device.restart":
            result += ["            on_click:", "              then:", "                - button.press: restart_button"]
        elif w.action == "device.safe_mode":
            result += ["            on_click:", "              then:", "                - button.press: safe_mode_button"]
        elif w.action == "device.screen_off":
            result += ["            on_click:", "              then:", "                - light.turn_off: backlight"]
        elif w.action and w.action_entity:
            result += ["            on_click:", "              then:", "                - homeassistant.action:",
                       f"                    action: {w.action}", "                    data:", f"                      entity_id: {w.action_entity}"]
            if w.action == "input_number.set_value":
                result += [f"                      value: {q(str(w.action_value))}"]
        return result

