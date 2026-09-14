from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import PageModel, ProjectModel, WidgetModel
from app.yaml_generator import YamlGenerator


def base_project(name: str) -> ProjectModel:
    return ProjectModel(device_name=f"matrix-{name}", wifi_ssid="test-network")


def variants(directory: Path) -> dict[str, ProjectModel]:
    image_path = directory / "sample.png"
    Image.new("RGBA", (64, 48), (47, 125, 246, 180)).save(image_path)

    normal = base_project("normal")
    normal.widgets = [WidgetModel(id="title", kind="shape", text="普通组件")]

    line = base_project("line")
    line.widgets = [WidgetModel(id="line", kind="shape", shape_type="line", text="", binding="")]

    image = base_project("image")
    image.widgets = [WidgetModel(id="image", kind="image", text="图片", asset_path=str(image_path))]

    pages = base_project("pages")
    pages.pages = [
        PageModel(id="main_page", name="主页", background_color="#080B10", background_color_2="#1976D2", background_gradient="horizontal"),
        PageModel(id="second", name="第二页", background_color="#111111", background_color_2="#333333", background_gradient="vertical"),
    ]
    pages.widgets = [
        WidgetModel(id="next", kind="page_button", text="下一页", target_page="second"),
        WidgetModel(id="shared", kind="shape", text="共享", pages=["main_page", "second"]),
    ]

    home_assistant = base_project("ha")
    home_assistant.widgets = [WidgetModel(id="temperature", kind="progress_bar", text="温度", binding="sensor.living_room_temperature", icon_name="温度计", icon_glyph="󰔏", icon_size=32, icon_offset_x=-90)]
    device_info = base_project("device")
    device_info.widgets = [
        WidgetModel(id="signal", kind="shape", text="信号", binding="device:wifi_signal", opacity=70),
        WidgetModel(id="ip", kind="shape", text="IP", binding="device:ip_address", binding_type="state"),
    ]
    battery = base_project("battery")
    battery.battery_monitor = True
    battery.battery_chip = "ina226"
    battery.battery_capacity_mwh = 18500
    battery.widgets = [WidgetModel(id="battery", kind="battery", text="电池", binding="device:battery_level")]
    settings = base_project("settings")
    settings.auto_screen_off = 30
    settings.bluetooth_proxy = True
    settings.widgets = [
        WidgetModel(id="clock", kind="shape", text="时间", binding="device:current_time", binding_type="state"),
        WidgetModel(id="api", kind="shape", text="API", binding="device:api_status", binding_type="state"),
        WidgetModel(id="wifi", kind="shape", text="WiFi", binding="device:wifi_status", binding_type="state"),
        WidgetModel(id="restart", kind="button", text="重启", action="device.restart"),
        WidgetModel(id="brightness", kind="slider", text="亮度", action="device.brightness", progress_min=10, progress_max=100),
        WidgetModel(id="timeout", kind="dropdown", text="息屏", action="device.screen_timeout", control_options="长亮\n30秒\n1分钟\n2分钟\n5分钟\n10分钟\n30分钟"),
        WidgetModel(id="mapped", kind="button", text="灯光", binding="light.test", binding_type="state", state_mapping=True, state_visual="both", action="light.toggle", action_entity="light.test", visibility_mode="state_not_equals", visible_state="unavailable"),
    ]
    icon = base_project("icon")
    icon.widgets = [
        WidgetModel(id="wifi", kind="icon", text="WiFi", icon_name="WiFi", icon_glyph="󰖩", font_size=40),
        WidgetModel(id="plus", kind="shape", text="", icon_name="加", icon_glyph="󰐕", icon_size=64, auto_fit_text=False),
    ]
    trend = base_project("trend")
    trend.widgets = [WidgetModel(id="temperature_trend", kind="trend_chart", text="温度", binding="sensor.temperature", trend_y_ticks=5, trend_x_ticks=5)]
    controls = base_project("controls")
    controls.widgets = [
        WidgetModel(id="guests", kind="slider", binding="input_number.ke_ren_shu", progress_min=0, progress_max=10),
        WidgetModel(id="presence", kind="switch", binding="input_boolean.person_home", binding_type="state"),
        WidgetModel(id="mode", kind="dropdown", binding="input_select.mode", binding_type="state", control_options="自动\n制冷"),
        WidgetModel(id="setpoint", kind="spinbox", binding="input_number.setpoint"),
    ]
    return {"normal": normal, "line": line, "image": image, "pages": pages, "home-assistant": home_assistant, "device-info": device_info, "battery": battery, "settings": settings, "icon": icon, "trend": trend, "controls": controls}


def main() -> int:
    with TemporaryDirectory(dir=Path.cwd()) as temporary:
        root = Path(temporary)
        for name, project in variants(root).items():
            yaml_path = root / f"{name}.yaml"
            YamlGenerator().generate(project, yaml_path)
            print(f"Validating {name}: {yaml_path}")
            result = subprocess.run([sys.executable, "-m", "esphome", "config", str(yaml_path)], capture_output=True, text=True)
            if result.returncode:
                print(result.stdout[-4000:])
                print(result.stderr[-4000:])
                return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
