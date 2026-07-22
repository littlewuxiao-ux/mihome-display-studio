from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QColorDialog, QComboBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QPlainTextEdit, QProgressBar,
    QSpinBox, QSplitter, QTabWidget, QToolBar, QVBoxLayout, QWidget,
)

from .canvas import DesignCanvas
from .models import ProjectModel, WidgetModel
from .processes import EsphomeProcess
from .serial_tools import scan_serial_ports
from .yaml_generator import YamlGenerator


class MainWindow(QMainWindow):
    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        self.project = ProjectModel(widgets=[WidgetModel(id="people_1", text="在家人数1", x=80, y=80, width=260, height=90, binding="sensor.people_home_1")])
        self.yaml_path = root / "build" / f"{self.project.device_name}.yaml"
        self.generator = YamlGenerator()
        self.runner = EsphomeProcess(self)
        self.current_widget: WidgetModel | None = None
        self.setWindowTitle("米家中枢屏幕工作台")
        self.setMinimumSize(1180, 720)
        self.resize(1420, 860)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #101318; color: #E5E7EB; font-family: 'Microsoft YaHei UI'; font-size: 13px; }
            QLineEdit, QSpinBox, QComboBox, QPlainTextEdit { background: #181D25; border: 1px solid #343B47; padding: 5px; }
            QPushButton { background: #232A35; border: 1px solid #3B4554; padding: 6px 10px; }
            QPushButton:hover { background: #2E3745; }
            QGroupBox { border: 1px solid #343B47; margin-top: 10px; padding-top: 8px; }
            QTabBar::tab:selected { background: #2563EB; }
        """)
        self._build_ui()
        self._connect()
        self._load_project_to_form()
        self._refresh_ports()

    def _build_ui(self) -> None:
        toolbar = QToolBar("工具")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.add_action = QPushButton("添加文本")
        self.add_button = QPushButton("添加按钮")
        self.delete_button = QPushButton("删除选中")
        self.generate_button = QPushButton("生成配置")
        self.validate_button = QPushButton("校验配置")
        self.compile_button = QPushButton("静默编译")
        self.flash_button = QPushButton("一键烧录")
        for button in (self.add_action, self.add_button, self.delete_button, self.generate_button, self.validate_button, self.compile_button, self.flash_button):
            toolbar.addWidget(button)

        self.canvas = DesignCanvas(self.project)
        self.form = self._make_form()
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("编译、校验和烧录日志将在这里显示")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.addWidget(self.progress)
        bottom_layout.addWidget(self.log)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.form)
        right_layout.addWidget(bottom, 1)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.canvas)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        self.setCentralWidget(splitter)
        self.statusBar().showMessage("就绪")

    def _make_form(self) -> QWidget:
        tabs = QTabWidget()
        general = QWidget(); layout = QFormLayout(general)
        self.name_edit = QLineEdit(); self.device_edit = QLineEdit()
        self.ssid_edit = QLineEdit(); self.password_edit = QLineEdit(); self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ha_edit = QLineEdit(); self.api_edit = QLineEdit(); self.api_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ota_edit = QLineEdit(); self.ota_edit.setEchoMode(QLineEdit.EchoMode.Password)
        for label, widget in (("项目名称", self.name_edit), ("设备名称", self.device_edit), ("WiFi名称", self.ssid_edit), ("WiFi密码", self.password_edit), ("HA地址（仅记录）", self.ha_edit), ("API加密密钥", self.api_edit), ("OTA密码", self.ota_edit)):
            layout.addRow(label, widget)
        entity = QWidget(); entity_layout = QFormLayout(entity)
        self.people1_edit = QLineEdit(); self.people2_edit = QLineEdit()
        entity_layout.addRow("在家人数1实体", self.people1_edit); entity_layout.addRow("在家人数2实体", self.people2_edit)
        font_row = QHBoxLayout(); self.font_label = QLabel("未选择，默认Google Noto Sans SC")
        font_button = QPushButton("导入字体")
        font_button.clicked.connect(self._choose_font)
        font_row.addWidget(self.font_label, 1); font_row.addWidget(font_button)
        entity_layout.addRow("中文字体", font_row)
        tabs.addTab(general, "网络与安全"); tabs.addTab(entity, "米家变量")

        widget_box = QGroupBox("选中组件")
        wlayout = QFormLayout(widget_box)
        self.text_edit = QLineEdit(); self.binding_edit = QLineEdit(); self.action_edit = QLineEdit()
        self.x_spin = QSpinBox(); self.x_spin.setRange(0, 800); self.y_spin = QSpinBox(); self.y_spin.setRange(0, 480)
        self.w_spin = QSpinBox(); self.w_spin.setRange(20, 800); self.h_spin = QSpinBox(); self.h_spin.setRange(20, 480)
        self.size_spin = QSpinBox(); self.size_spin.setRange(8, 96)
        self.text_color_button = QPushButton("文字颜色")
        self.background_color_button = QPushButton("背景颜色")
        self.text_color_button.clicked.connect(lambda: self._choose_color("text"))
        self.background_color_button.clicked.connect(lambda: self._choose_color("background"))
        self.animation_combo = QComboBox(); self.animation_combo.addItems(["无", "渐显", "滚动"])
        self.action_entity_edit = QLineEdit(); self.action_value_spin = QSpinBox(); self.action_value_spin.setRange(-9999, 9999)
        fields = (("文字", self.text_edit), ("绑定实体", self.binding_edit), ("X", self.x_spin), ("Y", self.y_spin), ("宽", self.w_spin), ("高", self.h_spin), ("字号", self.size_spin), ("文字颜色", self.text_color_button), ("背景颜色", self.background_color_button), ("动画", self.animation_combo), ("HA操作", self.action_edit), ("操作实体", self.action_entity_edit), ("操作值", self.action_value_spin))
        for label, widget in fields: wlayout.addRow(label, widget)
        container = QWidget(); container_layout = QVBoxLayout(container); container_layout.addWidget(tabs); container_layout.addWidget(widget_box); container_layout.addStretch()
        return container

    def _connect(self) -> None:
        self.add_action.clicked.connect(lambda: self.canvas.add_widget("label"))
        self.add_button.clicked.connect(lambda: self.canvas.add_widget("button"))
        self.delete_button.clicked.connect(self.canvas.remove_selected)
        self.canvas.selected.connect(self._select_widget)
        self.generate_button.clicked.connect(self._generate)
        self.validate_button.clicked.connect(lambda: self._run("validate"))
        self.compile_button.clicked.connect(lambda: self._run("compile"))
        self.flash_button.clicked.connect(self._flash)
        for widget in (self.text_edit, self.binding_edit, self.action_edit, self.action_entity_edit): widget.editingFinished.connect(self._apply_form)
        for widget in (self.x_spin, self.y_spin, self.w_spin, self.h_spin, self.size_spin, self.action_value_spin): widget.valueChanged.connect(self._apply_form)
        self.animation_combo.currentTextChanged.connect(self._apply_form)
        self.runner.output.connect(self.log.appendPlainText); self.runner.progress.connect(self.progress.setValue)
        self.runner.finished.connect(lambda ok, message: self.statusBar().showMessage(message))

    def _load_project_to_form(self) -> None:
        self.name_edit.setText(self.project.name); self.device_edit.setText(self.project.device_name); self.ssid_edit.setText(self.project.wifi_ssid)
        self.password_edit.setText(self.project.wifi_password); self.ha_edit.setText(self.project.ha_address); self.api_edit.setText(self.project.api_key); self.ota_edit.setText(self.project.ota_password)
        self.people1_edit.setText(self.project.people_entity_1); self.people2_edit.setText(self.project.people_entity_2)
        for edit in (self.name_edit, self.device_edit, self.ssid_edit, self.password_edit, self.ha_edit, self.api_edit, self.ota_edit, self.people1_edit, self.people2_edit): edit.editingFinished.connect(self._apply_project_form)

    def _apply_project_form(self) -> None:
        self.project.name = self.name_edit.text().strip(); self.project.device_name = self.device_edit.text().strip(); self.project.wifi_ssid = self.ssid_edit.text()
        self.project.wifi_password = self.password_edit.text(); self.project.ha_address = self.ha_edit.text().strip(); self.project.api_key = self.api_edit.text(); self.project.ota_password = self.ota_edit.text()
        self.project.people_entity_1 = self.people1_edit.text().strip(); self.project.people_entity_2 = self.people2_edit.text().strip()

    def _select_widget(self, model: WidgetModel | None) -> None:
        self.current_widget = model
        if model is None: return
        for widget, value in ((self.text_edit, model.text), (self.binding_edit, model.binding), (self.action_edit, model.action), (self.action_entity_edit, model.action_entity)):
            widget.blockSignals(True); widget.setText(value); widget.blockSignals(False)
        for widget, value in ((self.x_spin, model.x), (self.y_spin, model.y), (self.w_spin, model.width), (self.h_spin, model.height), (self.size_spin, model.font_size), (self.action_value_spin, int(model.action_value))):
            widget.blockSignals(True); widget.setValue(value); widget.blockSignals(False)
        self.animation_combo.blockSignals(True); self.animation_combo.setCurrentText(model.animation); self.animation_combo.blockSignals(False)
        self._set_color_button(self.text_color_button, model.text_color)
        self._set_color_button(self.background_color_button, model.background_color)

    def _apply_form(self) -> None:
        if not self.current_widget: return
        m = self.current_widget; m.text = self.text_edit.text(); m.binding = self.binding_edit.text().strip(); m.action = self.action_edit.text().strip(); m.action_entity = self.action_entity_edit.text().strip(); m.action_value = self.action_value_spin.value(); m.x = self.x_spin.value(); m.y = self.y_spin.value(); m.width = self.w_spin.value(); m.height = self.h_spin.value(); m.font_size = self.size_spin.value(); m.animation = self.animation_combo.currentText(); self.canvas.refresh_model(m)

    def _choose_color(self, target: str) -> None:
        if not self.current_widget:
            return
        current = self.current_widget.text_color if target == "text" else self.current_widget.background_color
        selected = QColorDialog.getColor(QColor(current), self, "选择颜色")
        if not selected.isValid():
            return
        value = selected.name().upper()
        if target == "text":
            self.current_widget.text_color = value
            self._set_color_button(self.text_color_button, value)
        else:
            self.current_widget.background_color = value
            self._set_color_button(self.background_color_button, value)
        self.canvas.refresh_model(self.current_widget)

    @staticmethod
    def _set_color_button(button: QPushButton, value: str) -> None:
        button.setText(value)
        button.setStyleSheet(f"background-color: {value}; color: #FFFFFF")

    def _choose_font(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择中文字体", "", "字体文件 (*.ttf *.otf *.woff)")
        if path: self.project.font_path = path; self.font_label.setText(Path(path).name)

    def _generate(self) -> bool:
        self._apply_project_form(); self._apply_form()
        try:
            self.generator.generate(self.project, self.yaml_path)
            self.project.save(self.root / "build" / "project.json")
            self.log.appendPlainText(f"已生成：{self.yaml_path}\n提示：HA地址用于记录，ESPHome通过原生API由HA主动连接设备。")
            self.statusBar().showMessage("配置生成完成"); return True
        except ValueError as exc:
            QMessageBox.warning(self, "配置无法生成", str(exc)); return False

    def _run(self, operation: str) -> None:
        if self.runner.running: return
        if not self._generate(): return
        getattr(self.runner, operation)(self.yaml_path)

    def _refresh_ports(self) -> None:
        if hasattr(self, "port_combo"): self.port_combo.clear()

    def _flash(self) -> None:
        if not self.runner.running and self._generate():
            ports = scan_serial_ports()
            if not ports:
                QMessageBox.warning(self, "未发现串口", "请连接USB数据线。首次烧录请按住BOOT键后再点击烧录。")
                return
            from PyQt6.QtWidgets import QInputDialog
            port, ok = QInputDialog.getItem(self, "选择烧录串口", "设备", [item.label for item in ports], 0, False)
            if ok:
                selected = next(item.port for item in ports if item.label == port)
                self.runner.upload(self.yaml_path, selected)
