from __future__ import annotations

from pathlib import Path
import json
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
        text = self._render(project, font_file)
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

    def _render(self, p: ProjectModel, font_file: str) -> str:
        glyphs = "".join(sorted(set("0123456789.-+ 人在家" + "".join(w.text for w in p.widgets))))
        font_sizes = sorted({w.font_size for w in p.widgets if w.kind != "image"} or {28})
        default_font_id = f"ui_font_{font_sizes[0]}"
        entity_widgets: dict[str, list[WidgetModel]] = {}
        for w in p.widgets:
            if w.kind != "image" and w.binding:
                entity_widgets.setdefault(w.binding, []).append(w)
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
        image_widgets = [widget for widget in p.widgets if widget.kind == "image"]
        if image_widgets:
            lines.append("image:")
            for widget in image_widgets:
                lines += ["  - platform: file", f"    file: {q(Path(widget.asset_path).as_posix())}",
                          f"    id: {widget.id}_asset", "    type: RGB565", f"    resize: {widget.width}x{widget.height}"]
                if Path(widget.asset_path).suffix.lower() in {".png", ".webp"}:
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
                        lines += ["        - lvgl.label.update:", f"            id: {w.id}_label", "            text:",
                                  "              format: \"%.0f\"", f"              args: [id({sid}).state]", "              if_nan: \"--\""]
            lines.append("")
        lines += ["lvgl:", "  displays: [main_display]", "  touchscreens: [touch_panel]", f"  default_font: {default_font_id}",
                  "  buffer_size: 25%", "  page_wrap: true", "  pages:", "    - id: main_page", "      bg_color: 0x080B10", "      pad_all: 0", "      widgets:"]
        if not p.widgets:
            lines += ["        - label:", "            align: CENTER", f"            text: {q('请在工作台添加组件')}", "            text_color: 0xFFFFFF"]
        for w in p.widgets:
            lines.extend(self._widget_lines(w))
        animations = [w for w in p.widgets if w.animation != "无"]
        if animations:
            lines += ["  animations:"]
            for w in animations:
                prop = "x" if w.animation == "滚动" else "opa"
                start, end = (w.x, max(0, 800 - w.width)) if prop == "x" else (0, 255)
                lines += [f"    - id: {w.id}_animation", "      duration: 2s", "      auto_start: true", "      loop: true",
                          "      timing: round_trip", "      widgets:", f"        - id: {w.id}_root", f"          {prop}:", f"            from: {start}", f"            to: {end}"]
        return "\n".join(lines) + "\n"

    def _widget_lines(self, w: WidgetModel) -> list[str]:
        common = [f"            id: {w.id}_root", f"            x: {w.x}", f"            y: {w.y}",
                  f"            width: {w.width}", f"            height: {w.height}", "            radius: 4", "            pad_all: 0"]
        if w.kind == "image":
            return ["        - image:", f"            id: {w.id}_root", f"            x: {w.x}", f"            y: {w.y}",
                    f"            width: {w.width}", f"            height: {w.height}", f"            src: {w.id}_asset"]
        if w.kind == "button":
            result = ["        - button:", *common, f"            bg_color: {color(w.background_color)}", "            widgets:",
                      "              - label:", f"                  id: {w.id}_label", "                  align: CENTER", f"                  text: {q(w.text)}",
                      f"                  text_color: {color(w.text_color)}", f"                  text_font: ui_font_{w.font_size}"]
            if w.action and w.action_entity:
                result += ["            on_click:", "              then:", "                - homeassistant.action:",
                           f"                    action: {w.action}", "                    data:", f"                      entity_id: {w.action_entity}"]
                if w.action == "input_number.set_value":
                    result += [f"                      value: {q(str(w.action_value))}"]
            return result
        text = "--" if w.binding else w.text
        return ["        - obj:", *common, "            bg_opa: TRANSP", "            border_width: 0", "            widgets:",
                "              - label:", f"                  id: {w.id}_label", "                  align: CENTER", f"                  text: {q(text)}",
                f"                  text_color: {color(w.text_color)}", f"                  text_font: ui_font_{w.font_size}"]

