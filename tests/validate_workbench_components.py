"""Validate every bundled icon plus the repaired control/state combinations."""
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.models import PageModel, ProjectModel, WidgetModel
from app.yaml_generator import YamlGenerator


def main():
    build = Path("build")
    source = Path("web/app.js").read_text(encoding="utf-8")
    icons = sorted({int(x, 16) for x in re.findall(r"0x(F[0-9A-Fa-f]{4})\b", source)})
    p = ProjectModel(wifi_ssid="test", battery_monitor=True, battery_chip="ina226", pages=[PageModel(id="main_page"), PageModel(id="details")])
    for i, codepoint in enumerate(icons):
        p.widgets.append(WidgetModel(id=f"catalog_{i}", kind="icon", text="", icon_glyph=chr(codepoint), width=48, height=48, x=(i % 15)*50, y=(i//15)*50))
    p.widgets += [
        WidgetModel(id="empty_state", kind="icon", binding="input_boolean.person", binding_type="state", show_fixed_icon=False,
            state_variants=[dict(value="off", label="", icon_glyph="", depth="inset"), dict(value="on", label="在", icon_glyph="\U000F0004", icon_size=48, depth="raised")]),
        WidgetModel(id="decimal", kind="slider", binding="input_number.level", value_decimals=2, progress_min=-1.25, progress_max=4.75, ha_visual_mode="slider_value", tap_mode="ha"),
        WidgetModel(id="readonly", kind="shape", binding="input_number.level", show_fixed_title=False, value_decimals=2, value_suffix="°C"),
        WidgetModel(id="ring_icon", kind="progress_circle", icon_glyph="\U000F0004", icon_offset_y=-20, binding="sensor.value"),
        WidgetModel(id="switch", kind="switch", binding="input_boolean.enabled", binding_type="state", tap_mode="ha"),
        WidgetModel(id="dropdown", kind="dropdown", binding="input_select.mode", binding_type="state", tap_mode="ha"),
        WidgetModel(id="spinbox", kind="spinbox", binding="input_number.target", tap_mode="ha"),
        WidgetModel(id="navigate", kind="shape", tap_mode="page", target_page="details"),
    ]
    for style in ["horizontal", "vertical", "ring"]:
        p.widgets.append(WidgetModel(id="battery_"+style, kind="battery", binding="device:battery_level", battery_style=style,
                                    battery_display="full" if style == "horizontal" else "percent", width=80 if style == "vertical" else 280, height=160 if style == "vertical" else 80))
    # Reuse a readable staged font; no generation writes to user caches.
    path = build / "workbench-components-check.yaml"
    path.write_text(YamlGenerator()._render(p, "C:/Users/wuxiao/.mijia-panel/fonts/simhei.ttf", {}), encoding="utf-8")
    operation = "compile" if "--compile" in sys.argv else "config"
    log = build / f"workbench-components-{operation}.log"
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run([sys.executable, "-m", "esphome", operation, str(path)], stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        print(log.read_text(encoding="utf-8", errors="replace")[-6000:])
    else:
        print(f"{operation} passed: {len(icons)} bundled glyphs and all repaired control combinations")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
