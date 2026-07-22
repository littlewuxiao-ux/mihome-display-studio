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

## Home Assistant准备

1. `ha_xiaomi_home` 需要先把米家中枢极客版变量同步成 HA 数字实体。
2. 工作台里填写的是 HA 实体 ID，例如 `sensor.people_home_1` 或 `input_number.people_home_1`。
3. 首次烧录后，在 HA 中添加发现的 ESPHome 设备。
4. 如按钮需要调用 HA 操作，在 ESPHome 集成的设备配置中启用“允许设备执行 Home Assistant 操作”。

ESPHome 设备通过原生 API 与 HA 通信，并不直接连接 `ha_xiaomi_home` 的内部 MQTT。HA 地址目前作为项目记录字段保留，连接方向是 HA 主动连接屏幕设备。

## 模块

- `web/index.html`：浏览器工作台结构
- `web/styles.css`：响应式工作台、屏幕边框和属性面板样式
- `web/app.js`：画布拖拽、图片上传、项目编辑和任务日志交互
- `app/web_server.py`：本地HTTP API、项目保存、串口和ESPHome任务管理
- `app/models.py`：项目和组件数据模型
- `app/yaml_generator.py`：板卡、LVGL、字体、图片和HA实体YAML生成


## 更新记录

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
