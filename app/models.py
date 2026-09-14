from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import math
import re
from typing import Any

ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+-]{0,31}$")
PROJECT_SCHEMA_VERSION = 30
DEVICE_BINDINGS = {
    "device:wifi_signal",
    "device:wifi_status",
    "device:uptime",
    "device:ip_address",
    "device:ssid",
    "device:firmware_version",
    "device:mac_address",
    "device:chip_model",
    "device:flash_size",
    "device:psram_size",
    "device:api_status",
    "device:current_time",
    "device:battery_level",
    "device:battery_voltage",
    "device:battery_current",
    "device:battery_power",
    "device:battery_remaining",
}


SENSITIVE_FIELDS = {"wifi_password", "api_key", "ota_password"}


def _repair_mojibake(value: Any) -> Any:
    """Recover legacy Chinese strings that were decoded as GBK once."""
    if not isinstance(value, str) or not value:
        return value
    try:
        repaired = value.encode("gbk").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    # Only accept a conversion that removes replacement/control characters.
    if "�" in repaired or any(ord(ch) < 32 and ch not in "\t\n\r" for ch in repaired):
        return value
    return repaired


def _repair_tree(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _repair_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_repair_tree(item) for item in value]
    return _repair_mojibake(value)


def _is_question_placeholder(value: Any) -> bool:
    return isinstance(value, str) and value != "" and set(value) == {"?"}


def _validate_project(project: Any) -> list[str]:
    errors = project.validate_project_structure()
    if not VERSION_RE.fullmatch(project.firmware_version):
        errors.append("固件版本只能包含字母、数字、点、加号、连字符或下划线，长度不超过32个字符")
    if not re.fullmatch(r"[a-z0-9-]+", project.device_name):
        errors.append("设备名称只能包含小写字母、数字和连字符")
    if not project.wifi_ssid:
        errors.append("请填写WiFi名称")
    if project.battery_monitor:
        if project.battery_chip not in {"ina219", "ina226"}:
            errors.append("电池检测芯片只能选择INA219或INA226")
        if not re.fullmatch(r"0x[0-9A-Fa-f]{2}", project.battery_address):
            errors.append("INA I2C地址格式应为0x40")
        if project.battery_full_voltage <= project.battery_low_voltage:
            errors.append("电池满电电压必须高于低电量电压")
        if project.battery_capacity_mwh < 100:
            errors.append("电池组总能量必须至少为100mWh")
    for label, entity in (("在家人数1", project.people_entity_1), ("在家人数2", project.people_entity_2)):
        if entity and not ENTITY_RE.fullmatch(entity):
            errors.append(f"{label}实体ID格式不正确")
    page_ids = {page.id for page in project.pages}
    widget_ids = {widget.id for widget in project.widgets}
    widget_by_id = {widget.id: widget for widget in project.widgets}
    if not project.pages:
        errors.append("项目至少需要一个界面")
    for widget in project.widgets:
        widget.clamp()
        if widget.kind not in {"label", "button", "image", "icon", "shape", "page_button", "progress_circle", "progress_bar", "battery", "slider", "switch", "checkbox", "dropdown", "roller", "spinbox", "spinner", "led", "qrcode", "textarea", "keyboard", "trend_chart", "buttonmatrix", "table", "msgbox", "container", "tabview", "tileview"}:
            errors.append(f"不支持的组件类型：{widget.kind}")
        visible_pages = widget.pages or [widget.page]
        if not visible_pages:
            errors.append(f"组件“{widget.text}”至少需要选择一个界面")
        elif any(page_id not in page_ids for page_id in visible_pages):
            errors.append(f"组件“{widget.text}”所在界面不存在")
        if (widget.kind == "page_button" or widget.tap_mode == "page") and widget.target_page not in page_ids:
            errors.append(f"切换按钮“{widget.text}”的目标界面不存在")
        if widget.tap_mode == "msgbox" and not any(item.id == widget.target_page and item.kind == "msgbox" for item in project.widgets):
            errors.append(f"按钮“{widget.text}”的目标消息框不存在")
        image_paths = [widget.asset_path] if widget.kind == "image" else []
        if widget.content_asset_path:
            image_paths.append(widget.content_asset_path)
        for image_path in image_paths:
            if not image_path or not Path(image_path).is_file():
                errors.append(f"组件“{widget.text}”的图片文件不存在")
        if widget.binding and widget.binding not in DEVICE_BINDINGS and not ENTITY_RE.fullmatch(widget.binding):
            errors.append(f"组件“{widget.text}”的绑定实体ID格式不正确")
        if widget.kind in {"progress_circle", "progress_bar", "battery"} and widget.binding_type == "state":
            errors.append(f"状态栏“{widget.text}”只能绑定数值实体")
        if widget.action_entity and not ENTITY_RE.fullmatch(widget.action_entity):
            errors.append(f"按钮“{widget.text}”的操作实体ID格式不正确")
        if widget.kind == "keyboard" and widget.control_target not in widget_ids:
            errors.append("屏幕键盘必须绑定项目中的文本输入框")
        if widget.parent_id:
            parent = widget_by_id.get(widget.parent_id)
            if not parent or parent.kind not in {"container", "tabview", "tileview"}:
                errors.append(f"组件“{widget.text}”的父容器不存在")
            else:
                seen = {widget.id}
                cursor = parent
                while cursor:
                    if cursor.id in seen:
                        errors.append(f"组件“{widget.text}”存在循环嵌套")
                        break
                    seen.add(cursor.id)
                    cursor = widget_by_id.get(cursor.parent_id) if cursor.parent_id else None
        if widget.binding.startswith("device:battery_") and not project.battery_monitor:
            errors.append("使用电池本机数据源前需要启用INA电池检测")
    return errors


