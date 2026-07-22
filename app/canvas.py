from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPen
from PyQt6.QtWidgets import QFrame, QGraphicsItem, QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem, QGraphicsView

from .models import ProjectModel, WidgetModel


class CanvasItem(QGraphicsRectItem):
    def __init__(self, model: WidgetModel) -> None:
        super().__init__(0, 0, model.width, model.height)
        self.model = model
        self.setPos(model.x, model.y)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.label = QGraphicsTextItem(model.text, self)
        self.refresh()

    def refresh(self) -> None:
        m = self.model
        self.setRect(0, 0, m.width, m.height)
        bg = QColor(m.background_color if m.kind == "button" else "#151A22")
        self.setBrush(QBrush(bg))
        self.setPen(QPen(QColor("#38BDF8") if self.isSelected() else QColor("#334155"), 2))
        self.label.setPlainText(m.text)
        self.label.setDefaultTextColor(QColor(m.text_color))
        self.label.setFont(QFont("Microsoft YaHei UI", m.font_size))
        bounds = self.label.boundingRect()
        self.label.setPos(max(4, (m.width - bounds.width()) / 2), max(0, (m.height - bounds.height()) / 2))

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            point: QPointF = value
            x = max(0, min(point.x(), 800 - self.rect().width()))
            y = max(0, min(point.y(), 480 - self.rect().height()))
            return QPointF(round(x), round(y))
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.model.x, self.model.y = round(self.x()), round(self.y())
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.refresh()
        return super().itemChange(change, value)


class DesignCanvas(QGraphicsView):
    selected = pyqtSignal(object)
    model_changed = pyqtSignal()

    def __init__(self, project: ProjectModel) -> None:
        super().__init__()
        self.project = project
        self.scene = QGraphicsScene(0, 0, 800, 480, self)
        self.setScene(self.scene)
        self.setRenderHints(self.renderHints())
        self.setBackgroundBrush(QColor("#080B10"))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumSize(820, 500)
        self.scene.selectionChanged.connect(self._selection_changed)
        self.rebuild()

    def rebuild(self) -> None:
        self.scene.clear()
        for model in self.project.widgets:
            self.scene.addItem(CanvasItem(model))

    def add_widget(self, kind: str) -> WidgetModel:
        index = len(self.project.widgets) + 1
        model = WidgetModel(
            id=f"widget_{index}", kind=kind,
            text="触摸按钮" if kind == "button" else "文本显示",
            x=30 + (index * 18) % 300, y=30 + (index * 18) % 180,
            background_color="#1976D2" if kind == "button" else "#151A22",
        )
        self.project.widgets.append(model)
        item = CanvasItem(model)
        self.scene.addItem(item)
        self.scene.clearSelection()
        item.setSelected(True)
        self.model_changed.emit()
        return model

    def remove_selected(self) -> None:
        items = [item for item in self.scene.selectedItems() if isinstance(item, CanvasItem)]
        for item in items:
            self.project.widgets.remove(item.model)
            self.scene.removeItem(item)
        if items:
            self.model_changed.emit()

    def refresh_model(self, model: WidgetModel) -> None:
        model.clamp()
        for item in self.scene.items():
            if isinstance(item, CanvasItem) and item.model is model:
                item.setPos(model.x, model.y)
                item.refresh()
                break
        self.model_changed.emit()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fitInView(QRectF(0, 0, 800, 480), Qt.AspectRatioMode.KeepAspectRatio)

    def _selection_changed(self) -> None:
        items = self.scene.selectedItems()
        self.selected.emit(items[0].model if items and isinstance(items[0], CanvasItem) else None)
