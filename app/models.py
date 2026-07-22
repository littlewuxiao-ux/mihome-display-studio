from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import math
import re
from typing import Any

ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


@dataclass
class PageModel:
    id: str
    name: str = "界面"
    background_color: str = "#080B10"


@dataclass
class WidgetModel:
    id: str
    kind: str = "label"
    text: str = "文本"
    x: int = 20
    y: int = 20
    width: int = 180
    height: int = 60
    font_size: int = 28
    text_color: str = "#FFFFFF"
    background_color: str = "#1976D2"
    binding: str = ""
    binding_type: str = "number"
    action: str = ""
    action_entity: str = ""
    action_value: float = 1.0
    animation: str = "无"
    asset_path: str = ""
    page: str = "main_page"
    z_index: int = 1
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
    font_weight: str = "normal"
    click_effect: str = "scale"
    progress_min: float = 0.0
    progress_max: float = 100.0
    progress_value: float = 50.0
    progress_color: str = "#2F7DF6"
    show_value: str = "percent"

    def clamp(self) -> None:
        self.width = max(20, min(self.width, 800))
        self.height = max(20, min(self.height, 480))
        self.x = max(0, min(self.x, 800 - self.width))
        self.y = max(0, min(self.y, 480 - self.height))
        self.font_size = max(8, min(self.font_size, 96))
        self.z_index = max(0, min(int(self.z_index), 999))
        self.image_offset_x = max(0, min(int(self.image_offset_x), 100))
        self.image_offset_y = max(0, min(int(self.image_offset_y), 100))
        self.border_width = max(0, min(int(self.border_width), 24))
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
    name: str = "米家中枢触控屏"
    device_name: str = "mijia-hub-panel"
    wifi_ssid: str = ""
    wifi_password: str = ""
    ha_address: str = ""
    api_key: str = ""
    ota_password: str = ""
    people_entity_1: str = "sensor.people_home_1"
    people_entity_2: str = "sensor.people_home_2"
    font_path: str = ""
    page_animation: str = "FADE_ON"
    pages: list[PageModel] = field(default_factory=lambda: [PageModel(id="main_page", name="主界面")])
    widgets: list[WidgetModel] = field(default_factory=list)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not re.fullmatch(r"[a-z0-9-]+", self.device_name):
            errors.append("设备名称只能包含小写字母、数字和连字符")
        if not self.wifi_ssid:
            errors.append("请填写WiFi名称")
        for label, entity in (("在家人数1", self.people_entity_1), ("在家人数2", self.people_entity_2)):
            if entity and not ENTITY_RE.fullmatch(entity):
                errors.append(f"{label}实体ID格式不正确")
        page_ids = {page.id for page in self.pages}
        if not self.pages:
            errors.append("项目至少需要一个界面")
        for widget in self.widgets:
            widget.clamp()
            if widget.kind not in {"label", "button", "image", "shape", "page_button", "progress_circle", "progress_bar"}:
                errors.append(f"不支持的组件类型：{widget.kind}")
            if widget.page not in page_ids:
                errors.append(f"组件“{widget.text}”所在界面不存在")
            if widget.kind == "page_button" and widget.target_page not in page_ids:
                errors.append(f"切换按钮“{widget.text}”的目标界面不存在")
            image_paths = [widget.asset_path] if widget.kind == "image" else []
            if widget.content_asset_path:
                image_paths.append(widget.content_asset_path)
            for image_path in image_paths:
                if not image_path or not Path(image_path).is_file():
                    errors.append(f"组件“{widget.text}”的图片文件不存在")
            if widget.binding and not ENTITY_RE.fullmatch(widget.binding):
                errors.append(f"组件“{widget.text}”的绑定实体ID格式不正确")
            if widget.kind in {"progress_circle", "progress_bar"} and widget.binding_type == "state":
                errors.append(f"状态栏“{widget.text}”只能绑定数值实体")
            if widget.action_entity and not ENTITY_RE.fullmatch(widget.action_entity):
                errors.append(f"按钮“{widget.text}”的操作实体ID格式不正确")
        return errors

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ProjectModel":
        data = dict(raw)
        data["pages"] = [PageModel(**item) for item in data.get("pages", [{"id": "main_page", "name": "主界面"}])]
        data["widgets"] = [WidgetModel(**item) for item in data.get("widgets", [])]
        return cls(**data)

    @classmethod
    def load(cls, path: Path) -> "ProjectModel":
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(raw)