@dataclass
class PageModel:
    id: str
    name: str = "界面"
    background_color: str = "#080B10"
    background_color_2: str = "#080B10"
    background_gradient: str = "none"

@dataclass
class WidgetModel:
    id: str
    kind: str = "label"
    text: str = "文本"
    show_fixed_title: bool = True
    x: int = 20
    y: int = 20
    width: int = 180
    height: int = 60
    font_size: int = 28
    text_color: str = "#FFFFFF"
    background_color: str = "#1976D2"
    background_opacity: int = 100
    opacity: int = 100
    text_opacity: int = 100
    border_opacity: int = 100
    image_opacity: int = 100
    image_tint: str = "#FFFFFF"
    image_tint_opacity: int = 0
    image_grayscale: int = 0
    image_brightness: int = 100
    image_blur: int = 0

    binding: str = ""
    binding_attribute: str = ""
    binding_type: str = "number"
    value_suffix: str = ""
    value_decimals: int = 0
    action: str = ""
    action_entity: str = ""
    action_value: float = 1.0
    action_data: dict[str, Any] = field(default_factory=dict)
    ha_action_mode: str = ""
    ha_state_profile: str = ""
    ha_visual_mode: str = ""
    tap_mode: str = "none"
    animation: str = "无"
    asset_path: str = ""
    page: str = "main_page"
    pages: list[str] = field(default_factory=list)
    z_index: int = 1
    locked: bool = False
    hidden: bool = False
    group_id: str = ""
    image_fit: str = "fill"
    image_offset_x: int = 50
    image_offset_y: int = 50
    shape_type: str = "rectangle"
    border_color: str = "#FFFFFF"
    border_width: int = 2
    radius: int = 4
    target_page: str = ""
    content_asset_path: str = ""
    line_angle: int = 0
    line_length: int = 160
    ellipse_radius_x: int = 80
    ellipse_radius_y: int = 50
    text_align: str = "center"
    text_offset_x: int = 0
    text_offset_y: int = 0
    auto_fit_text: bool = True
    font_weight: str = "normal"
    icon_name: str = ""
    icon_glyph: str = ""
    # Fixed icon visibility is independent from the HA state icon.
    # Keep this in the model so projects saved by the web editor can load.
    show_fixed_icon: bool = True
    state_icon_enabled: bool = False
    state_icon_on_name: str = ""
    state_icon_on_glyph: str = ""
    state_icon_off_name: str = ""
    state_icon_off_glyph: str = ""
    icon_size: int = 32
    icon_offset_x: int = 0
    icon_offset_y: int = 0
    click_effect: str = "scale"
    progress_min: float = 0.0
    progress_max: float = 100.0
    progress_value: float = 50.0
    progress_color: str = "#2F7DF6"
    show_value: str = "percent"
    state_on_value: str = "on"
    state_match: str = "equals"
    state_variants: list[dict[str, Any]] = field(default_factory=list)
    state_style_enabled: bool = True
    state_mapping: bool = False
    state_on_text: str = "开启"
    state_off_text: str = "关闭"
    state_on_color: str = "#45C46A"
    state_off_color: str = "#58616B"
    state_on_bg_opacity: int = 100
    state_off_bg_opacity: int = 72
    state_visual: str = "color"
    state_preview: str = "off"
    visibility_mode: str = "always"
    visible_state: str = "on"
    battery_style: str = "horizontal"
    battery_display: str = "percent"
    battery_low_color: str = "#E5534B"
    battery_warning_color: str = "#F5A623"
    battery_charge_color: str = "#45C46A"
    battery_discharge_color: str = "#2F7DF6"
    control_checked: bool = False
    control_options: str = "选项一\n选项二\n选项三"
    control_selected: int = 0
    control_rows: int = 3
    control_digits: int = 4
    control_decimals: int = 0
    control_text: str = ""
    control_target: str = ""
    matrix_buttons: list[dict[str, Any]] = field(default_factory=list)
    trend_mode: str = "line"
    trend_caption: str = ""
    trend_show_axes: bool = True
    trend_show_x_axis: bool = True
    trend_show_y_axis: bool = True
    trend_time_labels: str = "fuzzy"
    trend_sample_interval: int = 300
    trend_time_range_minutes: int = 120
    trend_point_count: int = 120
    trend_x_ticks: int = 5
    trend_y_ticks: int = 5
    trend_show_title: bool = True
    trend_show_current: bool = True
    trend_header_font_size: int = 14
    trend_axis_color: str = "#AEB7C2"
    parent_id: str = ""
    layout_type: str = "none"
    flex_flow: str = "row_wrap"
    flex_align_main: str = "start"
    flex_align_cross: str = "start"
    flex_align_track: str = "start"
    layout_pad_row: int = 8
    layout_pad_column: int = 8
    container_scrollable: bool = False
    container_scroll_dir: str = "VER"
    container_scrollbar: str = "AUTO"
    container_scroll_momentum: bool = True
    container_scroll_elastic: bool = True
    grid_rows: int = 2
    grid_columns: int = 2
    grid_row: int = 0
    grid_column: int = 0
    grid_row_span: int = 1
    grid_column_span: int = 1
    view_items: str = "标签一\n标签二"
    view_index: int = 0
    view_preview_index: int = 0
    view_preview_row: int = 0
    view_preview_column: int = 0

    def clamp(self) -> None:
        if self.binding == "device:wifi_signal" and self.binding_type == "state":
            self.binding = "device:wifi_status"
        if not self.pages:
            self.pages = [self.page]
        self.pages = list(dict.fromkeys(str(page) for page in self.pages if page))
        if self.pages:
            self.page = self.pages[0]
        self.width = max(20, min(self.width, 800))
        self.height = max(20, min(self.height, 480))
        self.x = max(0, min(self.x, 800 - self.width))
        self.y = max(0, min(self.y, 480 - self.height))
        self.font_size = max(8, min(self.font_size, 96))
        self.z_index = max(0, min(int(self.z_index), 999))
        self.image_offset_x = max(0, min(int(self.image_offset_x), 100))
        self.image_offset_y = max(0, min(int(self.image_offset_y), 100))
        self.border_width = max(0, min(int(self.border_width), 24))
        self.background_opacity = max(0, min(int(self.background_opacity), 100))
        self.opacity = max(0, min(int(self.opacity), 100))
        self.text_opacity = max(0, min(int(self.text_opacity), 100))
        self.border_opacity = max(0, min(int(self.border_opacity), 100))
        self.image_opacity = max(0, min(int(self.image_opacity), 100))
        self.image_tint_opacity = max(0, min(int(self.image_tint_opacity), 100))
        self.image_grayscale = max(0, min(int(self.image_grayscale), 100))
        self.image_brightness = max(0, min(int(self.image_brightness), 200))
        self.image_blur = max(0, min(int(self.image_blur), 20))
        self.state_on_bg_opacity = max(0, min(int(self.state_on_bg_opacity), 100))
        self.state_off_bg_opacity = max(0, min(int(self.state_off_bg_opacity), 100))
        if self.visibility_mode not in {"always", "state_equals", "state_not_equals"}:
            self.visibility_mode = "always"
        if self.state_visual not in {"color", "depth", "both"}:
            self.state_visual = "color"
        if self.state_preview not in {"on", "off", *(str(v.get("value", "")) for v in self.state_variants)}:
            self.state_preview = "off"
        if self.state_icon_enabled and not self.state_icon_on_glyph:
            self.state_icon_enabled = False
        if self.battery_style not in {"horizontal", "vertical", "ring"}:
            self.battery_style = "horizontal"
        if self.battery_display not in {"icon", "percent", "full"}:
            self.battery_display = "percent"
        if self.kind == "battery" and self.battery_display == "full":
            self.width = max(self.width, 280)
            self.height = max(self.height, 60)
            self.x = min(self.x, 800 - self.width)
            self.y = min(self.y, 480 - self.height)
        options = [item.strip() for item in re.split(r"[\n,]", self.control_options) if item.strip()]
        self.control_options = "\n".join(options[:32]) or "选项一"
        self.control_selected = max(0, min(int(self.control_selected), len(self.control_options.splitlines()) - 1))
        if self.trend_mode not in {"line", "step", "bar"}:
            self.trend_mode = "line"
        self.trend_sample_interval = max(0, min(int(self.trend_sample_interval), 86400))
        self.trend_time_range_minutes = max(1, min(int(self.trend_time_range_minutes), 10080))
        self.trend_point_count = max(2, min(int(self.trend_point_count), 240))
        self.trend_x_ticks = max(2, min(int(self.trend_x_ticks), 10))
        self.trend_y_ticks = max(2, min(int(self.trend_y_ticks), 10))
        if self.trend_time_labels not in {"fuzzy", "exact"}:
            self.trend_time_labels = "fuzzy"
        self.trend_header_font_size = max(8, min(int(self.trend_header_font_size), 48))
        if self.kind == "buttonmatrix":
            old = self.matrix_buttons if isinstance(self.matrix_buttons, list) else []
            normalized = []
            for row, row_text in enumerate(self.control_options.replace("\r", "").splitlines()):
                for column, label in enumerate(row_text.split("|")):
                    previous = next((item for item in old if item.get("row") == row and item.get("column") == column), {})
                    normalized.append({"text": label.strip(), "row": row, "column": column,
                                      "entity": str(previous.get("entity", "")), "action": str(previous.get("action", "")),
                                      "value": str(previous.get("value", "")), "disabled": bool(previous.get("disabled", False))})
            self.matrix_buttons = normalized
        self.control_rows = max(1, min(int(self.control_rows), 8))
        self.control_digits = max(1, min(int(self.control_digits), 10))
        self.control_decimals = max(0, min(int(self.control_decimals), self.control_digits - 1))
        if self.layout_type not in {"none", "flex", "grid"}:
            self.layout_type = "none"
        if self.flex_flow not in {"row", "column", "row_wrap", "column_wrap", "row_reverse", "column_reverse"}:
            self.flex_flow = "row_wrap"
        self.layout_pad_row = max(0, min(int(self.layout_pad_row), 100))
        self.layout_pad_column = max(0, min(int(self.layout_pad_column), 100))
        if self.container_scroll_dir not in {"VER", "HOR", "ALL"}:
            self.container_scroll_dir = "VER"
        if self.container_scrollbar not in {"OFF", "ON", "ACTIVE", "AUTO"}:
            self.container_scrollbar = "AUTO"
        self.grid_rows = max(1, min(int(self.grid_rows), 12))
        self.grid_columns = max(1, min(int(self.grid_columns), 12))
        self.grid_row = max(0, min(int(self.grid_row), 11))
        self.grid_column = max(0, min(int(self.grid_column), 11))
        self.grid_row_span = max(1, min(int(self.grid_row_span), 12))
        self.grid_column_span = max(1, min(int(self.grid_column_span), 12))
        self.view_items = "\n".join(item.strip() for item in self.view_items.splitlines() if item.strip()) or "标签一"
        self.view_index = max(0, min(int(self.view_index), 11))
        self.view_preview_index = max(0, min(int(self.view_preview_index), 11))
        self.view_preview_row = max(0, min(int(self.view_preview_row), self.grid_rows - 1))
        self.view_preview_column = max(0, min(int(self.view_preview_column), self.grid_columns - 1))
        self.value_decimals = max(0, min(int(self.value_decimals), 3))
        if self.tap_mode not in {"none", "ha", "page", "msgbox"}:
            self.tap_mode = "none"
        self.text_offset_x = max(-800, min(int(self.text_offset_x), 800))
        self.text_offset_y = max(-480, min(int(self.text_offset_y), 480))
        self.icon_size = max(8, min(int(self.icon_size), 192))
        self.icon_offset_x = max(-800, min(int(self.icon_offset_x), 800))
        self.icon_offset_y = max(-480, min(int(self.icon_offset_y), 480))

        self.radius = max(0, min(int(self.radius), 200))
        self.line_angle = max(-180, min(int(self.line_angle), 180))
        self.line_length = max(10, min(int(self.line_length), 900))
        self.ellipse_radius_x = max(10, min(int(self.ellipse_radius_x), 400))
        self.ellipse_radius_y = max(10, min(int(self.ellipse_radius_y), 240))
        if self.kind == "shape" and self.shape_type in {"ellipse", "circle"}:
            if self.shape_type == "circle":
                self.ellipse_radius_y = self.ellipse_radius_x
            self.width = min(800, self.ellipse_radius_x * 2)
            self.height = min(480, self.ellipse_radius_y * 2)
        elif self.kind == "shape" and self.shape_type == "line":
            radians = math.radians(self.line_angle)
            self.width = max(20, min(800, round(abs(math.cos(radians) * self.line_length) + self.border_width)))
            self.height = max(20, min(480, round(abs(math.sin(radians) * self.line_length) + self.border_width)))
        self.x = max(0, min(self.x, 800 - self.width))
        self.y = max(0, min(self.y, 480 - self.height))
        if self.progress_max <= self.progress_min:
            self.progress_max = self.progress_min + 1
        self.progress_value = max(self.progress_min, min(float(self.progress_value), self.progress_max))


