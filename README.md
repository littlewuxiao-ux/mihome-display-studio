# 米家中枢屏幕工作台

面向 VIEWE `UEDX80480070E-WB-A`（ESP32-S3-N16R8、800x480 RGB、GT911）的中文可视化 ESPHome/LVGL 配置、编译和烧录工具。

## 仓库

- 远程仓库：<https://github.com/littlewuxiao-ux/mihome-display-studio>
- 默认分支：`main`
- 更新规则：每次功能更新后补充本README的“更新记录”，运行测试，通过后提交并推送到远程仓库。

## 启动

```powershell
python -m pip install -r requirements.txt
python main.py
```

工具调用当前 Python 环境中的 ESPHome，不包含独立编译内核。启动后会自动打开本地浏览器工作台，默认地址为 <http://127.0.0.1:8765>；生成结果和项目数据位于 `build/`。

## 媒体支持

- 静态图片：支持PNG、JPEG、WebP和BMP，单文件最大8MB。图片会按画布尺寸转换为RGB565并编译进固件，PNG/WebP可保留透明通道。
- 动图：ESPHome支持GIF帧动画，但大尺寸或高帧率内容会快速占满16MB Flash并增加PSRAM压力，本版本暂未开放。
- 视频：ESPHome/LVGL没有适用于该板卡的通用MP4/H.264视频解码链路，本版本不支持视频插入。

## 当前功能

- 图形与图片：统一入口创建矩形，并可在属性栏切换为椭圆、圆形或线条；图形支持填充、边框、圆角和图片内容。
- 几何调整：椭圆支持横向/纵向半径，圆形保持等半径，线条支持长度和`-180°`至`180°`方向。
- 文字编辑：所有图形和图片都可以叠加文字；选中组件后可直接在画布中编辑，并分别设置字号、颜色和对齐。
- 状态组件：提供圆形和柱状状态栏，可设置范围、预览值、颜色以及百分比/原始数值显示。
- 虚拟按钮：支持按压缩放、按压变暗或关闭反馈，并可调用Home Assistant操作。
- 多界面：支持新增界面、界面切换按钮、鼠标滚轮切换界面和组件层级调整。
- 数值操作：鼠标悬停在数字或滑块输入框上时，可以使用滚轮增减数值。

## Home Assistant准备

屏幕推荐使用`米家设备 -> Home Assistant -> ESPHome屏幕`的数据链路。ESPHome设备通过原生API与HA通信，并不直接连接`ha_xiaomi_home`的内部MQTT；项目中的HA地址目前作为记录字段保留，实际连接方向是HA主动连接屏幕设备。

1. 在HA的“设置 -> 设备与服务”中配置官方`Xiaomi Home`集成；官方集成未覆盖的设备可按实际环境使用HACS中的`Xiaomi Miot Auto`。
2. 确保集成登录的账号和地区与米家App一致，然后在“开发者工具 -> 状态”中找到设备实体ID。
3. 首次烧录后，在HA中添加发现的ESPHome设备，并填写工作台配置的API加密密钥。
4. 在工作台选择图形、图片或状态栏，填写实体ID，例如`sensor.living_room_temperature`或`climate.living_room`。
5. 温度、湿度、功率和占用率选择“数值”；空调、门锁、灯光等开关/模式选择“设备状态”。圆形和柱状状态栏只能绑定数值实体。
6. 按钮需要控制设备时，填写HA操作和实体，例如`light.toggle`与`light.living_room`，并在ESPHome集成中允许设备执行Home Assistant操作。

CPU、内存和磁盘数据可通过HA“系统监视器”集成提供；PC或服务器的CPU/GPU数据可通过Glances接入。常见实体包括`sensor.processor_use`、`sensor.memory_use_percent`和`sensor.pc_gpu_load`，实际名称以HA开发者工具中显示的实体ID为准。

如果米家设备把数值放在实体属性中，例如空调的`current_temperature`，可先在HA中创建模板传感器，再把生成的`sensor`实体绑定到状态栏：

