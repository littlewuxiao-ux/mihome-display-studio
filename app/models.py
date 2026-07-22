from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import re
from typing import Any

ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


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
    action: str = ""
    action_entity: str = ""
    action_value: float = 1.0
    animation: str = "无"

    def clamp(self) -> None:
        self.width = max(20, min(self.width, 800))
        self.height = max(20, min(self.height, 480))
        self.x = max(0, min(self.x, 800 - self.width))
        self.y = max(0, min(self.y, 480 - self.height))
        self.font_size = max(8, min(self.font_size, 96))


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
        for widget in self.widgets:
            widget.clamp()
            if widget.binding and not ENTITY_RE.fullmatch(widget.binding):
                errors.append(f"组件“{widget.text}”的绑定实体ID格式不正确")
            if widget.action_entity and not ENTITY_RE.fullmatch(widget.action_entity):
                errors.append(f"按钮“{widget.text}”的操作实体ID格式不正确")
        return errors

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "ProjectModel":
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        raw["widgets"] = [WidgetModel(**item) for item in raw.get("widgets", [])]
        return cls(**raw)