@dataclass
class ProjectModel:
    schema_version: int = PROJECT_SCHEMA_VERSION
    name: str = "米家中枢触控屏"
    device_name: str = "mijia-hub-panel"
    firmware_version: str = "1.0.0"

    wifi_ssid: str = ""
    wifi_password: str = ""
    ha_address: str = ""
    api_key: str = ""
    ota_password: str = ""
    people_entity_1: str = "sensor.people_home_1"
    people_entity_2: str = "sensor.people_home_2"
    font_path: str = ""
    page_animation: str = "NONE"
    default_page: str = "main_page"
    battery_monitor: bool = False
    battery_chip: str = "ina219"
    battery_address: str = "0x40"
    battery_full_voltage: float = 4.20
    battery_low_voltage: float = 3.30
    battery_voltage_offset: float = 0.0
    battery_sample_interval: int = 10
    battery_shunt_resistance: float = 0.1
    battery_max_current: float = 3.2
    battery_capacity_mah: int = 3000
    battery_capacity_mwh: int = 11100
    battery_initial_percent: int = 100
    battery_current_inverted: bool = False
    bluetooth_proxy: bool = False
    auto_screen_off: int = 0
    theme_name: str = "graphite"
    theme_accent: str = "#2F7DF6"
    theme_surface: str = "#182129"
    theme_text: str = "#FFFFFF"
    theme_radius: int = 8
    pages: list[PageModel] = field(
        default_factory=lambda: [PageModel(id="main_page", name="主界面")]
    )
    widgets: list[WidgetModel] = field(default_factory=list)
    validate = _validate_project

    def __post_init__(self) -> None:
        page_ids = {page.id for page in self.pages if isinstance(page, PageModel)}
        if page_ids and self.default_page not in page_ids:
            self.default_page = self.pages[0].id
        self.battery_capacity_mwh = max(100, int(self.battery_capacity_mwh))
        self.battery_initial_percent = max(0, min(100, int(self.battery_initial_percent)))
        self.auto_screen_off = max(0, min(86400, int(self.auto_screen_off)))


    def to_dict(self, *, include_secrets: bool = True) -> dict[str, Any]:
        data = asdict(self)
        data["schema_version"] = PROJECT_SCHEMA_VERSION
        if not include_secrets:
            for field_name in SENSITIVE_FIELDS:
                data[field_name] = ""
        return data

    def validate_project_structure(self) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.pages, list) or not isinstance(self.widgets, list):
            return ["项目界面或组件数据格式不正确"]
        if any(not isinstance(page, PageModel) or not page.id for page in self.pages):
            errors.append("项目包含无效界面数据")
        if any(
            page.background_gradient not in {"none", "horizontal", "vertical"}
            for page in self.pages
            if isinstance(page, PageModel)
        ):
            errors.append("项目包含无效背景渐变方向")

        if any(not isinstance(widget, WidgetModel) or not widget.id for widget in self.widgets):
            errors.append("项目包含无效组件数据")
        page_ids = [page.id for page in self.pages]
        if len(page_ids) != len(set(page_ids)):
            errors.append("项目包含重复的界面ID")
        if page_ids and self.default_page not in page_ids:
            errors.append("默认启动界面不存在")
        widget_ids = [widget.id for widget in self.widgets]
        if len(widget_ids) != len(set(widget_ids)):
            errors.append("项目包含重复的组件ID")
        return errors

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ProjectModel":
        if not isinstance(raw, dict):
            raise ValueError("项目文件必须是JSON对象")
        # Project files are UTF-8; preserve the exact text entered in the
        # workbench. Legacy repair must never reinterpret valid Chinese.
        data = dict(raw)
        version = data.pop("schema_version", 0)
        if not isinstance(version, int) or version < 0 or version > PROJECT_SCHEMA_VERSION:
            raise ValueError(f"不支持的项目格式版本：{version}")
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        if allowed:
            data = {key: value for key, value in data.items() if key in allowed}
        if _is_question_placeholder(data.get("name")):
            data["name"] = "米家中枢触控屏"
        if data.get("page_animation") in {None, "", "FADE_ON"}:
            data["page_animation"] = "NONE"
        if version < 27 and "battery_capacity_mwh" not in data:
            data["battery_capacity_mwh"] = round(max(100, int(data.get("battery_capacity_mah", 3000))) * 3.7)
        pages_data = data.get("pages", [{"id": "main_page", "name": "主界面"}])
        for page in pages_data:
            if isinstance(page, dict) and _is_question_placeholder(page.get("name")):
                page["name"] = "主界面"
        widgets_data = data.get("widgets", [])
        if (
            len(widgets_data) == 1
            and isinstance(widgets_data[0], dict)
            and _is_question_placeholder(widgets_data[0].get("text"))
        ):
            widgets_data[0]["text"] = "在家人数1"
        data["pages"] = [PageModel(**item) for item in pages_data]
        if not data.get("default_page") or data["default_page"] not in {
            page.id for page in data["pages"]
        }:
            data["default_page"] = data["pages"][0].id if data["pages"] else "main_page"
        migrated_widgets = []
        valid_parent_ids = {
            item.get("id")
            for item in widgets_data
            if isinstance(item, dict) and item.get("kind") in {"container", "tabview", "tileview"}
        }
        for item in widgets_data:
            if isinstance(item, dict):
                item = dict(item)
                if version < 30:
                    # Earlier icon insertion/HA clearing could hide the only
                    # glyph while the canvas still rendered it visibly.
                    if (item.get("kind") == "icon" and item.get("icon_glyph")
                            and not item.get("binding") and not item.get("state_variants")
                            and not item.get("state_icon_enabled") and not item.get("show_fixed_title", True)):
                        item["show_fixed_icon"] = True
                    if item.get("kind") == "page_button":
                        item["tap_mode"] = "page"
                    elif item.get("action") and not item.get("tap_mode"):
                        item["tap_mode"] = "ha"
                if version < 24 and item.get("kind") == "trend_chart":
                    item["font_size"] = item.get("trend_header_font_size", 14)
                item.setdefault("pages", [item.get("page", "main_page")])
                if item.get("parent_id") and item["parent_id"] not in valid_parent_ids:
                    item["parent_id"] = ""
                if item.get("binding") == "device:wifi_signal" and item.get("binding_type") == "state":
                    item["binding"] = "device:wifi_status"
            migrated_widgets.append(WidgetModel(**item))
        data["widgets"] = migrated_widgets

        project = cls(**data)
        structure_errors = project.validate_project_structure()
        if structure_errors:
            raise ValueError("；".join(structure_errors))
        return project

    @classmethod
    def load(cls, path: Path) -> "ProjectModel":
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(raw)