```yaml configuration.yaml
# ... existing configuration ...
template:
  - sensor:
      - name: "客厅空调当前温度"
        unique_id: living_room_ac_current_temperature
        unit_of_measurement: "°C"
        state: >
          {{ state_attr('climate.living_room', 'current_temperature') }}
```

## 模块

- `web/index.html`：浏览器工作台结构
- `web/styles.css`：响应式工作台、屏幕边框和属性面板样式
- `web/app.js`：画布拖拽、图片上传、项目编辑和任务日志交互
- `app/web_server.py`：本地HTTP API、项目保存、串口和ESPHome任务管理
- `app/models.py`：项目和组件数据模型
- `app/yaml_generator.py`：板卡、LVGL、字体、图片和HA实体YAML生成


## 更新记录

### 2026-07-23（图形、状态栏与米家状态联动）

- 将文本、图片和基础形状整合为“图形与图片”工作流，旧文本组件在浏览器中自动按矩形图形处理。
- 为矩形、椭圆、圆形、线条和图片统一增加叠加文字、字号、颜色、对齐、图片内容及Home Assistant实体绑定。
- 增加椭圆横向/纵向半径、圆形等半径、线条长度和方向参数，并让画布缩放与几何参数同步。
- 增加数字和滑块输入框的鼠标滚轮调节，支持在画布中直接编辑各组件文字。
- 增加圆形状态栏和柱状状态栏，支持范围、预览值、进度颜色、百分比/数值显示以及HA实时更新。
- 将实体绑定分为“数值”和“设备状态”，分别生成ESPHome Home Assistant `sensor`与`text_sensor`配置。
- 增加虚拟按钮按压缩放、按压变暗和无反馈三种触摸效果，并同步生成LVGL `pressed`样式。
- 完善多界面、界面切换按钮、滚轮换页、组件层级、图片裁切与固件图片预处理。
- 补充米家设备、HA模板传感器、CPU/GPU状态投屏和按钮控制说明。
- 通过6项单元测试、前端语法检查、浏览器交互检查及ESPHome `2026.7.1`真实配置校验。

### 2026-07-22（Web工作台）

- 主界面由PyQt6桌面窗口切换为本地浏览器工作台，启动命令保持`python main.py`。
- 加入带物理外框、坐标标记和越界裁切的800x480屏幕画布，并支持60%、80%和100%缩放。
- 右侧属性栏扩展至360-410px并支持独立滚动，完整显示设备、网络、布局、样式和触摸操作字段。
- 加入PNG、JPEG、WebP和BMP上传、预览、拖拽、缩放、替换及ESPHome/LVGL静态图片YAML生成。
- 集成浏览器内项目自动保存、串口刷新、配置生成、校验、编译、烧录进度和实时日志。
- 明确标记常规视频不受支持，避免生成板卡无法解码的固件配置。
- 通过桌面和紧凑视口浏览器截图检查、前端交互检查、3项单元测试及真实图片配置`esphome config`校验。

### 2026-07-22（初始版本）

- 建立PyQt6中文桌面应用和800x480可视化拖拽画布。
- 支持文本、触摸按钮、坐标、尺寸、字号、颜色和滚动/渐显动画配置。
- 加入VIEWE开发板RGB显示、GT911触摸、PSRAM、背光及中文字体YAML生成。
- 加入Home Assistant数字实体订阅和LVGL标签实时更新。
- 加入ESPHome后台校验、编译、串口扫描、烧录进度及基础错误中文提示。
- 安装并验证ESPHome `2026.7.1`，生成配置已通过真实`esphome config`校验。
- 初始化Git版本管理，生成内容、缓存和本地敏感文件不进入仓库。
- 创建并绑定GitHub公开仓库，建立更新后测试、提交和推送的维护流程。

## 硬件说明

板卡引脚来自随项目提供的 VIEWE 快速指南。显示时序采用 800x480 RGB 面板的保守初始值；首次烧录应先验证测试画面、颜色和触摸方向。不同硬件修订版如显示抖动，需要按该修订版屏幕规格调整 porch 和 PCLK 参数。
