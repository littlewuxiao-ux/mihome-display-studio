const state = { project: null, selectedId: null, selectedIds: [], activePageId: "main_page", zoom: 1, dirty: false, taskTimer: null, serialTimer: null, pointer: null, marquee: null, uploadMode: "new", history: [], future: [], historySuspended: false, componentClipboard: null, styleClipboard: null };
const RECOVERY_KEY = "mijia-panel-recovery-v1";
const USER_TEMPLATES_KEY = "mijia-panel-user-templates-v1";
const SENSITIVE_PROJECT_FIELDS = ["wifi_password", "api_key", "ota_password"];
const ICON_CATALOG = {
  "空调模式": [["关闭", 0xF081D], ["制冷", 0xF0717], ["制热", 0xF0238], ["除湿", 0xF058E], ["送风", 0xF0210], ["自动", 0xF001B]],
  "人员与作息": [["成人", 0xF0004], ["男性", 0xF064D], ["女性", 0xF0649], ["老人", 0xF1581], ["儿童", 0xF02E7], ["不在", 0xF000D], ["床铺", 0xF02E3], ["起床", 0xF08A0], ["睡眠", 0xF04B2]],
  "连接": [["WiFi", 0xF05A9], ["蓝牙", 0xF00AF], ["网络", 0xF06F3], ["手机", 0xF03A4]],
  "控制": [["加", 0xF0415], ["减", 0xF0374], ["开关", 0xF0425], ["设置", 0xF0493], ["刷新", 0xF0450]],
  "家居": [["主页", 0xF02DC], ["灯光", 0xF0335], ["关灯", 0xF0E4F], ["空调", 0xF001B], ["关空调", 0xF081D], ["温度", 0xF050F], ["湿度", 0xF058E], ["门锁", 0xF033E]],
  "状态": [["电池", 0xF0079], ["提醒", 0xF0026], ["成功", 0xF012C], ["错误", 0xF0156], ["信息", 0xF02FC]],
};


const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function updateRangeValue(input) {
  const output = input.parentElement?.querySelector(":scope > .range-value");
  if (!output) return;
  const property = input.dataset.widgetNumber || input.dataset.project || input.dataset.page || "";
  output.textContent = `${input.value}${property === "image_blur" ? " px" : "%"}`;
}

function initializeRangeValues() {
  $$('input[type="range"]').forEach((input) => {
    if (!input.parentElement.querySelector(":scope > .range-value")) {
      const output = document.createElement("output");
      output.className = "range-value";
      input.insertAdjacentElement("afterend", output);
    }
    input.addEventListener("input", () => updateRangeValue(input));
    updateRangeValue(input);
  });
}

function syncRangeValues() {
  $$('input[type="range"]').forEach(updateRangeValue);
}

async function request(url, options = {}) {
  const response = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || `请求失败：${response.status}`);
  return data;
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(node.timer);
  node.timer = setTimeout(() => node.classList.remove("show"), 2800);
}

function activePage() {
  return state.project?.pages.find((page) => page.id === state.activePageId) || null;
}

function colorWithOpacity(hex, opacity) {
  const value = String(hex || "#000000").replace("#", "");
  const normalized = value.length === 3 ? value.split("").map((part) => part + part).join("") : value.padEnd(6, "0").slice(0, 6);
  return `rgba(${parseInt(normalized.slice(0, 2), 16)}, ${parseInt(normalized.slice(2, 4), 16)}, ${parseInt(normalized.slice(4, 6), 16)}, ${Math.max(0, Math.min(100, Number(opacity ?? 100))) / 100})`;
}


function selectedWidget() {
  return state.project?.widgets.find((item) => item.id === state.selectedId) || null;
}

function selectedWidgets() {
  const ids = new Set(state.selectedIds.length ? state.selectedIds : state.selectedId ? [state.selectedId] : []);
  return state.project?.widgets.filter((item) => ids.has(item.id)) || [];
}

function widgetPages(widget) {
  return Array.isArray(widget.pages) && widget.pages.length ? widget.pages : [widget.page];
}

function widgetOnPage(widget, pageId) {
  return widgetPages(widget).includes(pageId);
}

function widgetVisibleInContainerPreview(widget) {
  if (!widget.parent_id) return true;
  const parent = state.project.widgets.find((item) => item.id === widget.parent_id); if (!parent) return true;
  if (!widgetVisibleInContainerPreview(parent)) return false;
  if (parent.kind === "tabview") return Number(widget.view_index || 0) === Number(parent.view_preview_index || 0);
  if (parent.kind === "tileview") return Number(widget.grid_row || 0) === Number(parent.view_preview_row || 0) && Number(widget.grid_column || 0) === Number(parent.view_preview_column || 0);
  return true;
}

function cloneProject(project = state.project) {
  return JSON.parse(JSON.stringify(project));
}

function recoveryProject(project = state.project) {
  const draft = cloneProject(project);
  for (const field of SENSITIVE_PROJECT_FIELDS) draft[field] = "";
  return draft;
}

function storeRecoveryDraft() {
  if (!state.project) return;
  try {
    localStorage.setItem(RECOVERY_KEY, JSON.stringify({ savedAt: new Date().toISOString(), project: recoveryProject() }));
  } catch (_error) {
    // Automatic server saves remain the fallback when browser storage is unavailable.
  }
}

function clearRecoveryDraft() {
  try { localStorage.removeItem(RECOVERY_KEY); } catch (_error) { /* Storage may be disabled. */ }
}

function takeRecoveryDraft(serverProject) {
  try {
    const raw = localStorage.getItem(RECOVERY_KEY);
    if (!raw) return serverProject;
    const draft = JSON.parse(raw);
    if (!draft?.project || !window.confirm(`发现 ${new Date(draft.savedAt).toLocaleString()} 的未保存编辑，是否恢复？`)) {
      clearRecoveryDraft();
      return serverProject;
    }
    for (const field of SENSITIVE_PROJECT_FIELDS) draft.project[field] = serverProject[field] || "";
    return draft.project;
  } catch (_error) {
    clearRecoveryDraft();
    return serverProject;
  }
}





function recordHistory(snapshot) {
  if (state.historySuspended || !snapshot || JSON.stringify(snapshot) === JSON.stringify(state.project)) return;

  state.history.push(snapshot);
  state.history.splice(0, Math.max(0, state.history.length - 50));
  state.future = [];
  updateHistoryButtons();
}

function updateHistoryButtons() {
  const undo = $("#undoBtn"), redo = $("#redoBtn");
  if (undo) undo.disabled = state.history.length === 0;
  if (redo) redo.disabled = state.future.length === 0;
}

function refreshEditor() {
  state.activePageId = state.project.pages.some((page) => page.id === state.activePageId) ? state.activePageId : state.project.pages[0].id;
  state.selectedId = state.project.widgets.some((widget) => widget.id === state.selectedId) ? state.selectedId : null;
  state.selectedIds = state.selectedId ? [state.selectedId] : [];
  $$('[data-project]').forEach((input) => { input.value = state.project[input.dataset.project] ?? ""; });
  if (state.selectedId) selectWidget(state.selectedId); else switchPage(state.activePageId);
  updateHistoryButtons();
}

function undo() {
  if (!state.history.length) return;
  state.future.push(cloneProject());
  state.historySuspended = true;
  state.project = cloneProject(state.history.pop());
  state.historySuspended = false;
  refreshEditor(); markDirty(); saveProject();
}

function redo() {
  if (!state.future.length) return;
  state.history.push(cloneProject());
  state.historySuspended = true;
  state.project = cloneProject(state.future.pop());
  state.historySuspended = false;
  refreshEditor(); markDirty(); saveProject();
}


function clamp(widget) {
  if (widget.kind === "shape" && ["ellipse", "circle"].includes(widget.shape_type)) {
    if (widget.shape_type === "circle") widget.ellipse_radius_y = widget.ellipse_radius_x;
    widget.width = widget.ellipse_radius_x * 2; widget.height = widget.ellipse_radius_y * 2;
  }
  if (widget.kind === "shape" && widget.shape_type === "line") {
    const radians = widget.line_angle * Math.PI / 180;
    widget.width = Math.max(20, Math.round(Math.abs(Math.cos(radians) * widget.line_length) + widget.border_width));
    widget.height = Math.max(20, Math.round(Math.abs(Math.sin(radians) * widget.line_length) + widget.border_width));
  }
  widget.width = Math.max(20, Math.min(800, Number(widget.width) || 20));
  widget.height = Math.max(20, Math.min(480, Number(widget.height) || 20));
  widget.x = Math.max(0, Math.min(800 - widget.width, Number(widget.x) || 0));
  widget.y = Math.max(0, Math.min(480 - widget.height, Number(widget.y) || 0));
  widget.font_size = Math.max(8, Math.min(96, Number(widget.font_size) || 28));
  widget.progress_max = Math.max(Number(widget.progress_min) + 1, Number(widget.progress_max));
  widget.progress_value = Math.max(Number(widget.progress_min), Math.min(Number(widget.progress_max), Number(widget.progress_value)));
  widget.view_preview_index = Math.max(0, Number(widget.view_preview_index) || 0);
  widget.view_preview_row = Math.max(0, Math.min((Number(widget.grid_rows) || 1) - 1, Number(widget.view_preview_row) || 0));
  widget.view_preview_column = Math.max(0, Math.min((Number(widget.grid_columns) || 1) - 1, Number(widget.view_preview_column) || 0));
}

function progressPercent(widget) {
  return Math.max(0, Math.min(100, (widget.progress_value - widget.progress_min) * 100 / (widget.progress_max - widget.progress_min)));
}

function fontSample(widget) {
  if (widget.kind === "battery") return widget.battery_display === "full" ? "100% 4.20V 1.00A 4.20W 12.0h" : "100%";
  const title = widget.show_fixed_title === false ? "" : widget.text || "";
  if (!widget.binding) return title;
  const localSample = { "device:current_time": "2026-09-15 23:59", "device:ip_address": "192.168.100.255", "device:ssid": "WWWWWWWWWWWW", "device:wifi_status": "已连接" }[widget.binding];
  if (localSample) return `${title} ${localSample}`.trim();
  if (widget.binding_type === "state") return `${title} unavailable`.trim();
  return `${title} -888${widget.value_decimals ? `.${"8".repeat(widget.value_decimals)}` : ""} ${widget.value_suffix || ""}`.trim();
}

function canvasGeometry(widget) {
  let x = Number(widget.x) || 0, y = Number(widget.y) || 0, width = widget.width, height = widget.height;
  const parent = state.project.widgets.find((item) => item.id === widget.parent_id);
  if (!parent) return { x, y, width, height };
  const outer = canvasGeometry(parent);
  if (parent.layout_type === "grid") {
    const gapX = parent.layout_pad_column || 0, gapY = parent.layout_pad_row || 0;
    const cellW = (parent.width - gapX * (parent.grid_columns - 1)) / parent.grid_columns, cellH = (parent.height - gapY * (parent.grid_rows - 1)) / parent.grid_rows;
    return { x: outer.x + widget.grid_column * (cellW + gapX), y: outer.y + widget.grid_row * (cellH + gapY), width: cellW * widget.grid_column_span + gapX * (widget.grid_column_span - 1), height: cellH * widget.grid_row_span + gapY * (widget.grid_row_span - 1) };
  }
  if (parent.layout_type === "flex") {
    let siblings = state.project.widgets.filter((item) => item.parent_id === parent.id).sort((a, b) => a.z_index - b.z_index);
    if (parent.flex_flow.endsWith("reverse")) siblings = siblings.reverse();
    const column = parent.flex_flow.startsWith("column"), wrap = parent.flex_flow.includes("wrap");
    const gapX = Number(parent.layout_pad_column) || 0, gapY = Number(parent.layout_pad_row) || 0;
    let cursorX = 0, cursorY = 0, trackSize = 0;
    for (const item of siblings) {
      if (column && wrap && cursorY > 0 && cursorY + item.height > parent.height) { cursorY = 0; cursorX += trackSize + gapX; trackSize = 0; }
      if (!column && wrap && cursorX > 0 && cursorX + item.width > parent.width) { cursorX = 0; cursorY += trackSize + gapY; trackSize = 0; }
      if (item.id === widget.id) return { x: outer.x + cursorX, y: outer.y + cursorY, width, height };
      if (column) {
        cursorY += item.height + gapY; trackSize = Math.max(trackSize, item.width);
      } else {
        cursorX += item.width + gapX; trackSize = Math.max(trackSize, item.height);
      }
    }
    return { x: outer.x, y: outer.y, width, height };
  }
  return { x: outer.x + x, y: outer.y + y, width, height };
}

function effectiveFontSize(widget) {
  if (widget.auto_fit_text === false) return Number(widget.font_size);
  // HA state labels are explicitly sized in the inspector. Do not silently
  // clamp them to the longest possible state/title string, otherwise changing
  // the base font size appears to have no effect in the preview.
  if (widget.binding_type === "state" && (widget.state_mapping || widget.state_variants?.length)) return Number(widget.font_size);
  const units = Array.from(fontSample(widget)).reduce((total, character) => total + (character.codePointAt(0) > 0xFF ? 1 : 0.58), 0) || 1;
  const widthFit = Math.floor(Math.max(8, widget.width - 12) / units);
  const heightFit = Math.floor(Math.max(8, widget.height - 6) / 1.15);
  return Math.max(8, Math.min(widget.font_size, widthFit, heightFit));
}

function appendEditableText(node, widget, text) {
  const label = document.createElement("span");
  label.className = "widget-text"; label.textContent = text;
  const fittedSize = effectiveFontSize(widget);
  label.style.fontSize = `${fittedSize * state.zoom}px`;
  label.style.textAlign = widget.text_align;
  label.style.opacity = (widget.text_opacity ?? 100) / 100;
  label.style.transform = `translate(${(widget.text_offset_x || 0) * state.zoom}px, ${(widget.text_offset_y || 0) * state.zoom}px)`;
  if (widget.id === state.selectedId) {
    label.addEventListener("dblclick", (event) => { event.stopPropagation(); label.contentEditable = "true"; label.focus(); });
        label.addEventListener("focus", () => { label.textContent = widget.text; label.historySnapshot = cloneProject(); });
    label.addEventListener("input", () => { widget.text = label.innerText.replace(/\n/g, " "); $('[data-widget="text"]').value = widget.text; markDirty(); });
    label.addEventListener("blur", () => { label.contentEditable = "false"; recordHistory(label.historySnapshot); renderCanvas(); saveProject(); });

    label.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); label.blur(); } });
  }
  node.append(label);
}

function assetUrl(path) {
  if (!path) return "";
  return `/asset/${encodeURIComponent(path.replaceAll("\\", "/").split("/").pop())}`;
}

function renderPageTabs() {
  const tabs = $("#pageTabs");
  tabs.replaceChildren();
  for (const page of state.project.pages) {
    const button = document.createElement("button");
    button.textContent = page.name;
    button.classList.toggle("active", page.id === state.activePageId);
    button.addEventListener("click", () => switchPage(page.id));
    tabs.append(button);
  }
  const options = state.project.pages.map((page) => `<option value="${page.id}">${page.name}</option>`).join("");
    const activeSelect = $("#activePageSelect");
  activeSelect.innerHTML = options;
  activeSelect.value = state.activePageId;
  const currentPage = activePage();
  $("#defaultPage").checked = state.project.default_page === state.activePageId;
  $$('[data-page]').forEach((input) => { input.value = currentPage?.[input.dataset.page] ?? ""; });

    $("#widgetPage").innerHTML = options;
    $('[data-widget="target_page"]').innerHTML = options;
  $("#deletePageBtn").disabled = state.project.pages.length <= 1;

}

function userTemplates() {
  try { return JSON.parse(localStorage.getItem(USER_TEMPLATES_KEY) || "[]"); } catch (_error) { return []; }
}

function renderUserTemplates() {
  const templates = userTemplates(), select = $("#userTemplateSelect");
  select.innerHTML = templates.length ? templates.map((item, index) => `<option value="${index}">${item.name}</option>`).join("") : '<option value="">暂无模板</option>';
}

function saveUserTemplate() {
  const widget = selectedWidget(); if (!widget) { toast("请先选择一个组件"); return; }
  const name = window.prompt("模板名称", widget.text || widget.kind); if (!name) return;
  const templates = userTemplates(), data = JSON.parse(JSON.stringify(widget));
  delete data.id; delete data.page; delete data.pages; delete data.x; delete data.y; delete data.z_index; delete data.group_id;
  templates.push({ name, data }); localStorage.setItem(USER_TEMPLATES_KEY, JSON.stringify(templates.slice(-50))); renderUserTemplates(); toast("个人模板已保存");
}

function loadUserTemplate() {
  const item = userTemplates()[Number($("#userTemplateSelect").value)];
  if (!item) return; newWidget(item.data.kind, item.data);
}

function layerSummary(widget) {
  const names = { shape: { rectangle: "矩形", ellipse: "椭圆", circle: "圆形", line: "线条" }[widget.shape_type] || "形状", image: "图片", icon: "图标", button: "按钮", page_button: "页面按钮", label: "标签", progress_circle: "圆环仪表", progress_bar: "进度仪表", trend_chart: "趋势图", buttonmatrix: "按钮矩阵", table: "表格", container: "布局容器", tabview: "标签页", tileview: "磁贴页", msgbox: "消息框", slider: "滑块", switch: "开关", checkbox: "复选框", dropdown: "下拉框", roller: "滚轮", spinbox: "数字框", spinner: "加载指示", led: "LED", qrcode: "二维码", textarea: "输入框", keyboard: "键盘", battery: "电池" };
  let detail = widget.text || "";
  if (widget.kind === "image") detail = (widget.asset_path || "").split(/[\\/]/).pop() || "未选择图片";
  if (widget.kind === "icon") detail = widget.icon_name || detail;
  if (widget.kind === "container") detail = ({ flex: "Flex", grid: "Grid", none: "自由布局" })[widget.layout_type] || "";
  if (widget.kind === "trend_chart") detail = ({ line: "折线", step: "阶梯", bar: "柱状" })[widget.trend_mode || "line"];
  return { name: names[widget.kind] || widget.kind, detail: detail && detail !== names[widget.kind] ? detail : "" };
}

function renderLayerTree() {
  const tree = $("#layerTree"), query = $("#layerSearch").value.trim().toLowerCase();
  tree.replaceChildren();
  const widgets = state.project.widgets.filter((widget) => widgetOnPage(widget, state.activePageId))
    .filter((widget) => !query || `${widget.text} ${widget.id} ${widget.kind}`.toLowerCase().includes(query))
    .sort((a, b) => b.z_index - a.z_index);
  for (const widget of widgets) {
    const button = document.createElement("button");
    button.className = `layer-item${state.selectedIds.includes(widget.id) ? " active" : ""}${widget.hidden ? " hidden-layer" : ""}`;
    const summary = layerSummary(widget);
    button.innerHTML = `<b>${widget.hidden ? "○" : "●"}</b><span>${summary.name}${summary.detail ? ` · ${summary.detail}` : ""}</span><em>${widget.locked ? "锁定" : `#${widget.z_index}`}</em>`;
    button.addEventListener("click", () => selectWidget(widget.id));
    tree.append(button);
  }
}

function switchPage(pageId) {
  if (!state.project.pages.some((page) => page.id === pageId)) return;
  state.activePageId = pageId;
  state.selectedId = null;
  state.selectedIds = [];
  renderPageTabs();
  renderCanvas();
  $("#projectForm").classList.remove("hidden");
  $("#widgetForm").classList.add("hidden");
}

function cyclePage(direction) {
  const index = state.project.pages.findIndex((page) => page.id === state.activePageId);
  const next = (index + direction + state.project.pages.length) % state.project.pages.length;
  switchPage(state.project.pages[next].id);
}

function renderCanvas() {
  const screen = $("#screen");
  const page = state.project.pages.find((item) => item.id === state.activePageId);
    if (page?.background_gradient === "horizontal") screen.style.background = `linear-gradient(90deg, ${page.background_color}, ${page.background_color_2})`;
  else if (page?.background_gradient === "vertical") screen.style.background = `linear-gradient(180deg, ${page.background_color}, ${page.background_color_2})`;
  else screen.style.background = page?.background_color || "#080B10";

  screen.replaceChildren();
  const widgets = state.project.widgets.filter((widget) => !widget.hidden && widgetOnPage(widget, state.activePageId) && widgetVisibleInContainerPreview(widget)).sort((a, b) => a.z_index - b.z_index);
  for (const widget of widgets) {
    clamp(widget);
    const position = canvasGeometry(widget);
    const node = document.createElement("div");
    const groupedSelection = state.selectedIds.length > 1 && widget.group_id && selectedWidgets().every((item) => item.group_id === widget.group_id);
    node.className = `canvas-widget ${widget.kind} shape-${widget.shape_type} effect-${widget.click_effect}${state.selectedIds.includes(widget.id) && !groupedSelection ? " selected" : ""}`;
    node.dataset.id = widget.id;
    Object.assign(node.style, {
      left: `${position.x * state.zoom}px`, top: `${position.y * state.zoom}px`,
      width: `${position.width * state.zoom}px`, height: `${position.height * state.zoom}px`,
            color: widget.text_color, backgroundColor: widget.kind === "image" ? "transparent" : colorWithOpacity(widget.background_color, widget.background_opacity ?? 100),

      borderColor: colorWithOpacity(widget.border_color, widget.border_opacity ?? 100), borderWidth: `${widget.border_width * state.zoom}px`,
      borderRadius: ["ellipse", "circle"].includes(widget.shape_type) ? "50%" : `${widget.radius * state.zoom}px`,
      fontSize: `${widget.font_size * state.zoom}px`, zIndex: widget.z_index, opacity: (widget.opacity ?? 100) / 100,
    });
    if (widget.kind === "shape" && widget.shape_type === "line") {
      node.style.background = "transparent"; node.style.border = "0"; node.style.overflow = "visible";
      const line = document.createElement("i"); line.className = "shape-line-segment";
            const radians = widget.line_angle * Math.PI / 180;
      const dx = Math.cos(radians) * widget.line_length * state.zoom, dy = Math.sin(radians) * widget.line_length * state.zoom;
      line.style.left = `${Math.max(0, -dx)}px`; line.style.top = `${Math.max(0, -dy)}px`;
      line.style.width = `${widget.line_length * state.zoom}px`; line.style.height = `${Math.max(1, widget.border_width) * state.zoom}px`;

      line.style.background = colorWithOpacity(widget.border_color, widget.border_opacity ?? 100); line.style.transform = `rotate(${widget.line_angle}deg)`;
      node.append(line);
    } else if (widget.kind === "battery") {
      const percent = progressPercent(widget);
      node.style.border = "0";
      if (widget.battery_style === "ring") {
        node.style.borderRadius = "50%";
        const batteryColor = percent <= 20 ? widget.battery_low_color : (widget.battery_discharge_color || widget.progress_color);
        node.style.background = `conic-gradient(${batteryColor} ${percent}%, ${widget.background_color} 0)`;
        const hole = document.createElement("i"); hole.className = "progress-hole"; node.append(hole);
      } else {
        const fill = document.createElement("i"); fill.className = "progress-fill";
        if (widget.battery_style === "vertical") Object.assign(fill.style, { width: "100%", height: `${percent}%`, top: "auto" });
        else fill.style.width = `${percent}%`;
        fill.style.background = percent <= 20 ? widget.battery_low_color : (widget.battery_discharge_color || widget.progress_color); node.append(fill);
      }
    } else if (widget.kind === "progress_circle") {
      const percent = progressPercent(widget);
      node.style.borderRadius = "50%";
      // LVGL arcs run from 135 degrees to 45 degrees: a 270 degree sweep with
      // a 90 degree gap. Match that geometry in the editor preview.
      const sweep = percent * 0.75;
      node.style.border = "0";
      const progressColor = colorWithOpacity(widget.progress_color, widget.border_opacity ?? 100);
      const trackColor = colorWithOpacity(widget.background_color, widget.background_opacity ?? 100);
      node.style.background = "transparent";
      const ring = document.createElement("i"); ring.className = "progress-ring";
      const arcWidth = Math.max(3, widget.border_width || 0) * state.zoom;
      ring.style.background = `conic-gradient(from 225deg, ${progressColor} 0 ${sweep}%, ${trackColor} ${sweep}% 75%, transparent 75% 100%)`;
      ring.style.webkitMask = `radial-gradient(farthest-side, transparent calc(100% - ${arcWidth}px), #000 calc(100% - ${arcWidth}px + 1px))`;
      ring.style.mask = ring.style.webkitMask; node.append(ring);
    } else if (widget.kind === "progress_bar") {
      const fill = document.createElement("i"); fill.className = "progress-fill"; fill.style.width = `${progressPercent(widget)}%`; fill.style.background = widget.progress_color; node.append(fill);
    } else if (widget.kind === "slider") {
      node.style.background = "transparent"; node.style.border = "0";
      const track = document.createElement("i"); track.className = "native-slider-track";
      const percent = progressPercent(widget);
      track.style.setProperty("--slider-percent", `${percent}%`);
      const railMargin = Math.min(12, Math.max(2, Math.floor(widget.width / 8)));
      Object.assign(track.style, { left: `${railMargin * state.zoom}px`, right: `${railMargin * state.zoom}px`, height: `${Math.min(8, widget.height) * state.zoom}px` });
      if (widget.ha_visual_mode === "slider_value") { const value = document.createElement("span"); value.className = "slider-value"; value.textContent = widget.binding ? `--${widget.value_suffix || ""}` : Number(widget.progress_value).toFixed(widget.value_decimals || 0) + (widget.value_suffix || ""); Object.assign(value.style, { position: "absolute", top: "0", width: "100%", textAlign: "center", fontSize: `${effectiveFontSize(widget) * state.zoom}px` }); node.append(value); }
      const fill = document.createElement("i"); fill.className = "native-slider-fill"; fill.style.width = `${percent}%`; fill.style.background = widget.progress_color;
      const knob = document.createElement("i"); knob.className = "native-slider-knob"; knob.style.left = `clamp(0px, ${percent}%, 100%)`; knob.style.background = widget.text_color;
      track.style.background = colorWithOpacity(widget.background_color, widget.background_opacity ?? 100); track.append(fill, knob); node.append(track);
    } else if (widget.kind === "switch") {
      node.style.border = "0"; node.style.borderRadius = `${widget.height / 2 * state.zoom}px`;
      node.style.background = widget.control_checked ? widget.progress_color : colorWithOpacity(widget.background_color, widget.background_opacity ?? 100);
      const knob = document.createElement("i"); knob.className = "native-switch-knob"; knob.classList.toggle("checked", Boolean(widget.control_checked)); knob.style.background = widget.text_color; node.append(knob);
    } else if (widget.kind === "checkbox") {
      node.style.background = "transparent"; node.style.border = "0"; node.style.justifyItems = "start";
      const mark = document.createElement("i"); mark.className = "native-checkbox-mark"; mark.style.borderColor = widget.border_color;
      if (widget.control_checked) { mark.textContent = "✓"; mark.style.background = widget.progress_color; }
      const label = document.createElement("span"); label.className = "native-control-label"; label.textContent = widget.text; node.append(mark, label);
    } else if (widget.kind === "dropdown") {
      const options = String(widget.control_options || "选项一").split("\n").filter(Boolean);
      node.style.background = colorWithOpacity(widget.background_color, widget.background_opacity ?? 100);
      const label = document.createElement("span"); label.className = "native-dropdown-label"; label.textContent = options[widget.control_selected] || options[0];
      const symbol = document.createElement("span"); symbol.className = "native-dropdown-symbol"; symbol.textContent = "⌄"; node.append(label, symbol);
    } else if (widget.kind === "roller") {
      const options = String(widget.control_options || "选项一").split("\n").filter(Boolean);
      node.classList.add("native-roller");
      options.slice(0, widget.control_rows || 3).forEach((option, index) => { const row = document.createElement("span"); row.textContent = option; row.classList.toggle("active", index === widget.control_selected); node.append(row); });
    } else if (widget.kind === "spinbox") {
      node.classList.add("native-spinbox"); node.textContent = Number(widget.progress_value).toFixed(widget.control_decimals || 0);
    } else if (widget.kind === "spinner") {
      node.style.background = "transparent"; node.style.border = "0"; const ring = document.createElement("i"); ring.className = "native-spinner"; ring.style.borderColor = `${widget.background_color} ${widget.progress_color} ${widget.progress_color}`; node.append(ring);
    } else if (widget.kind === "led") {
      node.style.background = "transparent"; node.style.border = "0"; const led = document.createElement("i"); led.className = "native-led"; led.style.background = widget.progress_color; led.style.opacity = progressPercent(widget) / 100; node.append(led);
    } else if (widget.kind === "qrcode") {
      node.classList.add("native-qrcode"); node.style.color = widget.text_color; node.style.backgroundColor = widget.background_color;
    } else if (widget.kind === "textarea") {
      node.classList.add("native-textarea"); node.textContent = widget.text || widget.control_text || "请输入内容";
    } else if (widget.kind === "keyboard") {
      node.classList.add("native-keyboard"); "QWERTYUIOPASDFGHJKLZXCVBNM".split("").forEach((key) => { const item = document.createElement("i"); item.textContent = key; node.append(item); });
    } else if (widget.kind === "trend_chart") {
      node.classList.add("trend-chart-preview");
      const values = [58, 42, 64, 35, 48, 30, 54, 26, 40, 22, 37, 18];
      const hasHeader = widget.trend_show_title !== false || widget.trend_show_current !== false;
      const headerSpace = hasHeader ? 30 : 6, captionSpace = widget.trend_caption ? 14 : 0, bottomSpace = widget.trend_show_x_axis !== false ? 22 : 6;
      const chartX = widget.trend_show_y_axis !== false ? 36 : 8;
      const chartWidth = Math.max(20, widget.width - (widget.trend_show_y_axis !== false ? 46 : 16) - (widget.trend_show_x_axis !== false ? 42 : 0));
      const chartHeight = Math.max(20, widget.height - headerSpace - bottomSpace - captionSpace);
      const plot = document.createElement("div"); plot.className = "trend-plot";
      Object.assign(plot.style, { left: `${chartX * state.zoom}px`, top: `${headerSpace * state.zoom}px`, width: `${chartWidth * state.zoom}px`, height: `${chartHeight * state.zoom}px` });
      const yTicks = widget.trend_y_ticks || 5;
      const axisColor = widget.trend_axis_color || "#AEB7C2";
      if (widget.trend_show_y_axis !== false) for (let tick = 0; tick < yTicks; tick++) { const grid = document.createElement("b"); grid.className = "trend-grid-line"; grid.style.top = `${tick * 100 / Math.max(1, yTicks - 1)}%`; plot.append(grid); }
      if (widget.trend_mode === "bar") values.forEach((value, index) => { const bar = document.createElement("i"); bar.style.left = `${index * 100 / values.length + 1}%`; bar.style.bottom = "0"; bar.style.width = `${75 / values.length}%`; bar.style.height = `${100 - value}%`; bar.style.background = widget.progress_color; plot.append(bar); });
      else values.forEach((value, index) => { if (!index) return; const segments = widget.trend_mode === "step" ? [[(index - 1) * 100 / (values.length - 1), values[index - 1], index * 100 / (values.length - 1), values[index - 1]], [index * 100 / (values.length - 1), values[index - 1], index * 100 / (values.length - 1), value]] : [[(index - 1) * 100 / (values.length - 1), values[index - 1], index * 100 / (values.length - 1), value]]; segments.forEach(([x1, y1, x2, y2]) => { const line = document.createElement("i"); const dx = x2 - x1, dy = y2 - y1; line.style.left = `${x1}%`; line.style.top = `${y1}%`; line.style.width = `${Math.hypot(dx, dy)}%`; line.style.transform = `rotate(${Math.atan2(dy, dx)}rad)`; line.style.background = widget.progress_color; plot.append(line); }); });
      node.append(plot);
      if (widget.trend_show_title !== false || widget.trend_show_current !== false) { const title = document.createElement("strong"); title.className = `trend-title align-${widget.text_align || "left"}`; title.style.fontSize = `${effectiveFontSize(widget) * state.zoom}px`; title.textContent = `${widget.trend_show_title !== false ? widget.text || "" : ""}${widget.trend_show_current !== false ? `${widget.trend_show_title !== false && widget.text ? " " : ""}--${widget.value_suffix || ""}` : ""}`; node.append(title); }
      if (widget.trend_show_y_axis !== false) { const unit = document.createElement("span"); unit.className = "trend-y-unit"; unit.style.color = axisColor; unit.textContent = widget.value_suffix ? `(${widget.value_suffix.replace(/[().]/g, "")})` : ""; node.append(unit); for (let tick = 0; tick < yTicks; tick++) { const label = document.createElement("span"); label.className = "trend-y-tick"; label.style.color = axisColor; label.style.top = `${(headerSpace + chartHeight * tick / Math.max(1, yTicks - 1)) * state.zoom}px`; const value = Number(widget.progress_max) - (Number(widget.progress_max) - Number(widget.progress_min)) * tick / Math.max(1, yTicks - 1); label.textContent = value.toFixed(Math.max(0, Math.min(3, Number(widget.value_decimals) || 0))); node.append(label); } }
      if (widget.trend_show_x_axis !== false) { const axis = document.createElement("div"); axis.className = "trend-x-axis"; Object.assign(axis.style, { left: `${chartX * state.zoom}px`, top: `${(headerSpace + chartHeight + 2) * state.zoom}px`, width: `${chartWidth * state.zoom}px`, color: axisColor }); const ticks = widget.trend_x_ticks || 5, minutes = widget.trend_time_range_minutes || 120, now = new Date(), exact = widget.trend_time_labels === "exact"; if (exact) { const rangeMs = minutes * 60000, oldest = now.getTime() - rangeMs; for (let tick = 0; tick < ticks - 1; tick++) { const ratio = tick / Math.max(1, ticks - 1), time = new Date(oldest + ratio * rangeMs), label = document.createElement("span"), shortRange = minutes < 180, value = shortRange ? time.getMinutes() : minutes < 2880 ? time.getHours() : time.getDate(), boundary = shortRange ? time.getMinutes() === 0 : minutes < 2880 ? time.getHours() === 0 : time.getDate() === 1; label.style.left = `${ratio * 100}%`; label.textContent = `${boundary ? "|" : ""}${String(value).padStart(2, "0")}`; axis.append(label); } } else { for (let tick = 0; tick < ticks - 1; tick++) { const label = document.createElement("span"), remaining = minutes * (ticks - 1 - tick) / Math.max(1, ticks - 1); label.style.left = `${tick * 100 / Math.max(1, ticks - 1)}%`; label.textContent = minutes >= 180 ? String(Math.round(remaining / 60)) : String(Math.round(remaining)); axis.append(label); } } node.append(axis); }
      if (widget.trend_caption) { const caption = document.createElement("span"); caption.className = "trend-caption"; caption.textContent = widget.trend_caption; node.append(caption); }
    } else if (["buttonmatrix", "table"].includes(widget.kind)) {
      node.classList.add("matrix-preview");
      if (widget.kind === "table") node.classList.add("table-preview");
      String(widget.control_options || "1|2|3\n4|5|6").split("\n").forEach((rowText) => { const row = document.createElement("span"); row.className = "matrix-row"; rowText.split("|").forEach((text) => { const cell = document.createElement("i"); cell.textContent = text; row.append(cell); }); node.append(row); });
    } else if (widget.kind === "msgbox") {
      node.classList.add("msgbox-preview"); const title = document.createElement("strong"); title.textContent = widget.text || "提示"; const body = document.createElement("span"); body.textContent = widget.control_text || "消息内容"; node.append(title, body);
    } else if (widget.kind === "image") {
      const image = document.createElement("img");
      image.src = assetUrl(widget.asset_path); image.alt = widget.text || "图片";
      image.style.objectFit = widget.image_fit === "cover" ? "cover" : widget.image_fit === "contain" ? "contain" : "fill";
      image.style.objectPosition = `${widget.image_offset_x}% ${widget.image_offset_y}%`;
      image.style.opacity = (widget.image_opacity ?? 100) / 100;
      image.style.filter = `grayscale(${widget.image_grayscale ?? 0}%) brightness(${widget.image_brightness ?? 100}%) blur(${widget.image_blur ?? 0}px)`;
      if ((widget.image_tint_opacity ?? 0) > 0) image.style.backgroundColor = colorWithOpacity(widget.image_tint, widget.image_tint_opacity);
      node.append(image);
    } else if (widget.content_asset_path) {
      const image = document.createElement("img");
      image.className = "content-image"; image.src = assetUrl(widget.content_asset_path);
      image.style.objectFit = widget.image_fit === "cover" ? "cover" : widget.image_fit === "contain" ? "contain" : "fill";
      image.style.objectPosition = `${widget.image_offset_x}% ${widget.image_offset_y}%`;
      image.style.opacity = (widget.image_opacity ?? 100) / 100;
      image.style.filter = `grayscale(${widget.image_grayscale ?? 0}%) brightness(${widget.image_brightness ?? 100}%) blur(${widget.image_blur ?? 0}px)`;
      node.append(image);
    }
    if (widget.binding_type === "state" && widget.state_mapping && !(widget.state_variants || []).length) {
      const active = widget.state_preview === "on";
      const useColor = ["color", "both"].includes(widget.state_visual || "color");
      const useDepth = ["depth", "both"].includes(widget.state_visual || "color");
      const stateColor = useColor ? (active ? widget.state_on_color : widget.state_off_color) : widget.background_color;
      const stateOpacity = widget.background_opacity ?? 100;
      node.style.backgroundColor = colorWithOpacity(stateColor, stateOpacity);
      if (widget.state_icon_enabled) node.style.color = active ? widget.state_on_color : widget.state_off_color;
      if (useDepth) {
        node.style.filter = "none";
        node.style.borderWidth = `${(active ? Math.max(4, widget.border_width) : widget.border_width) * state.zoom}px`;
        node.style.boxShadow = active ? `inset 0 -${3 * state.zoom}px 0 #0006, 0 ${2 * state.zoom}px ${6 * state.zoom}px #0008` : "inset 0 2px 4px #0007";
      }
    }
    const activeVariant = widget.state_style_enabled === false ? null : (widget.state_variants || []).find((item) => item.value === widget.state_preview);
    if (activeVariant) {
      node.style.backgroundColor = colorWithOpacity(activeVariant.background_color, widget.background_opacity ?? 100);
      node.style.color = activeVariant.text_color || widget.text_color;
      if (activeVariant.depth === "inset") {
        node.style.boxShadow = "none";
        node.style.filter = "none";
        node.style.transform = "none";
        for (const [edge, background] of [["top", "linear-gradient(to bottom, #000000ad 0, transparent 25%, transparent 100%)"], ["left", "linear-gradient(to right, #000000ad 0, transparent 25%, transparent 100%)"], ["bottom", "linear-gradient(to bottom, transparent 0, transparent 75%, #ffffff47 100%)"], ["right", "linear-gradient(to right, transparent 0, transparent 75%, #ffffff47 100%)"]]) {
          const bevel = document.createElement("i");
          bevel.className = `state-inset-edge state-inset-${edge}`;
          bevel.style.setProperty("--edge-inset", `${(widget.border_width || 0) * state.zoom}px`);
          bevel.style.setProperty("--edge-radius", `${Math.max(0, (widget.radius || 0) - (widget.border_width || 0)) * state.zoom}px`);
          bevel.style.background = background;
          node.append(bevel);
        }
      } else if (activeVariant.depth === "raised") {
        node.style.boxShadow = `inset 0 ${1 * state.zoom}px 0 #ffffff28, 0 ${4 * state.zoom}px ${9 * state.zoom}px #0009`;
        node.style.filter = "none";
        node.style.transform = "none";
      } else {
        node.style.boxShadow = "none"; node.style.filter = "none"; node.style.transform = "none";
      }
    }
    const fixedTitle = widget.show_fixed_title === false ? "" : String(widget.text || "").trim();
    const textualStatus = widget.binding && /(light_status|deng_guang_zhuang_tai)/i.test(widget.binding);
    const lightStatusPreview = ["off", "全关", "关闭"].includes(widget.state_preview) ? "全关" : "亮灯 3 盏";
    let displayText = widget.binding ? `${fixedTitle || ""}${fixedTitle ? " " : ""}${textualStatus ? lightStatusPreview : "--"}${widget.value_suffix ? ` ${widget.value_suffix}` : ""}` : fixedTitle;
    // Light-stat sensors expose a human-readable value (for example
    // "亮灯 3 盏"). Keep that dynamic value in the preview instead of
    // replacing it with the generic on/off variant label.
    if (widget.binding_type === "state" && widget.state_mapping && !textualStatus) {
      const stateLabel = activeVariant ? (activeVariant.label || "") : (widget.state_preview === "on" ? widget.state_on_text : widget.state_off_text);
      displayText = [fixedTitle, stateLabel].filter(Boolean).join(" ");
    }
    // A light-status sensor has a dynamic value. Use its explicit variant
    // label when configured; otherwise keep the readable sensor preview.
    if (textualStatus && activeVariant?.label) {
      displayText = [fixedTitle, activeVariant.label].filter(Boolean).join(" ");
    }
    if (["progress_circle", "progress_bar"].includes(widget.kind)) displayText = widget.binding ? `${fixedTitle ? `${fixedTitle} ` : ""}--${widget.value_suffix ? ` ${widget.value_suffix}` : ""}` : `${fixedTitle ? `${fixedTitle} ` : ""}${widget.show_value === "percent" ? `${Math.round(progressPercent(widget))}%` : `${widget.progress_value}${widget.value_suffix ? ` ${widget.value_suffix}` : ""}`}`;
    if (widget.kind === "battery") {
      displayText = widget.battery_display === "icon" ? "" : widget.battery_display === "percent" ? "--%" : "--%  --V  --A  --W  --h";
      const batteryIcon = document.createElement("span");
      batteryIcon.className = "battery-status-icon mdi-glyph";
      batteryIcon.textContent = "\u{F0079}";
      batteryIcon.style.color = widget.text_color;
      node.append(batteryIcon);
    }
    if (widget.kind === "icon") {
      const hasVariantIcon = activeVariant && Object.prototype.hasOwnProperty.call(activeVariant, "icon_glyph");
      const glyph = hasVariantIcon ? activeVariant.icon_glyph : (widget.state_icon_enabled && widget.state_style_enabled !== false ? (widget.state_preview === "on" ? widget.state_icon_on_glyph : widget.state_icon_off_glyph) : widget.show_fixed_icon !== false ? widget.icon_glyph || "" : "");
      const icon = document.createElement("span"); icon.className = "shape-accessory-icon mdi-glyph"; icon.textContent = glyph || "";
      Object.assign(icon.style, { fontSize: `${(activeVariant?.icon_size ?? widget.icon_size ?? 32) * state.zoom}px`, opacity: (widget.text_opacity ?? 100) / 100, color: activeVariant?.text_color || widget.text_color, transform: `translate(${(activeVariant?.icon_offset_x ?? widget.icon_offset_x ?? 0) * state.zoom}px, ${(activeVariant?.icon_offset_y ?? widget.icon_offset_y ?? 0) * state.zoom}px)` }); node.append(icon);
      const status = textualStatus ? "亮灯 3 盏" : (activeVariant?.label || ""); displayText = [fixedTitle, status].filter(Boolean).join(" ");
    }
    if (((widget.show_fixed_icon !== false && widget.icon_glyph) || activeVariant?.icon_glyph) && widget.kind !== "icon") {
      const accessory = document.createElement("span");
      accessory.className = "shape-accessory-icon mdi-glyph";
      const hasVariantIcon = activeVariant && Object.prototype.hasOwnProperty.call(activeVariant, "icon_glyph");
      accessory.textContent = hasVariantIcon ? activeVariant.icon_glyph : (widget.state_icon_enabled ? (widget.state_preview === "on" ? widget.state_icon_on_glyph : widget.state_icon_off_glyph) : (widget.show_fixed_icon !== false ? widget.icon_glyph : "")) || "";
      Object.assign(accessory.style, {
        fontSize: `${(hasVariantIcon ? (activeVariant.icon_size ?? widget.icon_size ?? 32) : (widget.icon_size || 32)) * state.zoom}px`,
        color: activeVariant?.text_color || widget.text_color,
        opacity: (widget.text_opacity ?? 100) / 100,
        transform: `translate(${(hasVariantIcon ? (activeVariant.icon_offset_x ?? 0) : (widget.icon_offset_x || 0)) * state.zoom}px, ${(hasVariantIcon ? (activeVariant.icon_offset_y ?? 0) : (widget.icon_offset_y || 0)) * state.zoom}px)`,
      });
      node.append(accessory);
    }
    if (["tabview", "tileview"].includes(widget.kind)) {
      const badge = document.createElement("span"); badge.className = "view-preview-badge";
      if (widget.kind === "tabview") { const names = String(widget.view_items || "标签一").split("\n").filter(Boolean); badge.textContent = `预览：${names[widget.view_preview_index || 0] || `标签 ${widget.view_preview_index || 0}`}`; }
      else badge.textContent = `预览磁贴：${widget.view_preview_row || 0}, ${widget.view_preview_column || 0}`;
      node.append(badge);
    }
        if (!(widget.kind === "shape" && widget.shape_type === "line") && !["slider", "switch", "checkbox", "dropdown", "roller", "spinbox", "led", "qrcode", "textarea", "keyboard", "trend_chart", "buttonmatrix", "table", "msgbox"].includes(widget.kind)) {
      appendEditableText(node, widget, displayText);
    }

    if (widget.id === state.selectedId && state.selectedIds.length === 1) {
            const handle = document.createElement("span"); handle.className = "resize-handle";
      if (widget.kind === "shape" && widget.shape_type === "line") {
        const radians = widget.line_angle * Math.PI / 180;
        const dx = Math.cos(radians) * widget.line_length * state.zoom, dy = Math.sin(radians) * widget.line_length * state.zoom;
        handle.classList.add("vector-handle");
        Object.assign(handle.style, { left: `${Math.max(0, -dx) + dx}px`, top: `${Math.max(0, -dy) + dy}px`, right: "auto", bottom: "auto" });
      }
      node.append(handle);

    }
    node.addEventListener("pointerdown", beginPointerAction);
    screen.append(node);
  }
  const grouped = selectedWidgets();
  if (grouped.length > 1 && grouped.every((widget) => widget.group_id && widget.group_id === grouped[0].group_id)) {
    const left = Math.min(...grouped.map((widget) => widget.x));
    const top = Math.min(...grouped.map((widget) => widget.y));
    const right = Math.max(...grouped.map((widget) => widget.x + widget.width));
    const bottom = Math.max(...grouped.map((widget) => widget.y + widget.height));
    const box = document.createElement("div");
    box.className = "group-selection-box";
    Object.assign(box.style, { left: `${left * state.zoom}px`, top: `${top * state.zoom}px`, width: `${(right - left) * state.zoom}px`, height: `${(bottom - top) * state.zoom}px` });
    const handle = document.createElement("span"); handle.className = "group-resize-handle";
    handle.addEventListener("pointerdown", beginGroupResize); box.append(handle);
    screen.append(box);
  }
  const selected = selectedWidget();
  const estimateAsset = (path, widget) => path ? widget.width * widget.height * (/\.(png|webp)$/i.test(path) ? 3 : 2) : 0;
  const imageBytes = state.project.widgets.reduce((total, widget) => total + estimateAsset(widget.asset_path, widget) + estimateAsset(widget.content_asset_path, widget), 0);
  const mediaLabel = `图片约 ${(imageBytes / 1048576).toFixed(1)} MB${imageBytes > 6 * 1048576 ? "，建议减少" : ""}`;
  $("#selectionInfo").textContent = state.selectedIds.length > 1 ? `已选择 ${state.selectedIds.length} 个组件` : selected ? `${selected.text || "组件"} · ${selected.x}, ${selected.y} · ${selected.width} × ${selected.height}` : mediaLabel;
  $("#deleteBtn").disabled = !selected;
  $("#copyBtn").disabled = !selected;
  $("#pasteBtn").disabled = !state.componentClipboard;
  $("#copyStyleBtn").disabled = !selected;
  $("#pasteStyleBtn").disabled = !selected || !state.styleClipboard;
  $("#lockBtn").disabled = !selected;
  $("#hideBtn").disabled = !selected;
  $("#groupBtn").disabled = state.selectedIds.length < 2;
  $("#ungroupBtn").disabled = !selectedWidgets().some((widget) => widget.group_id);
  $("#lockBtn").textContent = selected?.locked ? "解锁" : "锁定";
  $("#hideBtn").textContent = selected?.hidden ? "显示" : "隐藏";
  renderLayerTree();
}

function beginPointerAction(event) {
  event.preventDefault();
  const id = event.currentTarget.dataset.id;
  const resizing = event.target.classList.contains("resize-handle");
  const wasSelected = state.selectedIds.includes(id);
  if (!wasSelected || event.ctrlKey || event.metaKey) selectWidget(id, event.ctrlKey || event.metaKey);
  state.selectedId = id;
  const widget = state.project.widgets.find((item) => item.id === id);
  if (widget.locked) { toast("组件已锁定"); return; }
        state.pointer = { id, resizing, wasSelected, moved: false, x: event.clientX, y: event.clientY, wx: widget.x, wy: widget.y, width: widget.width, height: widget.height, lineLength: widget.line_length, lineAngle: widget.line_angle, positions: Object.fromEntries(selectedWidgets().map((item) => [item.id, { x: item.x, y: item.y }])), historySnapshot: cloneProject() };


}

function beginGroupResize(event) {
  event.preventDefault(); event.stopPropagation();
  const items = selectedWidgets(); if (items.length < 2) return;
  const left = Math.min(...items.map((item) => item.x)), top = Math.min(...items.map((item) => item.y));
  const right = Math.max(...items.map((item) => item.x + item.width)), bottom = Math.max(...items.map((item) => item.y + item.height));
  state.pointer = { id: state.selectedId, resizing: true, groupResizing: true, moved: false, x: event.clientX, y: event.clientY,
    bounds: { left, top, width: right - left, height: bottom - top },
    geometries: Object.fromEntries(items.map((item) => [item.id, { x: item.x, y: item.y, width: item.width, height: item.height, font_size: item.font_size, icon_size: item.icon_size, border_width: item.border_width, radius: item.radius, line_length: item.line_length }])), historySnapshot: cloneProject() };
}

function movePointer(event) {
  if (state.marquee) {
    const rect = $("#screen").getBoundingClientRect(), x = (event.clientX - rect.left) / state.zoom, y = (event.clientY - rect.top) / state.zoom;
    const left = Math.max(0, Math.min(state.marquee.x, x)), top = Math.max(0, Math.min(state.marquee.y, y));
    const right = Math.min(800, Math.max(state.marquee.x, x)), bottom = Math.min(480, Math.max(state.marquee.y, y));
    Object.assign(state.marquee.node.style, { left: `${left * state.zoom}px`, top: `${top * state.zoom}px`, width: `${(right - left) * state.zoom}px`, height: `${(bottom - top) * state.zoom}px` });
    Object.assign(state.marquee, { left, top, right, bottom }); return;
  }
  if (!state.pointer) return;
  const widget = selectedWidget();
  if (!widget || widget.id !== state.pointer.id) return;
  const dx = (event.clientX - state.pointer.x) / state.zoom;
  const dy = (event.clientY - state.pointer.y) / state.zoom;
  state.pointer.moved ||= Math.abs(dx) + Math.abs(dy) > 2;
  if (state.pointer.groupResizing) {
    const bounds = state.pointer.bounds;
    const scaleX = Math.max(20, bounds.width + dx) / bounds.width, scaleY = Math.max(20, bounds.height + dy) / bounds.height;
    const contentScale = Math.max(0.2, Math.min(scaleX, scaleY));
    for (const item of selectedWidgets()) {
      const origin = state.pointer.geometries[item.id]; if (!origin) continue;
      item.x = Math.round(bounds.left + (origin.x - bounds.left) * scaleX); item.y = Math.round(bounds.top + (origin.y - bounds.top) * scaleY);
      item.width = Math.max(20, Math.round(origin.width * scaleX)); item.height = Math.max(20, Math.round(origin.height * scaleY));
      item.font_size = Math.max(8, Math.min(96, Math.round(origin.font_size * contentScale)));
      item.icon_size = Math.max(8, Math.min(192, Math.round(origin.icon_size * contentScale)));
      item.border_width = Math.max(0, Math.min(24, Math.round(origin.border_width * contentScale)));
      item.radius = Math.max(0, Math.min(200, Math.round(origin.radius * contentScale)));
      if (item.kind === "shape" && ["ellipse", "circle"].includes(item.shape_type)) { item.ellipse_radius_x = Math.round(item.width / 2); item.ellipse_radius_y = item.shape_type === "circle" ? item.ellipse_radius_x : Math.round(item.height / 2); }
      if (item.kind === "shape" && item.shape_type === "line") item.line_length = Math.max(10, Math.round(origin.line_length * contentScale));
      clamp(item);
    }
  } else if (state.pointer.resizing) {
    const nextWidth = Math.round(state.pointer.width + dx), nextHeight = Math.round(state.pointer.height + dy);
    if (widget.kind === "shape" && ["ellipse", "circle"].includes(widget.shape_type)) {
      widget.ellipse_radius_x = Math.max(10, Math.round(nextWidth / 2));
      widget.ellipse_radius_y = widget.shape_type === "circle" ? widget.ellipse_radius_x : Math.max(10, Math.round(nextHeight / 2));
        } else if (widget.kind === "shape" && widget.shape_type === "line") {
      const radians = state.pointer.lineAngle * Math.PI / 180;
      const vectorX = Math.cos(radians) * state.pointer.lineLength + dx;
      const vectorY = Math.sin(radians) * state.pointer.lineLength + dy;
      widget.line_length = Math.max(10, Math.round(Math.hypot(vectorX, vectorY)));
      widget.line_angle = Math.round(Math.atan2(vectorY, vectorX) * 180 / Math.PI);

    } else {
      widget.width = nextWidth; widget.height = nextHeight;
    }
  } else {
    for (const item of selectedWidgets()) {
      const origin = state.pointer.positions[item.id] || { x: item.x, y: item.y };
      item.x = Math.round((origin.x + dx) / 10) * 10;
      item.y = Math.round((origin.y + dy) / 10) * 10;
      clamp(item);
    }
  }
  clamp(widget);
    if (widget.kind === "shape" && widget.shape_type === "line" && state.pointer.resizing) renderCanvas();
  else {
    for (const item of selectedWidgets()) {
      const node = $(`.canvas-widget[data-id="${item.id}"]`);
      const position = canvasGeometry(item);
      if (node) Object.assign(node.style, { left: `${position.x * state.zoom}px`, top: `${position.y * state.zoom}px`, width: `${position.width * state.zoom}px`, height: `${position.height * state.zoom}px` });
    }
    const groupBox = $(".group-selection-box");
    if (groupBox && selectedWidgets().length > 1) {
      const items = selectedWidgets(), left = Math.min(...items.map((item) => item.x)), top = Math.min(...items.map((item) => item.y));
      const right = Math.max(...items.map((item) => item.x + item.width)), bottom = Math.max(...items.map((item) => item.y + item.height));
      Object.assign(groupBox.style, { left: `${left * state.zoom}px`, top: `${top * state.zoom}px`, width: `${(right - left) * state.zoom}px`, height: `${(bottom - top) * state.zoom}px` });
    }
  }
  fillWidgetForm(); markDirty();
}

function endPointer() {
  if (state.marquee) {
    const box = state.marquee; state.marquee = null; box.node.remove();
    const selected = state.project.widgets.filter((widget) => !widget.hidden && widgetOnPage(widget, state.activePageId) && widget.x < box.right && widget.x + widget.width > box.left && widget.y < box.bottom && widget.y + widget.height > box.top);
    if (selected.length) { selectWidget(selected.at(-1).id); state.selectedIds = selected.map((widget) => widget.id); state.selectedId = state.selectedIds.at(-1); renderCanvas(); }
    else selectWidget(null);
    return;
  }
  if (!state.pointer) return;
  const pointer = state.pointer;
  const widget = selectedWidget();
  state.pointer = null;
  if (!pointer.moved && pointer.wasSelected && widget?.kind === "page_button") {
    switchPage(widget.target_page);
    } else {
    renderCanvas();
  }
  recordHistory(pointer.historySnapshot);
  saveProject();

}

function selectWidget(id, additive = false) {
  if (!id) state.selectedIds = [];
  else if (additive) state.selectedIds = state.selectedIds.includes(id) ? state.selectedIds.filter((item) => item !== id) : [...state.selectedIds, id];
  else {
    const widget = state.project.widgets.find((item) => item.id === id);
    state.selectedIds = widget?.group_id ? state.project.widgets.filter((item) => item.group_id === widget.group_id).map((item) => item.id) : [id];
  }
  state.selectedId = id && state.selectedIds.includes(id) ? id : state.selectedIds.at(-1) || null;
  const widget = selectedWidget();
  $("#projectForm").classList.toggle("hidden", Boolean(widget));
  $("#widgetForm").classList.toggle("hidden", !widget);
  $("#inspectorTitle").textContent = widget ? (widget.text || "图片组件") : "项目设置";
  $("#kindBadge").textContent = widget ? widget.kind.toUpperCase() : "PROJECT";
  if (widget) fillWidgetForm();
  renderCanvas();
}

function fillWidgetForm() {
  const widget = selectedWidget();
  if (!widget) return;
  ensureInspectorArchitecture(widget);
  renderStateAppearanceEditor(widget);
  renderPageTabs();
  $$('[data-widget]').forEach((input) => { input.value = widget[input.dataset.widget] ?? ""; });
  [...$("#widgetPage").options].forEach((option) => { option.selected = widgetPages(widget).includes(option.value); });
  $$('[data-widget-number]').forEach((input) => { input.value = widget[input.dataset.widgetNumber] ?? 0; });
  const image = widget.kind === "image";
  const shape = widget.kind === "shape";
  const progress = ["progress_circle", "progress_bar", "trend_chart"].includes(widget.kind);
  const battery = widget.kind === "battery";
  const nativeControl = ["slider", "switch", "checkbox", "dropdown", "roller", "spinbox", "spinner", "led", "qrcode", "textarea", "keyboard", "buttonmatrix", "table"].includes(widget.kind);
  const container = widget.kind === "container";
  const pagedContainer = ["tabview", "tileview"].includes(widget.kind);
  const textStyleKinds = ["label", "button", "page_button", "icon", "shape", "progress_circle", "progress_bar", "trend_chart", "battery", "checkbox", "msgbox", "textarea", "dropdown", "roller", "spinbox", "buttonmatrix", "table"];
  const topLayerExcluded = ["shape", "image", "container", "tabview", "tileview", "trend_chart", "buttonmatrix", "table", "keyboard", "textarea", "msgbox"];
  const usesTopLayer = state.project.pages.length > 1 && !widget.parent_id && !topLayerExcluded.includes(widget.kind) && widgetPages(widget).length === state.project.pages.length && widget.width * widget.height <= 800 * 480 * 0.35;
  $("#sharedLayerHint").classList.toggle("hidden", widgetPages(widget).length < 2);
  $("#sharedLayerHint").textContent = usesTopLayer ? "公共层优化：此组件覆盖全部页面，烧录时只创建一个LVGL对象。" : "跨页面组件：烧录时复用数据订阅和素材，各页面保留独立显示实例。";
  const contentKinds = ["label", "button", "page_button", "shape", "icon", "progress_circle", "progress_bar", "trend_chart", "battery", "slider", "switch", "checkbox", "dropdown", "roller", "spinbox", "msgbox", "textarea"];
  const bindingKinds = ["label", "button", "shape", "icon", "progress_circle", "progress_bar", "trend_chart", "battery", "slider", "switch", "checkbox", "dropdown", "roller", "spinbox"];
  const fixedBindingKinds = ["icon", "slider", "switch", "checkbox", "dropdown", "roller", "spinbox"];
  $("#contentSection").classList.toggle("hidden", !contentKinds.includes(widget.kind));
  $("#containerLayoutSection").classList.toggle("hidden", !container);
  $("#containerScrollRows").classList.toggle("hidden", !container || !widget.container_scrollable);
  $("#flexFlowRow").classList.toggle("hidden", !container || widget.layout_type !== "flex");
  $("#gridSizeRow").classList.toggle("hidden", !container || widget.layout_type !== "grid");
  const parentWidget = state.project.widgets.find((item) => item.id === widget.parent_id);
  $("#gridCellSection").classList.toggle("hidden", parentWidget?.layout_type !== "grid" && parentWidget?.kind !== "tileview");
  $("#viewLayoutSection").classList.toggle("hidden", !pagedContainer);
  $("#viewItemsRow").classList.toggle("hidden", widget.kind !== "tabview");
  $("#viewChildSection").classList.toggle("hidden", parentWidget?.kind !== "tabview" && parentWidget?.kind !== "tileview");
  const isTab = widget.kind === "tabview", isTile = widget.kind === "tileview", tabParent = parentWidget?.kind === "tabview", tileParent = parentWidget?.kind === "tileview";
  $("#tileSizeRows").classList.toggle("hidden", !isTile); $("#tabPreviewRow").classList.toggle("hidden", !isTab); $("#tilePreviewRows").classList.toggle("hidden", !isTile);
  $("#tabChildIndexRow").classList.toggle("hidden", !tabParent); $("#tileChildHint").classList.toggle("hidden", !tileParent);
  $("#gridCellTitle").textContent = tileParent ? "磁贴归属" : "Grid单元格";
  $("#gridRowLabel").childNodes[0].textContent = tileParent ? "所属磁贴行" : "行位置"; $("#gridColumnLabel").childNodes[0].textContent = tileParent ? "所属磁贴列" : "列位置";
  $("#gridRowSpanLabel").classList.toggle("hidden", tileParent); $("#gridColumnSpanLabel").classList.toggle("hidden", tileParent);
  if (isTab) { const tabs = String(widget.view_items || "标签一").split("\n").filter(Boolean); $("#tabPreviewSelect").innerHTML = tabs.map((name, index) => `<option value="${index}">${index} · ${name}</option>`).join(""); $("#tabPreviewSelect").value = widget.view_preview_index || 0; }
  if (tabParent) { const tabs = String(parentWidget.view_items || "标签一").split("\n").filter(Boolean); $("#tabChildIndexSelect").innerHTML = tabs.map((name, index) => `<option value="${index}">${index} · ${name}</option>`).join(""); $("#tabChildIndexSelect").value = widget.view_index || 0; }
  const parentOptions = state.project.widgets.filter((item) => ["container", "tabview", "tileview"].includes(item.kind) && item.id !== widget.id).map((item) => `<option value="${item.id}">${item.text || "布局容器"}</option>`).join("");
  $("#parentContainer").innerHTML = `<option value="">无（页面根级）</option>${parentOptions}`; $("#parentContainer").value = widget.parent_id || "";
  const canLoadImage = shape || ["label", "button", "page_button"].includes(widget.kind);
  $("#assetRow").classList.toggle("hidden", !image);
  $("#contentAssetRow").classList.toggle("hidden", !canLoadImage);
  $("#assetContentSection").classList.toggle("hidden", !image && !canLoadImage);
  $("#removeContentImage").disabled = !widget.content_asset_path;
  $("#textRow").classList.toggle("hidden", (shape && widget.shape_type === "line") || battery || widget.kind === "slider");
  $("#textRow").childNodes[0].textContent = widget.kind === "icon" ? "名称" : "文字";

  $("#bindingRow").classList.toggle("hidden", !bindingKinds.includes(widget.kind));
  $("#bindingRow").childNodes[0].textContent = widget.kind === "trend_chart" ? "趋势数值实体" : "绑定实体";
  $("#bindingTypeRow").classList.toggle("hidden", !bindingKinds.includes(widget.kind) || progress || fixedBindingKinds.includes(widget.kind));
  $("#valueFormatRow").classList.toggle("hidden", !bindingKinds.includes(widget.kind) || widget.binding_type === "state");
  $("#stateMapSection").classList.toggle("hidden", widget.binding_type !== "state" || widget.kind === "page_button" || ["switch", "checkbox", "dropdown", "roller"].includes(widget.kind));
  const stateHint = $("#stateMapSection").querySelector(".numeric-state-hint");
  if (stateHint) stateHint.textContent = widget.binding_type === "state" && widget.binding?.startsWith("sensor.") ? "传感器状态也可以按文字或数值判断：例如状态值为 0 时表示全关，设为内凹；其他值表示有灯亮，设为凸起。" : "开启状态值匹配后，可为不同状态设置颜色、图标和凹凸效果。";
  const stateValueLabel = $("#stateOnValueLabel");
  if (stateValueLabel) stateValueLabel.textContent = widget.binding?.startsWith("sensor.") ? "内凹状态值" : "开启状态值";
  const supportsStateIcon = ["icon", "shape", "button", "page_button", "progress_circle", "progress_bar"].includes(widget.kind);
  $("#stateIconRows").classList.toggle("hidden", !supportsStateIcon);
  $("#stateIconNames").textContent = `开启：${widget.state_icon_on_name || "未选择"}；关闭：${widget.state_icon_off_name || "未选择"}`;
  $("#targetPageRow").classList.toggle("hidden", widget.kind !== "page_button" && !["page", "msgbox"].includes(widget.tap_mode));
  if (widget.tap_mode === "msgbox") $('[data-widget="target_page"]').innerHTML = state.project.widgets.filter((item) => item.kind === "msgbox").map((item) => `<option value="${item.id}">${item.text || "消息框"}</option>`).join("");
  else $('[data-widget="target_page"]').innerHTML = state.project.pages.map((page) => `<option value="${page.id}">${page.name}</option>`).join("");
  $('[data-widget="target_page"]').value = widget.target_page || "";
  $("#imageSection").classList.toggle("hidden", !image && !widget.content_asset_path);
  $("#geometrySection").classList.toggle("hidden", !shape);
  $("#ellipseGeometry").classList.toggle("hidden", !shape || !["ellipse", "circle"].includes(widget.shape_type));
  $("#lineGeometry").classList.toggle("hidden", !shape || widget.shape_type !== "line");
  $("#progressSection").classList.toggle("hidden", !progress);
  $("#progressSectionTitle").textContent = widget.kind === "trend_chart" ? "曲线与坐标" : "数值与进度";
  $("#showValueRow").classList.toggle("hidden", widget.kind === "trend_chart");
  $("#progressPreviewRow").classList.toggle("hidden", widget.kind === "trend_chart");
  $("#progressColorRow").childNodes[0].textContent = widget.kind === "trend_chart" ? "曲线颜色" : "进度颜色";
  $("#trendModeRow").classList.toggle("hidden", widget.kind !== "trend_chart");
  $("#trendDetailRows").classList.toggle("hidden", widget.kind !== "trend_chart");
  $("#trendModeHint").classList.toggle("hidden", widget.kind !== "trend_chart");
  $("#nativeControlSection").classList.toggle("hidden", !nativeControl);
  $("#matrixButtonSection").classList.toggle("hidden", widget.kind !== "buttonmatrix");
  $("#controlRangeRow").classList.toggle("hidden", widget.kind !== "slider");
  $("#controlCheckedRow").classList.toggle("hidden", !["switch", "checkbox"].includes(widget.kind));
  $("#controlOptionsRow").classList.toggle("hidden", !["dropdown", "roller", "buttonmatrix", "table"].includes(widget.kind));
  $("#controlSelectedRow").classList.toggle("hidden", !["dropdown", "roller"].includes(widget.kind));
  $("#controlTextRow").classList.toggle("hidden", !["qrcode", "textarea", "msgbox"].includes(widget.kind));
  $("#controlDetailRow").classList.toggle("hidden", !["roller", "spinbox"].includes(widget.kind));
  $("#batterySection").classList.toggle("hidden", !battery);
  $("#styleSection").classList.toggle("hidden", !textStyleKinds.includes(widget.kind));
  $("#autoFitTextRow").classList.toggle("hidden", widget.kind === "trend_chart");
  $("#textOffsetRow").classList.toggle("hidden", widget.kind === "trend_chart");
  $("#forceCenterBtn").classList.toggle("hidden", widget.kind === "trend_chart");
  const lineShape = shape && widget.shape_type === "line";
  $("#fillColorRow").classList.toggle("hidden", lineShape);
  $("#backgroundOpacityRow").classList.toggle("hidden", lineShape);
  $("#backgroundOpacityRow").childNodes[0].textContent = "背景透明度（所有状态共用）";
  $("#radiusRow").classList.toggle("hidden", lineShape || ["spinner", "led", "qrcode"].includes(widget.kind));
  $("#borderColorRow").classList.toggle("hidden", ["spinner", "led"].includes(widget.kind));
  $("#borderOpacityRow").classList.toggle("hidden", ["spinner", "led"].includes(widget.kind));
  $("#borderWidthRow").classList.toggle("hidden", ["spinner", "led"].includes(widget.kind));

  $("#clickEffectRow").classList.toggle("hidden", !["button", "page_button", "shape", "icon"].includes(widget.kind));
  $("#actionSection").classList.toggle("hidden", !["button", "page_button", "shape", "icon"].includes(widget.kind));
  $("#effectiveFontHint").textContent = `设置字号 ${widget.font_size}px，预计真机字号 ${effectiveFontSize(widget)}px`;
  const supportsAccessoryIcon = ["shape", "button", "page_button", "progress_circle", "progress_bar"].includes(widget.kind);
  $("#shapeIconSection").classList.toggle("hidden", !supportsAccessoryIcon);
  $("#shapeIconName").textContent = widget.icon_glyph ? `当前图标：${widget.icon_name || "自定义图标"}` : "当前未插入图标";
  $("#removeShapeIcon").disabled = !widget.icon_glyph;
  const haAction = widget.tap_mode === "ha" || widget.kind === "button";
  $("#haActionRow").classList.toggle("hidden", !haAction);
  $("#haEntityRow").classList.toggle("hidden", !haAction);
  $("#haValueRow").classList.toggle("hidden", !haAction);
  if (image) $("#assetPreview").src = assetUrl(widget.asset_path);
  if (widget.kind === "buttonmatrix") renderMatrixButtonEditor(widget);
  renderStateAppearanceEditor(widget);
  syncRangeValues();
  setInspectorMode($("#inspectorModeTabs button.active")?.dataset.inspectorMode || "visual");
}

const HA_ENTITY_ACTIONS = {
  none: [],
  switch: [["toggle", "切换"], ["turn_on", "开启"], ["turn_off", "关闭"]],
  light: [["toggle", "切换"], ["turn_on", "开启"], ["turn_off", "关闭"], ["turn_on_brightness", "设置亮度"]],
  climate: [["toggle", "切换"], ["turn_on", "开启"], ["turn_off", "关闭"], ["set_temperature", "设置温度"], ["set_hvac_mode", "设置运行模式"]],
  cover: [["toggle", "切换"], ["open_cover", "打开"], ["close_cover", "关闭"], ["stop_cover", "停止"], ["set_cover_position", "设置位置"]],
  lock: [["lock", "上锁"], ["unlock", "解锁"]],
  scene: [["turn_on", "执行场景"]], script: [["turn_on", "执行"], ["turn_off", "停止"], ["toggle", "切换"]],
  input_boolean: [["toggle", "切换"], ["turn_on", "开启"], ["turn_off", "关闭"]],
  input_number: [["set_value", "设为指定数值"], ["increment", "增加一个步长"], ["decrement", "减少一个步长"]],
  number: [["set_value", "设为指定数值"]],
  input_select: [["select_option", "选择选项"]], select: [["select_option", "选择选项"]], device: [],
  sensor: [], binary_sensor: []
};

function ensureInspectorArchitecture(widget) {
  let tabs = $("#inspectorModeTabs");
  if (!tabs) {
    tabs = document.createElement("div"); tabs.id = "inspectorModeTabs"; tabs.className = "inspector-mode-tabs";
    tabs.innerHTML = '<button type="button" data-inspector-mode="visual" class="active">基础控制</button><button type="button" data-inspector-mode="ha">HA 功能控制</button>';
    $("#widgetForm").prepend(tabs);
    tabs.addEventListener("click", (event) => { const button = event.target.closest("button"); if (button) setInspectorMode(button.dataset.inspectorMode); });
    const ha = document.createElement("section"); ha.id = "haControlPanel"; ha.className = "form-section inspector-group inspector-binding hidden";
    ha.innerHTML = '<div id="haFunctionSection" class="ha-subgroup"><h2 class="ha-control-heading">HA 基础控制<button type="button" id="toggleHaControl" aria-label="展开或收起 HA 基础控制">⌃</button></h2><div id="haControlBody"><label>实体类型<select id="haEntityDomain"><option value="none">无（仅外观）</option><option value="switch">开关</option><option value="light">灯光</option><option value="climate">空调</option><option value="cover">窗帘</option><option value="lock">门锁</option><option value="scene">场景</option><option value="script">脚本</option><option value="input_boolean">布尔助手</option><option value="sensor">传感器</option><option value="binary_sensor">二元传感器</option></select></label><label id="haEntityIdRow">显示数据的实体 ID<input id="haEntityId" placeholder="climate.living_room"></label><label id="haPrimaryActionRow">点击操作<select id="haPrimaryAction"></select></label><div id="haActionParameterRow" class="hidden"><label id="haActionParameterLabel">操作参数<input id="haActionParameter"></label></div><div id="haSensorFormatRow" class="field-grid hidden"><label>单位<input id="haSensorUnit"></label><label>小数位<input id="haSensorDecimals" type="number" min="0" max="3"></label></div><small id="haControlHint" class="field-hint"></small></div></div>';
    const sensorOption = ha.querySelector('#haEntityDomain option[value="sensor"]');
    sensorOption.textContent = "传感器";
    ha.querySelector('#haEntityDomain option[value="binary_sensor"]').textContent = "二元传感器";
    sensorOption.before(new Option("数值助手", "input_number"));
    sensorOption.before(new Option("数值实体", "number"), new Option("选项助手", "input_select"), new Option("选项实体", "select"), new Option("本机数据", "device"));
    tabs.after(ha);
    $("#toggleHaControl").addEventListener("click", () => {
      const group = $("#haFunctionSection");
      const collapsed = group.dataset.collapsed !== "true";
      group.dataset.collapsed = String(collapsed);
      $("#haControlBody").classList.toggle("hidden", collapsed);
      group.classList.toggle("ha-collapsed", collapsed);
      $("#toggleHaControl").textContent = collapsed ? "⌄" : "⌃";
    });
    const actionEntity = document.createElement("label"); actionEntity.id = "haActionEntityRow";
    actionEntity.innerHTML = '操作另一个实体（选填）<input id="haActionEntityId" placeholder="留空：操作上方实体">';
    $("#haPrimaryActionRow").before(actionEntity);
    const buttonName = document.createElement("label"); buttonName.id = "haButtonNameRow";
    buttonName.innerHTML = '按钮名称<input id="haButtonName" placeholder="例如：主卧关灯">';
    $("#haEntityIdRow").before(buttonName);
    const numberConfig = document.createElement("div"); numberConfig.id = "haNumberConfig"; numberConfig.className = "hidden";
    numberConfig.innerHTML = '<div class="field-grid"><label>最小值<input id="haNumberMin" type="number"></label><label>最大值<input id="haNumberMax" type="number"></label><label>单位<input id="haNumberUnit"></label><label>小数位<input id="haNumberDecimals" type="number" min="0" max="3"></label></div>';
    $("#haPrimaryActionRow").before(numberConfig);
    const sensorState = document.createElement("div"); sensorState.id = "haSensorStateConfig"; sensorState.className = "ha-subgroup hidden";
    sensorState.innerHTML = '<h2 class="ha-control-heading">传感器状态显示</h2><label>启用状态映射<select id="haSensorStateMapping"><option value="false">关闭</option><option value="true">启用</option></select></label><label id="haSensorClosedValueLabel">内凹状态值<input id="haSensorClosedValue" placeholder="例如：全关、关闭、空闲"></label><small class="field-hint">实体状态等于此文字时内凹；其他状态（例如“亮灯 1 盏”）外凸。下面的“HA 状态显示”可继续编辑每种状态的颜色、图标和深度。</small>';
    numberConfig.after(sensorState);
    const visualText = document.createElement("label"); visualText.id = "visualDisplayTextRow"; visualText.innerHTML = '固定标题<input id="visualDisplayText" placeholder="例如：卧室空调">';
    $("#styleSection h2").after(visualText);
    const visualBehavior = document.createElement("div"); visualBehavior.id = "visualBehaviorControls";
    visualBehavior.innerHTML = '<label>显示固定标题<select id="visualShowFixedTitle"><option value="true">显示</option><option value="false">隐藏（仅用于图层命名）</option></select></label><label>显示固定图标<select id="visualShowFixedIcon"><option value="true">显示</option><option value="false">隐藏</option></select></label><div class="field-grid"><label>按压反馈<select id="visualClickEffect"><option value="none">无反馈</option><option value="scale">按压缩放</option><option value="darken">按压变暗</option><option value="highlight">高亮描边</option></select></label><label>状态外观联动<select id="visualStateLink"><option value="true">跟随 HA 状态</option><option value="false">使用固定外观</option></select></label></div>';
    visualText.after(visualBehavior);
    const numberAppearance = document.createElement("label"); numberAppearance.id = "numberAppearanceRow"; numberAppearance.className = "hidden";
    numberAppearance.innerHTML = '数值外观<select id="numberAppearanceMode"><option value="number">只显示数值（无加减按钮）</option><option value="slider">滑块</option><option value="slider_value">滑块和数值</option></select>';
    visualBehavior.after(numberAppearance);
    $("#visualClickEffect").addEventListener("change", (event) => { const current = selectedWidget(); if (!current) return; current.click_effect = event.target.value; renderCanvas(); markDirty(); saveProject(); });
    $("#visualShowFixedTitle").addEventListener("change", (event) => { const current = selectedWidget(); if (!current) return; current.show_fixed_title = event.target.value === "true"; renderCanvas(); markDirty(); saveProject(); });
    $("#visualShowFixedIcon").addEventListener("change", (event) => { const current = selectedWidget(); if (!current) return; current.show_fixed_icon = event.target.value === "true"; renderCanvas(); markDirty(); saveProject(); });
    $("#visualStateLink").addEventListener("change", (event) => { const current = selectedWidget(); if (!current) return; current.state_style_enabled = event.target.value === "true"; renderStateAppearanceEditor(current); renderCanvas(); markDirty(); saveProject(); });
    $("#numberAppearanceMode").addEventListener("change", applyNumberAppearance);
    for (const id of ["haNumberMin", "haNumberMax", "haNumberUnit", "haNumberDecimals"]) $("#" + id).addEventListener("input", applyHaPreset);
    $("#haEntityDomain").addEventListener("change", applyHaPreset);
    $("#haEntityId").addEventListener("input", applyHaPreset);
    $("#haActionEntityId").addEventListener("input", applyHaPreset);
    $("#haButtonName").addEventListener("input", (event) => { const current = selectedWidget(); if (!current) return; current.ha_button_name = event.target.value; markDirty(); saveProject(); });
    $("#haPrimaryAction").addEventListener("change", applyHaPreset);
    $("#haActionParameter").addEventListener("input", applyHaPreset);
    const sensorType = document.createElement("label");
    sensorType.innerHTML = '传感器显示内容<select id="haSensorType"><option value="number">数值</option><option value="state">文字状态</option></select>';
    $("#haSensorFormatRow").prepend(sensorType); $("#haSensorType").addEventListener("change", applyHaPreset);
    $("#haSensorUnit").addEventListener("input", applyHaPreset); $("#haSensorDecimals").addEventListener("input", applyHaPreset);
    $("#haSensorStateMapping").addEventListener("change", (event) => { const current = selectedWidget(); if (!current) return; const before = cloneProject(); current.state_mapping = event.target.value === "true"; if (current.state_mapping) { current.binding_type = "state"; current.ha_state_profile = "sensor:custom"; current.state_on_value ||= "全关"; current.state_preview = "off"; current.state_variants = current.state_variants?.length ? current.state_variants : [{ value: "off", label: "关闭", depth: "inset", background_color: current.state_off_color || "#3B424C", text_color: current.text_color }, { value: "on", label: "其他", depth: "raised", background_color: current.state_on_color || "#247A4D", text_color: current.text_color }]; } renderHaActions(current); renderStateAppearanceEditor(current); recordHistory(before); renderCanvas(); markDirty(); saveProject(); });
    $("#haSensorClosedValue").addEventListener("input", (event) => { const current = selectedWidget(); if (!current) return; const before = cloneProject(); current.state_on_value = event.target.value; current.state_mapping = true; current.binding_type = "state"; current.ha_state_profile = "sensor:custom"; renderStateAppearanceEditor(current); recordHistory(before); renderCanvas(); markDirty(); saveProject(); });
    $("#visualDisplayText").addEventListener("input", (event) => { const current = selectedWidget(); if (!current) return; current.text = event.target.value; renderCanvas(); markDirty(); saveProject(); });
  }
  const domain = widget.binding?.startsWith("device:") ? "device" : (!widget.binding && !widget.action_entity) ? "none" : (widget.binding || widget.action_entity || "").split(".")[0];
  $("#haEntityDomain").value = Object.hasOwn(HA_ENTITY_ACTIONS, domain) ? domain : "none";
  $("#haEntityId").value = widget.binding || "";
  if ($("#haActionEntityId")) $("#haActionEntityId").value = widget.action_entity === widget.binding ? "" : (widget.action_entity || "");
  if ($("#haButtonName")) $("#haButtonName").value = widget.ha_button_name || "";
  $("#visualDisplayText").value = widget.text || "";
  $("#visualClickEffect").value = widget.click_effect || "none";
  $("#visualShowFixedTitle").value = String(widget.show_fixed_title !== false);
  $("#visualShowFixedIcon").value = String(widget.show_fixed_icon !== false);
  $("#visualStateLink").value = String(widget.state_style_enabled !== false);
  const numberHelper = ["input_number", "number"].includes($("#haEntityDomain").value);
  $("#numberAppearanceRow").classList.toggle("hidden", !numberHelper);
  if ($("#haNumberConfig").firstElementChild !== $("#numberAppearanceRow")) $("#haNumberConfig").prepend($("#numberAppearanceRow"));
  $("#numberAppearanceMode").value = widget.ha_visual_mode || (widget.kind === "slider" ? "slider" : "number");
  $("#haSensorType").value = widget.binding_type || "number";
  if ($("#haSensorStateMapping")) { $("#haSensorStateMapping").value = String(Boolean(widget.state_mapping)); $("#haSensorClosedValue").value = widget.state_on_value || ""; }
  const switchSelect = $("#pageSwitchEnabled"), targetSelect = $("#layoutTargetPage");
  switchSelect.value = String(widget.tap_mode === "page");
  $("#layoutTargetPageRow").classList.toggle("hidden", widget.tap_mode !== "page");
  targetSelect.replaceChildren(...state.project.pages.filter(p => p.id !== widget.page).map(p => new Option(p.name, p.id)));
  targetSelect.value = widget.target_page;
  if (!targetSelect.value && targetSelect.options.length) targetSelect.selectedIndex = 0;
  switchSelect.onchange = () => {
    const before = cloneProject();
    if (switchSelect.value === "true" && !targetSelect.value) { toast("请先创建一个子页面"); switchSelect.value = "false"; return; }
    widget.tap_mode = switchSelect.value === "true" ? "page" : "none";
    widget.target_page = targetSelect.value;
    recordHistory(before); fillWidgetForm(); markDirty(); saveProject();
  };
  targetSelect.onchange = () => { const before = cloneProject(); widget.target_page = targetSelect.value; recordHistory(before); markDirty(); saveProject(); };
  renderHaActions(widget);
  if ($("#styleSection").previousElementSibling !== tabs) tabs.after($("#styleSection"));
}

function renderHaActions(widget) {
  const domain = $("#haEntityDomain").value;
  if (domain !== "none" && HA_STATE_PRESETS[domain] && widget.binding_type === "state" && ["climate", "switch", "light", "cover", "lock", "input_boolean", "binary_sensor"].includes(domain)) ensureHaStateList(domain, widget);
  const actionEntity = $("#haActionEntityId").value.trim() || widget.binding || "";
  const actionDomain = actionEntity.split(".")[0] || domain;
  const actions = HA_ENTITY_ACTIONS[actionDomain] || [];
  const number = ["input_number", "number"].includes(domain), slider = widget.kind === "slider";
  $("#haPrimaryAction").replaceChildren(new Option("只显示，不操作", ""), ...actions.map(([value, label]) => new Option(label, value)));
  const operation = widget.tap_mode === "ha" || slider ? (widget.ha_action_mode || (widget.action || "").split(".")[1] || "") : "";
  $("#haPrimaryAction").value = operation;
  $("#haPrimaryActionRow").classList.toggle("hidden", ["none", "device"].includes(domain) || slider || widget.tap_mode === "page");
  $("#haActionEntityRow").classList.toggle("hidden", ["none", "device"].includes(domain) || widget.tap_mode === "page");
  $("#haNumberConfig").classList.toggle("hidden", !number);
  $("#numberAppearanceRow").classList.toggle("hidden", !number);
  $("#haEntityIdRow").classList.toggle("hidden", domain === "none");
  $("#haButtonNameRow").classList.add("hidden");
  $("#haSensorFormatRow").classList.toggle("hidden", !["sensor", "device"].includes(domain));
  $("#haSensorStateConfig").classList.toggle("hidden", domain !== "sensor" || !["button", "shape", "icon", "label"].includes(widget.kind));
  $("#haEntityIdRow").childNodes[0].textContent = domain === "device" ? "本机数据源" : "显示数据的实体 ID";
  $("#haEntityId").placeholder = domain === "device" ? "device:battery_level" : `${domain === "none" ? "sensor" : domain}.example`;
  $("#haNumberMin").value = widget.progress_min ?? 0; $("#haNumberMax").value = widget.progress_max ?? 100;
  $("#haNumberUnit").value = widget.value_suffix || ""; $("#haNumberDecimals").value = widget.value_decimals ?? 0;
  $("#haSensorUnit").value = widget.value_suffix || ""; $("#haSensorDecimals").value = widget.value_decimals ?? 0;
  $("#haControlHint").textContent = widget.tap_mode === "page" ? "此组件点击后切换页面；实体仍可用于显示。" : slider ? "滑块跟随实体数值；松手后把滑块当前值写回实体。" : operation === "set_value" ? "点击时将实体直接设为下面的目标数值，不是增加或减少。" : operation === "increment" || operation === "decrement" ? "点击一次，按 HA 数值助手自身配置的步长增加或减少。" : operation ? `显示读取上方实体；点击执行 ${actionDomain}.${operation}。` : "只读取实体用于显示，不发送命令，也不会生成增加/减少按钮。";
  renderHaActionParameter(widget);
  if (["dropdown", "roller"].includes(widget.kind) && operation === "select_option") $("#haControlHint").textContent = "从控件中选择后，将所选选项写回实体；选项文字需与 HA 一致。";
  if (domain === "device") $("#haControlHint").textContent = "本机数据由开发板直接读取，无需填写 HA 操作实体。";
}

function renderHaActionParameter(widget) {
  const operation = $("#haPrimaryAction").value, row = $("#haActionParameterRow"), input = $("#haActionParameter"), label = $("#haActionParameterLabel");
  const config = { turn_on_brightness: ["亮度（0–255）", "brightness", 128, "number"], set_temperature: ["目标温度（°C）", "temperature", 24, "number"], set_hvac_mode: ["运行模式", "hvac_mode", "cool", "text"], set_cover_position: ["位置（0–100）", "position", 50, "number"], set_value: ["点击后设为", "value", widget.action_value ?? 0, "number"], select_option: ["目标选项", "option", "", "text"] }[operation];
  row.classList.toggle("hidden", !config || widget.kind === "slider" || widget.tap_mode === "page" || (["dropdown", "roller"].includes(widget.kind) && operation === "select_option"));
  input.dataset.actionKey = config?.[1] || "";
  if (!config) return;
  label.childNodes[0].textContent = config[0]; input.type = config[3]; input.value = widget.action_data?.[config[1]] ?? config[2];
}

const HA_STATE_PRESETS = {
  sensor: [["off", "关闭", "#3B424C", 0xF0156], ["on", "正常", "#247A4D", 0xF012C]],
  switch: [["off", "关闭", "#3B424C", 0xF0425], ["on", "开启", "#247A4D", 0xF0425]],
  light: [["off", "关闭", "#3B424C", 0xF0336], ["on", "开启", "#9A7418", 0xF0335]],
  climate: [["off", "关闭", "#3B424C", 0xF081D], ["cool", "制冷", "#176B91", 0xF0717], ["heat", "制热", "#A64538", 0xF0238], ["dry", "除湿", "#71611E", 0xF058E], ["fan_only", "送风", "#28745F", 0xF0210], ["auto", "自动", "#5D4A86", 0xF001B]],
  cover: [["closed", "关闭", "#3B424C", 0xF1847], ["open", "打开", "#247A4D", 0xF1846], ["opening", "正在打开", "#176B91", 0xF1846], ["closing", "正在关闭", "#71611E", 0xF1847], ["stopped", "已停止", "#5A5360", 0xF04DB]],
  lock: [["locked", "已上锁", "#247A4D", 0xF033E], ["unlocked", "已解锁", "#8A6330", 0xF0FC6], ["locking", "上锁中", "#176B91", 0xF033E], ["unlocking", "解锁中", "#176B91", 0xF0FC6], ["jammed", "卡住", "#A64538", 0xF0159]],
  script: [["off", "停止", "#3B424C", 0xF04DB], ["on", "运行", "#247A4D", 0xF040A]],
  input_boolean: [["off", "关闭", "#3B424C", 0xF0130], ["on", "开启", "#247A4D", 0xF0131]],
  binary_sensor: [["off", "否", "#3B424C", 0xF0156], ["on", "是", "#247A4D", 0xF012C]]
};

function ensureHaStateList(domain, widget) {
  const preset = HA_STATE_PRESETS[domain];
  if (!preset) return;
  const profile = `${domain}:4`;
  const existing = new Map((widget.state_variants || []).map((item) => [item.value, item]));
  if (!widget.state_variants?.length || widget.ha_state_profile !== profile || domain === "climate") {
    const generated = preset.map(([value, label, background, icon], index) => ({
      value, label, icon_name: label, icon_glyph: String.fromCodePoint(icon),
      background_color: background,
      text_color: widget.text_color, opacity: index ? widget.state_on_bg_opacity : widget.state_off_bg_opacity,
      depth: index ? "raised" : "inset"
    })).map((item) => ({ ...item, ...(existing.get(item.value) || {}) }));
    widget.state_variants = [...generated, ...(widget.state_variants || []).filter((item) => !preset.some(([value]) => value === item.value))];
    widget.ha_state_profile = profile;
    if (!preset.some(([value]) => value === widget.state_preview)) widget.state_preview = preset[0][0];
  }
}

function applyHaPreset(event) {
  const widget = selectedWidget(); if (!widget) return;
  const before = cloneProject(), domain = $("#haEntityDomain").value, entity = $("#haEntityId").value.trim();
  const pageMode = widget.tap_mode === "page";
  let operation = $("#haPrimaryAction").value;
  if (event?.target.id === "haEntityDomain") operation = "";
  widget.binding = domain === "none" ? "" : entity;
  widget.action_entity = domain === "none" ? "" : $("#haActionEntityId").value.trim();
  if (widget.action_entity === entity) widget.action_entity = "";
  if (domain === "none") {
    widget.action = ""; widget.action_data = {}; widget.ha_action_mode = "";
    widget.state_variants = []; widget.state_mapping = false; widget.state_icon_enabled = false;
    if (widget.kind === "icon" && widget.icon_glyph) widget.show_fixed_icon = true;
    widget.ha_state_profile = "none";
  } else if (domain === "input_number" || domain === "number") {
    widget.binding_type = "number"; widget.state_mapping = false; widget.state_variants = []; widget.ha_state_profile = domain;
    widget.progress_min = Number($("#haNumberMin").value || 0); widget.progress_max = Number($("#haNumberMax").value || 100);
    widget.value_suffix = $("#haNumberUnit").value; widget.value_decimals = Number($("#haNumberDecimals").value || 0);
    if (widget.kind === "slider") operation = "set_value";
  } else if (domain === "sensor" || domain === "device") {
    widget.value_suffix = $("#haSensorUnit").value; widget.value_decimals = Number($("#haSensorDecimals").value || 0);
    widget.binding_type = $("#haSensorType").value;
    if (domain === "sensor" && /deng_guang_zhuang_tai/i.test(entity)) {
      widget.binding_type = "state"; widget.state_mapping = true; widget.state_on_value = "全关"; widget.state_preview = "off"; widget.ha_state_profile = "sensor:custom";
    }
    if (domain === "sensor" && widget.state_mapping && widget.ha_state_profile?.startsWith("sensor:")) widget.ha_state_profile = "sensor:custom";
  } else {
    widget.binding_type = "state";
    if (event?.target.id === "haEntityDomain" || !widget.state_variants?.length) ensureHaStateList(domain, widget);
    widget.state_mapping = Boolean(widget.state_variants?.length);
  }
  if (domain !== "none") {
    const target = widget.action_entity || entity, actionDomain = target.split(".")[0] || domain;
    if (!(HA_ENTITY_ACTIONS[actionDomain] || []).some(([key]) => key === operation)) operation = "";
    widget.ha_action_mode = operation;
    widget.action = operation && target ? `${actionDomain}.${operation === "turn_on_brightness" ? "turn_on" : operation}` : "";
    const input = $("#haActionParameter"), key = input.dataset.actionKey;
    if (event?.target.id === "haActionParameter" && key) widget.action_data = { [key]: input.type === "number" ? Number(input.value) : input.value };
    else if (event?.target.id === "haPrimaryAction") widget.action_data = {};
  }
  widget.tap_mode = pageMode ? "page" : widget.action ? "ha" : "none";
  clamp(widget); renderHaActions(widget);
  if (event?.target.id === "haPrimaryAction" && widget.action) {
    const parameter = $("#haActionParameter");
    if (parameter.dataset.actionKey) widget.action_data = { [parameter.dataset.actionKey]: parameter.type === "number" ? Number(parameter.value) : parameter.value };
  }
  renderStateAppearanceEditor(widget); recordHistory(before); renderCanvas(); markDirty(); saveProject();
}

function applyNumberAppearance() {
  const widget = selectedWidget(); if (!widget) return;
  const before = cloneProject(), mode = $("#numberAppearanceMode").value;
  const pageMode = widget.tap_mode === "page";
  widget.ha_visual_mode = mode; widget.kind = mode.startsWith("slider") ? "slider" : "shape";
  widget.binding_type = "number"; widget.state_mapping = false; widget.state_variants = [];
  if (mode.startsWith("slider")) {
    widget.height = Math.max(mode === "slider_value" ? 58 : 33, Math.min(widget.height, 80));
    widget.ha_action_mode = "set_value"; widget.action = `${(widget.action_entity || widget.binding).split(".")[0] || "input_number"}.set_value`; widget.tap_mode = "ha";
  } else {
    widget.action = ""; widget.ha_action_mode = ""; widget.action_data = {}; widget.tap_mode = "none";
  }
  if (pageMode) widget.tap_mode = "page";
  clamp(widget); recordHistory(before); fillWidgetForm(); renderCanvas(); markDirty(); saveProject();
}

function setInspectorMode(mode) {
  $$("#inspectorModeTabs button").forEach((button) => button.classList.toggle("active", button.dataset.inspectorMode === mode));
  $("#haControlPanel").classList.toggle("hidden", mode !== "ha");
  const legacyFunctionalSections = new Set(["contentSection", "stateMapSection", "actionSection", "iconControlSection", "stateAppearancePanel"]);
  [...$("#widgetForm").children].forEach((section) => {
    if (section.id === "inspectorModeTabs" || section.id === "haControlPanel") return;
    section.classList.toggle("inspector-mode-hidden", legacyFunctionalSections.has(section.id) || mode === "ha");
  });
}

function renderStateAppearanceEditor(widget) {
  let panel = $("#stateAppearancePanel");
  if (!panel) {
    panel = document.createElement("section"); panel.id = "stateAppearancePanel";
    panel.className = "ha-subgroup state-appearance-group"; $("#haControlPanel").append(panel);
  }
  const variants = widget.state_variants || [];
  panel.classList.toggle("hidden", !variants.length || widget.state_style_enabled === false);
  if (!variants.length) return;
  if (!variants.some((item) => item.value === widget.state_preview)) widget.state_preview = variants[0].value;
  const selected = variants.find((item) => item.value === widget.state_preview) || variants[0];
  panel.innerHTML = `<h2 class="state-appearance-heading" tabindex="0">HA 状态显示<button type="button" id="toggleStateAppearance" aria-label="展开或收起状态显示">⌃</button></h2><div id="stateAppearanceBody"><label>预览与编辑状态<select id="appearanceStateSelect">${variants.map((item) => `<option value="${item.value}">${item.label} (${item.value})</option>`).join("")}</select></label><div class="state-appearance-editor"><label id="variantLabelRow">此状态文字<input id="variantLabel" placeholder="例如：制冷"></label><label>此状态深度<select id="variantDepth"><option value="raised">凸起</option><option value="inset">凹下</option><option value="flat">平面</option></select></label><div class="field-grid"><label id="variantBackgroundRow">此状态背景颜色<input id="variantBackground" type="color"></label><label id="variantTextColorRow">此状态文字颜色<input id="variantTextColor" type="color"></label></div><div class="field-grid"><label>此状态图标大小<input id="variantIconSize" type="number" min="8" max="192"></label><label>图标 X 位置<input id="variantIconX" type="number" min="-400" max="400"></label><label>图标 Y 位置<input id="variantIconY" type="number" min="-240" max="240"></label></div><div class="asset-actions"><button id="variantIconSelect" class="button" type="button">选择图标</button><button id="variantIconReset" class="button" type="button">恢复默认</button><button id="variantIconClear" class="button" type="button">清除当前状态图标</button></div><small id="variantIconName" class="field-hint"></small></div></div>`;
  const collapsed = panel.dataset.collapsed === "true"; $("#stateAppearanceBody").classList.toggle("hidden", collapsed); panel.classList.toggle("ha-collapsed", collapsed); $("#toggleStateAppearance").textContent = collapsed ? "⌄" : "⌃";
  $("#variantIconReset").textContent = "恢复实体默认图标";
  $("#variantIconClear").textContent = "清除当前状态图标";
  $("#variantIconReset").title = "恢复当前状态由实体类型定义的默认图标";
  $("#variantIconClear").title = "仅移除当前预览状态的图标，其他状态不受影响";
  // 状态文字会同时用于工作台预览和设备端渲染，因此所有支持 HA 状态的
  // 按钮（包括纯图标按钮）都必须能在这里查看和编辑。清空即可隐藏该状态文字。
  $("#variantLabelRow").classList.remove("hidden");
  $("#variantTextColorRow").childNodes[0].textContent = widget.kind === "icon" ? "此状态图标颜色（覆盖基础）" : "此状态文字颜色（覆盖基础）";
  const toggle = () => { panel.dataset.collapsed = String(panel.dataset.collapsed !== "true"); renderStateAppearanceEditor(widget); };
  $("#toggleStateAppearance").addEventListener("click", toggle);
  if (collapsed) return;
  $("#appearanceStateSelect").value = selected.value; $("#variantLabel").value = selected.label;
  $("#variantDepth").value = selected.depth || "flat";
  $("#variantBackground").value = selected.background_color || widget.background_color; $("#variantTextColor").value = selected.text_color || widget.text_color;
  $("#variantIconSize").value = selected.icon_size ?? 32; $("#variantIconX").value = selected.icon_offset_x ?? 0; $("#variantIconY").value = selected.icon_offset_y ?? 0;
  $("#variantIconName").textContent = selected.icon_name ? `当前图标：${selected.icon_name}` : "当前状态未单独设置图标";
  $("#appearanceStateSelect").addEventListener("change", (event) => { widget.state_preview = event.target.value; renderStateAppearanceEditor(widget); renderCanvas(); });
  for (const [id, field] of [["variantLabel", "label"], ["variantDepth", "depth"], ["variantBackground", "background_color"], ["variantTextColor", "text_color"]]) {
    $("#" + id).addEventListener("input", (event) => { selected[field] = event.target.value; renderCanvas(); markDirty(); saveProject(); });
  }
  for (const [id, field] of [["variantIconSize", "icon_size"], ["variantIconX", "icon_offset_x"], ["variantIconY", "icon_offset_y"]]) $("#" + id).addEventListener("input", (event) => { selected[field] = Number(event.target.value); renderCanvas(); markDirty(); saveProject(); });
  $("#variantIconSelect").addEventListener("click", () => {
    const category = widget.ha_state_profile?.startsWith("climate:") ? "空调模式" : undefined;
    openIconPicker(category, widget.id, `variant:${selected.value}`);
  });
  $("#variantIconReset").addEventListener("click", () => {
    const domain = (widget.ha_state_profile || "").split(":")[0];
    const preset = (HA_STATE_PRESETS[domain] || []).find(([value]) => value === selected.value);
    if (preset) { selected.icon_name = preset[1]; selected.icon_glyph = String.fromCodePoint(preset[3]); }
    renderStateAppearanceEditor(widget); renderCanvas(); markDirty(); saveProject();
  });
  $("#variantIconClear").addEventListener("click", () => { selected.icon_name = ""; selected.icon_glyph = ""; renderStateAppearanceEditor(widget); renderCanvas(); markDirty(); saveProject(); });
}

function renderMatrixButtonEditor(widget) {
  const editor = $("#matrixButtonEditor"); editor.replaceChildren();
  const previous = Array.isArray(widget.matrix_buttons) ? widget.matrix_buttons : [];
  const buttons = [];
  String(widget.control_options || "按钮一").split("\n").forEach((rowText, row) => rowText.split("|").forEach((text, column) => {
    const old = previous.find((item) => Number(item.row) === row && Number(item.column) === column) || {};
    buttons.push({ text: text.trim(), row, column, entity: old.entity || "", action: old.action || "", value: old.value || "", disabled: Boolean(old.disabled) });
  }));
  widget.matrix_buttons = buttons;
  buttons.forEach((item, index) => {
    const block = document.createElement("div"); block.className = "matrix-button-config";
    block.innerHTML = `<strong>${item.text || `按钮 ${index + 1}`}（第${item.row + 1}行，第${item.column + 1}列）</strong><label>HA实体<input data-matrix-field="entity" placeholder="switch.living_room"></label><div class="field-grid"><label>HA动作<input data-matrix-field="action" placeholder="switch.toggle"></label><label>操作值<input data-matrix-field="value" placeholder="可留空"></label></div><label><input type="checkbox" data-matrix-field="disabled"> 禁用此按钮</label>`;
    for (const field of ["entity", "action", "value"]) block.querySelector(`[data-matrix-field="${field}"]`).value = item[field];
    block.querySelector('[data-matrix-field="disabled"]').checked = item.disabled;
    block.querySelectorAll("[data-matrix-field]").forEach((input) => input.addEventListener("change", () => {
      const before = cloneProject(); item[input.dataset.matrixField] = input.type === "checkbox" ? input.checked : input.value.trim();
      recordHistory(before); markDirty(); saveProject();
    }));
    editor.append(block);
  });
}

function newWidget(kind, extra = {}) {
  const index = state.project.widgets.length + 1;
  const topLayer = Math.max(0, ...state.project.widgets.filter((item) => widgetOnPage(item, state.activePageId)).map((item) => item.z_index || 0)) + 1;
  const labels = { button: "虚拟按钮", page_button: "切换界面", image: "图片", icon: "图标", shape: "双击编辑", label: "文本显示", progress_circle: "50%", progress_bar: "50%", battery: "电池", slider: "", switch: "", checkbox: "复选框", dropdown: "", roller: "选项二", spinbox: "50", spinner: "", led: "", qrcode: "二维码", textarea: "", keyboard: "", trend_chart: "趋势", buttonmatrix: "按钮矩阵", table: "数据表格", msgbox: "提示", container: "布局容器", tabview: "标签页", tileview: "磁贴页" };
  const progress = ["progress_circle", "progress_bar", "battery"].includes(kind);
  const widget = {
        id: `widget_${Date.now().toString(36)}_${index}`, kind, text: kind === "shape" && extra.shape_type === "line" ? "" : labels[kind],

    x: 40 + (index * 18) % 260, y: 40 + (index * 18) % 160,
    width: kind === "image" ? 240 : kind === "shape" || kind === "progress_circle" ? 160 : ["battery", "trend_chart", "buttonmatrix", "table", "container", "tabview", "tileview"].includes(kind) ? 300 : kind === "switch" ? 72 : kind === "checkbox" ? 180 : kind === "qrcode" ? 160 : kind === "keyboard" ? 500 : 220,
        height: kind === "image" ? 140 : kind === "progress_circle" ? 160 : kind === "shape" && extra.shape_type === "line" ? 20 : kind === "shape" ? 100 : kind === "progress_bar" ? 48 : kind === "battery" ? 86 : kind === "trend_chart" ? 180 : ["buttonmatrix", "table", "container"].includes(kind) ? 160 : ["tabview", "tileview"].includes(kind) ? 240 : kind === "switch" ? 38 : kind === "slider" ? 42 : kind === "roller" ? 120 : kind === "spinner" || kind === "led" ? 56 : kind === "qrcode" ? 160 : kind === "keyboard" ? 180 : 54,

        font_size: 28, text_color: state.project.theme_text || "#FFFFFF", background_color: kind.includes("button") ? (state.project.theme_accent || "#1976D2") : (state.project.theme_surface || "#252B33"), background_opacity: 100, opacity: 100, text_opacity: 100, border_opacity: 100,

    binding: "", binding_type: ["switch", "checkbox", "dropdown", "roller"].includes(kind) ? "state" : "number", value_suffix: "", value_decimals: 0, state_mapping: false, state_on_value: "on", state_on_text: "开启", state_off_text: "关闭", state_on_color: "#45C46A", state_off_color: "#58616B", state_on_bg_opacity: 100, state_off_bg_opacity: 72, state_visual: "color", state_preview: "off", visibility_mode: "always", visible_state: "on", action: "", action_entity: "", action_value: 1, tap_mode: kind === "page_button" ? "page" : kind === "button" ? "ha" : "none", animation: "无", asset_path: "", content_asset_path: "",
    page: state.activePageId, pages: [state.activePageId], z_index: topLayer, locked: false, hidden: false, group_id: "", image_fit: "fill", image_offset_x: 50, image_offset_y: 50, image_opacity: 100, image_tint: "#FFFFFF", image_tint_opacity: 0, image_grayscale: 0, image_brightness: 100, image_blur: 0,
    shape_type: extra.shape_type || "rectangle", border_color: "#FFFFFF", border_width: progress ? 12 : kind === "shape" ? 2 : 0, radius: state.project.theme_radius ?? 8,
    line_angle: 0, line_length: 160, ellipse_radius_x: 80, ellipse_radius_y: 50, text_align: "center", text_offset_x: 0, text_offset_y: 0, auto_fit_text: true, icon_name: "", icon_glyph: "", state_icon_enabled: false, state_icon_on_name: "", state_icon_on_glyph: "", state_icon_off_name: "", state_icon_off_glyph: "", icon_size: 32, icon_offset_x: 0, icon_offset_y: 0, click_effect: "scale",
    progress_min: 0, progress_max: 100, progress_value: 50, progress_color: "#2F7DF6", show_value: "percent", battery_style: "horizontal", battery_display: "percent", battery_low_color: "#E5534B", battery_warning_color: "#F5A623", battery_charge_color: "#45C46A", battery_discharge_color: "#2F7DF6", control_checked: false, control_options: ["buttonmatrix", "table"].includes(kind) ? "1|2|3\n4|5|6\n7|8|9" : "选项一\n选项二\n选项三", control_selected: 0, control_rows: 3, control_digits: 4, control_decimals: 0, control_text: kind === "qrcode" ? "https://esphome.io" : kind === "msgbox" ? "消息内容" : "", control_target: "",
    parent_id: "", layout_type: kind === "container" ? "flex" : "none", flex_flow: "row_wrap", flex_align_main: "start", flex_align_cross: "start", flex_align_track: "start", layout_pad_row: 8, layout_pad_column: 8, grid_rows: 2, grid_columns: 2, grid_row: 0, grid_column: 0, grid_row_span: 1, grid_column_span: 1, view_items: "标签一\n标签二", view_index: 0,
    target_page: state.project.pages.find((page) => page.id !== state.activePageId)?.id || state.activePageId, ...extra,
  };
  widget.trend_mode ||= "line"; widget.trend_caption ||= ""; widget.trend_show_axes ??= true; widget.trend_show_x_axis ??= true; widget.trend_show_y_axis ??= true; widget.trend_axis_color ||= "#AEB7C2"; widget.trend_time_labels ||= "fuzzy"; widget.trend_sample_interval ??= 0; widget.trend_point_count ||= 120; widget.trend_x_ticks ||= 5; widget.trend_y_ticks ||= 5; widget.matrix_buttons ||= [];
  widget.view_preview_index ||= 0; widget.view_preview_row ||= 0; widget.view_preview_column ||= 0;
  widget.container_scrollable ??= false; widget.container_scroll_dir ||= "VER"; widget.container_scrollbar ||= "AUTO"; widget.container_scroll_momentum ??= true; widget.container_scroll_elastic ??= true;
  widget.trend_time_range_minutes ||= 120; widget.trend_show_title ??= true; widget.trend_show_current ??= true; if (kind === "trend_chart") widget.font_size = 14;
    const before = cloneProject();
  if (kind === "shape" && extra.shape_type === "ellipse") { widget.ellipse_radius_x = 80; widget.ellipse_radius_y = 50; }
  if (kind === "shape" && extra.shape_type === "circle") { widget.ellipse_radius_x = 60; widget.ellipse_radius_y = 60; }
  clamp(widget); state.project.widgets.push(widget); selectWidget(widget.id); recordHistory(before); markDirty(); saveProject();

}

function copySelectedWidget() {
  const sources = selectedWidgets();
  if (!sources.length) return;
  const before = cloneProject(), copies = sources.map((source, index) => {
    const copy = JSON.parse(JSON.stringify(source));
    copy.id = `widget_${Date.now().toString(36)}_${state.project.widgets.length + index + 1}`;
    copy.text = `${source.text || source.kind} 副本`; copy.x += 20; copy.y += 20; copy.locked = false; copy.hidden = false; clamp(copy); return copy;
  });
  state.project.widgets.push(...copies); selectWidget(copies.at(-1).id); state.selectedIds = copies.map((copy) => copy.id); state.selectedId = state.selectedIds.at(-1); renderCanvas();
  recordHistory(before); markDirty(); saveProject();
}

const HA_CONTROL_WIZARD = {
  input_number: {
    label: "数值助手", placeholder: "input_number.example", controls: [
      ["number", "数字显示", "shape"], ["slider", "滑块", "slider"]
    ]
  },
  input_boolean: {
    label: "布尔助手", placeholder: "input_boolean.example", controls: [
      ["switch", "开关", "switch"], ["button", "状态按钮", "button"]
    ]
  },
  light_power: {
    label: "灯光开关", placeholder: "light.living_room", controls: [
      ["switch", "开关", "switch"], ["button", "状态按钮", "button"]
    ]
  },
  light_brightness: {
    label: "灯光亮度", placeholder: "light.living_room", controls: [
      ["slider", "亮度滑块", "slider"], ["roller", "亮度滚轮", "roller"]
    ]
  }
};

function openHaControlWizard(type = "input_number") {
  const dialog = $("#componentPicker"), tabs = $("#componentCategories"), grid = $("#componentGrid"), config = HA_CONTROL_WIZARD[type];
  $("#componentPickerTitle").textContent = "插入 HA 实体控件"; tabs.replaceChildren(); grid.replaceChildren();
  for (const [key, item] of Object.entries(HA_CONTROL_WIZARD)) {
    const button = document.createElement("button"); button.textContent = item.label; button.classList.toggle("active", key === type);
    button.addEventListener("click", () => openHaControlWizard(key)); tabs.append(button);
  }
  const setup = document.createElement("div"); setup.className = "ha-wizard-setup";
  setup.innerHTML = `<label>实体 ID<input id="wizardEntity" placeholder="${config.placeholder}"></label>${type === "input_number" ? '<div class="field-grid"><label>最小值<input id="wizardMin" type="number" value="0"></label><label>最大值<input id="wizardMax" type="number" value="100"></label></div>' : ''}<small>选择外观后直接插入已绑定控件</small>`;
  grid.append(setup);
  for (const [mode, label, kind] of config.controls) {
    const button = document.createElement("button"); button.innerHTML = `<span class="meter-preview">${kind === "slider" ? "↔" : kind === "roller" ? "↕" : kind === "switch" ? "◉" : "42"}</span><strong>${label}</strong>`;
    button.addEventListener("click", () => {
      const entity = $("#wizardEntity").value.trim(); if (!entity) { toast("请先填写 HA 实体 ID"); return; }
      const domain = type.startsWith("light") ? "light" : type;
      const extra = { text: config.label, binding: entity, action_entity: "", ha_visual_mode: mode, binding_type: type === "input_boolean" || type === "light_power" ? "state" : "number" };
      if (type === "input_number") Object.assign(extra, { progress_min: Number($("#wizardMin").value || 0), progress_max: Number($("#wizardMax").value || 100), action: kind === "slider" ? "input_number.set_value" : "", tap_mode: kind === "slider" ? "ha" : "none", show_fixed_title: false, ha_action_mode: kind === "slider" ? "set_value" : "", ha_state_profile: "input_number" });
      if (type === "input_boolean") Object.assign(extra, { action: "input_boolean.toggle", ha_action_mode: "toggle", tap_mode: "ha", state_mapping: true, ha_state_profile: "input_boolean:4" });
      if (type === "light_power") Object.assign(extra, { action: "light.toggle", ha_action_mode: "toggle", tap_mode: "ha", state_mapping: true, ha_state_profile: "light:4" });
      if (type === "light_brightness") Object.assign(extra, { binding_attribute: "brightness", progress_min: 0, progress_max: 255, action: "light.turn_on", ha_action_mode: "turn_on_brightness", control_options: "0%\n25%\n50%\n75%\n100%", control_rows: 3 });
      newWidget(kind, extra); const created = selectedWidget(); if (["input_boolean", "light"].includes(domain)) ensureHaStateList(domain, created);
      dialog.close();
    }); grid.append(button);
  }
  if (!dialog.open) dialog.showModal();
}

function copyComponentsToClipboard() {
  const sources = selectedWidgets(); if (!sources.length) return;
  state.componentClipboard = JSON.parse(JSON.stringify(sources)); renderCanvas(); toast(`已复制 ${sources.length} 个组件`);
}

function pasteCopiedWidgets() {
  const sources = state.componentClipboard; if (!sources?.length) return;
  const before = cloneProject(), idMap = new Map(), groupMap = new Map(), stamp = Date.now().toString(36);
  sources.forEach((source, index) => idMap.set(source.id, `widget_${stamp}_${state.project.widgets.length + index + 1}`));
  const copies = sources.map((source) => {
    const copy = JSON.parse(JSON.stringify(source)); copy.id = idMap.get(source.id); copy.text = `${source.text || source.kind} 副本`;
    copy.x += 20; copy.y += 20; copy.locked = false; copy.hidden = false; copy.page = state.activePageId; copy.pages = [state.activePageId];
    copy.parent_id = idMap.get(source.parent_id) || "";
    if (source.group_id) { if (!groupMap.has(source.group_id)) groupMap.set(source.group_id, `group_${stamp}_${groupMap.size}`); copy.group_id = groupMap.get(source.group_id); }
    clamp(copy); return copy;
  });
  state.project.widgets.push(...copies); state.selectedIds = copies.map((copy) => copy.id); state.selectedId = state.selectedIds.at(-1); renderCanvas();
  recordHistory(before); markDirty(); saveProject(); toast(`已粘贴 ${copies.length} 个组件`);
}

const STYLE_PROPERTIES = ["font_size", "text_color", "background_color", "background_opacity", "opacity", "text_opacity", "border_color", "border_width", "border_opacity", "radius", "text_align", "text_offset_x", "text_offset_y", "auto_fit_text", "font_weight", "icon_size", "icon_offset_x", "icon_offset_y", "image_fit", "image_offset_x", "image_offset_y", "image_opacity", "image_tint", "image_tint_opacity", "image_grayscale", "image_brightness", "image_blur", "progress_color", "state_on_color", "state_off_color", "state_on_bg_opacity", "state_off_bg_opacity", "state_visual", "click_effect"];

function copySelectedStyle() {
  const source = selectedWidget(); if (!source) return;
  state.styleClipboard = Object.fromEntries(STYLE_PROPERTIES.filter((property) => property in source).map((property) => [property, JSON.parse(JSON.stringify(source[property]))]));
  renderCanvas(); toast("组件格式已复制");
}

function pasteCopiedStyle() {
  const targets = selectedWidgets(); if (!state.styleClipboard || !targets.length) return;
  const before = cloneProject();
  targets.forEach((target) => { for (const [property, value] of Object.entries(state.styleClipboard)) if (property in target) target[property] = JSON.parse(JSON.stringify(value)); clamp(target); });
  recordHistory(before); fillWidgetForm(); renderCanvas(); markDirty(); saveProject(); toast(`格式已应用到 ${targets.length} 个组件`);
}

function beginMarquee(event) {
  if (event.target !== event.currentTarget) return;
  event.preventDefault();
  const rect = event.currentTarget.getBoundingClientRect(), node = document.createElement("div"); node.className = "selection-box"; event.currentTarget.append(node);
  const x = (event.clientX - rect.left) / state.zoom, y = (event.clientY - rect.top) / state.zoom;
  state.marquee = { x, y, left: x, top: y, right: x, bottom: y, node };
}

function openIconPicker(category = Object.keys(ICON_CATALOG)[0], targetWidgetId = null, stateSlot = "") {
  const dialog = $("#iconPicker"), tabs = $("#iconCategories"), grid = $("#iconGrid");
  tabs.replaceChildren(); grid.replaceChildren();
  for (const name of Object.keys(ICON_CATALOG)) {
    const button = document.createElement("button");
    button.textContent = name; button.classList.toggle("active", name === category);
    button.addEventListener("click", () => openIconPicker(name, targetWidgetId, stateSlot)); tabs.append(button);
  }
  for (const [name, codepoint] of ICON_CATALOG[category]) {
    const button = document.createElement("button"), glyph = String.fromCodePoint(codepoint);
    button.innerHTML = `<span class="mdi-glyph">${glyph}</span><small>${name}</small>`;
    button.addEventListener("click", () => {
      if (targetWidgetId) {
        const widget = state.project.widgets.find((item) => item.id === targetWidgetId);
        if (widget) {
          const before = cloneProject();
          if (stateSlot.startsWith("variant:")) {
            const variant = (widget.state_variants || []).find((item) => item.value === stateSlot.slice(8));
            if (variant) { variant.icon_name = name; variant.icon_glyph = glyph; }
          }
          else if (stateSlot === "on") { widget.state_icon_on_name = name; widget.state_icon_on_glyph = glyph; widget.state_icon_enabled = true; }
          else if (stateSlot === "off") { widget.state_icon_off_name = name; widget.state_icon_off_glyph = glyph; widget.state_icon_enabled = true; }
          else { widget.icon_name = name; widget.icon_glyph = glyph; widget.show_fixed_icon = true; }
          widget.icon_size ||= 32;
          if (widget.kind === "progress_circle" && !widget.icon_offset_y && !widget.text_offset_y) {
            widget.icon_offset_y = -28; widget.text_offset_y = 25;
          } else if (widget.kind === "progress_bar" && !widget.icon_offset_x && !widget.text_offset_x) {
            widget.icon_offset_x = -Math.max(28, Math.round(widget.width * 0.36)); widget.text_offset_x = 18;
          }
          recordHistory(before); fillWidgetForm(); renderCanvas(); markDirty(); saveProject();
        }
      } else {
        newWidget("icon", { text: name, icon_name: name, icon_glyph: glyph, show_fixed_icon: true, show_fixed_title: false, icon_size: 40, width: 64, height: 64, font_size: 40, background_opacity: 0, border_width: 0 });
      }
      dialog.close();
    });
    grid.append(button);
  }
  if (!dialog.open) dialog.showModal();
}

const METER_PRESETS = {
  "温度": { text: "温度", binding: "sensor.living_room_temperature", min: -10, max: 50, suffix: "°C", decimals: 1, color: "#F26B5B" },
  "湿度": { text: "湿度", binding: "sensor.living_room_humidity", min: 0, max: 100, suffix: "%", decimals: 0, color: "#42A5F5" },
  "亮度": { text: "亮度", binding: "sensor.living_room_illuminance", min: 0, max: 1000, suffix: "lx", decimals: 0, color: "#F5C451" },
  "自定义": { text: "数值", binding: "sensor.example_value", min: 0, max: 100, suffix: "", decimals: 0, color: "#2F7DF6" },
};

function openMeterPicker(type = "温度") {
  const dialog = $("#componentPicker"), tabs = $("#componentCategories"), grid = $("#componentGrid"), preset = METER_PRESETS[type];
  $("#componentPickerTitle").textContent = "选择数值仪表";
  tabs.replaceChildren(); grid.replaceChildren();
  for (const name of Object.keys(METER_PRESETS)) {
    const button = document.createElement("button"); button.textContent = name; button.classList.toggle("active", name === type);
    button.addEventListener("click", () => openMeterPicker(name)); tabs.append(button);
  }
  [["数字", "大号数值与单位", "shape"], ["圆环", "范围进度与中心数值", "progress_circle"], ["柱状", "紧凑横向进度", "progress_bar"]].forEach(([name, description, kind]) => {
    const button = document.createElement("button");
    button.innerHTML = `<span class="meter-preview meter-${kind}">${name === "数字" ? "42" : name === "圆环" ? "◔" : "▬"}</span><strong>${name}</strong><small>${description}</small>`;
    button.addEventListener("click", () => {
      const common = { text: preset.text, binding: preset.binding, binding_type: "number", value_suffix: preset.suffix, value_decimals: preset.decimals, progress_min: preset.min, progress_max: preset.max, progress_color: preset.color, show_value: "value" };
      if (kind === "shape") newWidget("shape", { ...common, width: 230, height: 100, font_size: 40, background_color: "#18242D", border_color: preset.color, border_width: 2, radius: 8 });
      else if (kind === "progress_circle") newWidget(kind, { ...common, width: 160, height: 160, border_width: 14, background_color: "#303841" });
      else newWidget(kind, { ...common, width: 300, height: 54, border_width: 2, background_color: "#303841" });
      dialog.close();
    });
    grid.append(button);
  });
  if (!dialog.open) dialog.showModal();
}

const STATUS_ICON_PRESETS = {
  "文字状态": [
    { name: "空调", text: "空调", binding: "climate.living_room", onValue: "off", onText: "关闭", offText: "运行中", onColor: "#58616B", offColor: "#2F7DF6" },
    { name: "在家", text: "在家", binding: "input_boolean.person_home", onValue: "on", onText: "在家", offText: "离家", onColor: "#45C46A", offColor: "#58616B" },
    { name: "睡眠", text: "睡眠", binding: "input_boolean.person_sleeping", onValue: "on", onText: "睡眠", offText: "起床", onColor: "#6F7FDB", offColor: "#58616B" },
  ],
  "图片状态": [
    { name: "空调", text: "空调", binding: "climate.living_room", onValue: "off", onText: "关闭", offText: "运行中", onGlyph: 0xF001B, offGlyph: 0xF050F, onColor: "#58616B", offColor: "#2F7DF6" },
    { name: "在家", text: "在家", binding: "input_boolean.person_home", onValue: "on", onText: "在家", offText: "离家", onGlyph: 0xF0004, offGlyph: 0xF000D, onColor: "#45C46A", offColor: "#58616B" },
    { name: "睡眠", text: "睡眠", binding: "input_boolean.person_sleeping", onValue: "on", onText: "睡眠", offText: "起床", onGlyph: 0xF04B2, offGlyph: 0xF08A0, onColor: "#6F7FDB", offColor: "#58616B" },
  ],
};

function openStatusIconPicker(category = "文字状态") {
  const dialog = $("#componentPicker"), tabs = $("#componentCategories"), grid = $("#componentGrid");
  $("#componentPickerTitle").textContent = "选择状态图标";
  tabs.replaceChildren(); grid.replaceChildren();
  Object.keys(STATUS_ICON_PRESETS).forEach((name) => {
    const button = document.createElement("button");
    button.textContent = name; button.classList.toggle("active", name === category);
    button.addEventListener("click", () => openStatusIconPicker(name)); tabs.append(button);
  });
  STATUS_ICON_PRESETS[category].forEach((preset) => {
    const button = document.createElement("button");
    const preview = preset.onGlyph ? String.fromCodePoint(preset.onGlyph) : "开";
    button.innerHTML = `<span class="mdi-glyph">${preview}</span><strong>${preset.name}</strong><small>${preset.onText} / ${preset.offText}</small>`;
    button.addEventListener("click", () => {
      const common = {
        text: preset.text, binding: preset.binding, binding_type: "state", state_mapping: true,
        state_on_value: preset.onValue, state_on_text: preset.onText, state_off_text: preset.offText,
        state_on_color: preset.onColor, state_off_color: preset.offColor, state_visual: "both",
        width: category === "文字状态" ? 250 : 120, height: category === "文字状态" ? 82 : 120,
        font_size: category === "文字状态" ? 24 : 54, background_color: "#18242D", border_color: preset.offColor,
        border_width: 1, radius: 8,
      };
      if (preset.onGlyph) {
        Object.assign(common, {
          kind: "icon", icon_name: preset.name, icon_glyph: String.fromCodePoint(preset.onGlyph),
          state_icon_enabled: true, state_icon_on_name: preset.onText, state_icon_on_glyph: String.fromCodePoint(preset.onGlyph),
          state_icon_off_name: preset.offText, state_icon_off_glyph: String.fromCodePoint(preset.offGlyph),
          background_opacity: 0, border_width: 0,
        });
        newWidget("icon", common);
      } else newWidget("shape", common);
      dialog.close();
    });
    grid.append(button);
  });
  if (!dialog.open) dialog.showModal();
}

const SMART_PRESETS = [
  { name: "天气", glyph: 0xF0595, text: "天气", binding: "weather.home", color: "#24516A" },
  { name: "灯光", glyph: 0xF0335, text: "灯光", binding: "light.living_room", color: "#6B5721", action: "light.toggle", entity: "light.living_room" },
  { name: "窗帘", glyph: 0xF1846, text: "窗帘", binding: "cover.living_room", color: "#3E5064", action: "cover.toggle", entity: "cover.living_room" },
  { name: "门锁", glyph: 0xF033E, text: "门锁", binding: "lock.front_door", color: "#315842", stateOn: "locked", onText: "已锁", offText: "未锁" },
  { name: "场景", glyph: 0xF0FCE, text: "观影场景", binding: "", color: "#61436D", action: "scene.turn_on", entity: "scene.movie" },
];

function addSmartCard(preset) {
  const group = `group_${Date.now().toString(36)}`, x = 90, y = 90;
  newWidget("shape", {
    text: preset.text, x, y, width: 280, height: 96, font_size: 25, text_offset_x: 30,
    binding: preset.binding, binding_type: "state", background_color: preset.color, border_color: "#FFFFFF", border_opacity: 28, border_width: 1, radius: 8,
    state_mapping: Boolean(preset.stateOn), state_on_value: preset.stateOn || "on", state_on_text: preset.onText || "开启", state_off_text: preset.offText || "关闭",
    tap_mode: preset.action ? "ha" : "none", action: preset.action || "", action_entity: preset.entity || "", group_id: group,
  });
  const card = selectedWidget();
  newWidget("icon", {
    text: preset.name, icon_name: preset.name, icon_glyph: String.fromCodePoint(preset.glyph), x: x + 18, y: y + 19, width: 58, height: 58,
    font_size: 38, text_color: "#FFFFFF", background_opacity: 0, border_width: 0,
    tap_mode: preset.action ? "ha" : "none", action: preset.action || "", action_entity: preset.entity || "", group_id: group,
  });
  const icon = selectedWidget();
  state.selectedIds = [card.id, icon.id]; state.selectedId = icon.id; renderCanvas(); saveProject();
}

function openSmartPicker() {
  const dialog = $("#componentPicker"), tabs = $("#componentCategories"), grid = $("#componentGrid");
  $("#componentPickerTitle").textContent = "选择智能家居卡片";
  tabs.replaceChildren(); grid.replaceChildren();
  SMART_PRESETS.forEach((preset) => {
    const button = document.createElement("button"), glyph = String.fromCodePoint(preset.glyph);
    button.innerHTML = `<span class="mdi-glyph">${glyph}</span><strong>${preset.name}</strong><small>图标、状态与卡片样式</small>`;
    button.addEventListener("click", () => { addSmartCard(preset); dialog.close(); });
    grid.append(button);
  });
  if (!dialog.open) dialog.showModal();
}

function addTemplate(name) {
  const add = (kind, extra) => newWidget(kind, extra);
  if (name === "input_keyboard") {
    add("textarea", { x: 120, y: 40, width: 560, height: 62, control_text: "请输入内容" });
    const target = selectedWidget();
    add("keyboard", { x: 120, y: 120, width: 560, height: 300, control_target: target.id });
    return;
  }
  if (name === "meter") { openMeterPicker(); return; }
  if (name === "status_icon") { openStatusIconPicker(); return; }
  if (name === "room_lights") {
    const rooms = [
      ["客厅 / 厨房", "sensor.ke_ting_chu_fang_deng_guang_zhuang_tai", "script.turn_off_living_kitchen_lights", 80, 72],
      ["洗手间", "sensor.xi_shou_jian_deng_guang_zhuang_tai", "script.turn_off_bathroom_lights", 400, 72],
      ["主卧", "sensor.zhu_wo_deng_guang_zhuang_tai", "script.turn_off_master_bedroom_lights", 80, 180],
      ["次卧", "sensor.ci_wo_deng_guang_zhuang_tai", "script.turn_off_secondary_bedroom_lights", 400, 180],
      ["儿童房", "sensor.er_tong_fang_deng_guang_zhuang_tai", "script.turn_off_children_bedroom_lights", 80, 288],
      ["全屋关灯", "", "script.turn_off_all_lights", 400, 288],
    ];
    rooms.forEach(([text, binding, actionEntity, x, y]) => add("button", {
      text, x, y, width: 280, height: 84, font_size: 23, binding, binding_type: "state",
      state_mapping: Boolean(binding), state_on_value: "0", state_on_text: "亮灯", state_off_text: "关闭", state_visual: "both", state_preview: "off", ha_state_profile: "sensor:light_status",
      state_visual: "both", background_color: "#243746", border_color: "#4B7185", border_width: 1, radius: 8,
      tap_mode: "ha", action: "script.turn_on", action_entity: actionEntity,
    }));
    toast("已添加房间灯光状态与分组关灯按钮，请确认五个传感器实体 ID");
    return;
  }
  if (name === "smart_home") { openSmartPicker(); return; }
  if (name === "battery") {
    state.project.battery_monitor = true;
    $$('[data-project="battery_monitor"]').forEach((input) => { input.value = "true"; });
    add("battery", { text: "", binding: "device:battery_level", progress_min: 0, progress_max: 100, show_value: "percent", width: 150, height: 48, progress_color: "#45C46A", background_color: "#303841", border_width: 6, battery_style: "horizontal", battery_display: "percent" });
    toast("已添加INA电池组件并启用硬件检测，请核对芯片、地址和采样电阻");
    return;
  }
  if (name === "presence") {
    const cards = [
      { text: "成员一", binding: "person.person_1", x: 80 },
      { text: "成员二", binding: "person.person_2", x: 410 },
    ];
    cards.forEach((item) => add("shape", {
      ...item, y: 112, width: 310, height: 92, font_size: 23, binding_type: "state",
      state_mapping: true, state_on_value: "home", state_on_text: "在家", state_off_text: "离家",
      state_on_color: "#267A55", state_off_color: "#4A5561", state_visual: "both",
      background_color: "#17232D", border_color: "#486173", border_width: 1, radius: 6,
    }));
    add("shape", {
      text: "当前在家", binding: "sensor.people_home_count", binding_type: "number", value_suffix: "人",
      x: 250, y: 232, width: 300, height: 82, font_size: 28, background_color: "#16384A",
      border_color: "#4DA3FF", border_width: 1, radius: 6,
    });
    toast("已添加两名家庭成员和在家人数；请将实体改为HA中的person实体与人数传感器");
    return;
  }
  if (name === "presence_icons") {
    const absent = String.fromCodePoint(0xF000D);
    const presets = [
      ["成人", 0xF0004, "input_boolean.adult_home"], ["男性", 0xF064D, "input_boolean.man_home"],
      ["女性", 0xF0649, "input_boolean.woman_home"], ["老人", 0xF1581, "input_boolean.elder_home"],
      ["儿童", 0xF02E7, "input_boolean.child_home"], ["睡眠", 0xF04B2, "input_boolean.sleeping"],
    ];
    presets.forEach(([text, codepoint, entity], index) => {
      const sleep = text === "睡眠";
      add("icon", {
        text, x: 64 + (index % 3) * 180, y: 72 + Math.floor(index / 3) * 150, width: 112, height: 112,
        font_size: 54, icon_name: text, icon_glyph: String.fromCodePoint(codepoint), background_opacity: 0, border_width: 0,
        binding: entity, binding_type: "state", state_mapping: true, state_on_value: "on", state_on_text: sleep ? "睡眠" : "在",
        state_off_text: sleep ? "起床" : "不在", state_on_color: sleep ? "#6F7FDB" : "#45C46A", state_off_color: "#66717D",
        state_visual: "color", state_icon_enabled: true, state_icon_on_name: text, state_icon_on_glyph: String.fromCodePoint(codepoint),
        state_icon_off_name: sleep ? "起床" : "不在", state_icon_off_glyph: sleep ? String.fromCodePoint(0xF08A0) : absent,
        tap_mode: "ha", action: "homeassistant.toggle", action_entity: entity,
      });
    });
    toast("已添加六个双状态图标；请替换为实际HA实体");
    return;
  }
  const statusTemplates = {
    temperature: { text: "温度", binding: "sensor.living_room_temperature", progress_min: -10, progress_max: 50, show_value: "value", value_suffix: "°C", value_decimals: 1, progress_color: "#F26B5B" },
    humidity: { text: "湿度", binding: "sensor.living_room_humidity", progress_min: 0, progress_max: 100, show_value: "percent", progress_color: "#42A5F5" },
    brightness: { text: "亮度", binding: "sensor.living_room_illuminance", progress_min: 0, progress_max: 1000, show_value: "value", value_suffix: "lx", progress_color: "#F5C451" },
  };
  if (statusTemplates[name]) {
    add("progress_circle", { ...statusTemplates[name], width: 150, height: 150, border_width: 14, background_color: "#303841" });
    return;
  }
  if (name === "climate") {
    add("shape", { text: "空调", binding: "climate.living_room", binding_type: "state", state_mapping: true, state_on_value: "on", state_on_text: "开启", state_off_text: "关闭", width: 240, height: 92, background_color: "#16384A", border_color: "#4FC3F7", border_width: 2, radius: 8 });
    return;
  }
  if (name === "icons") {
    openIconPicker();
    return;
  }
  if (name === "settings") createSettingsPage();
  if (name === "gauge") add("progress_circle", { text: "数值", binding: "sensor.example_value", progress_min: 0, progress_max: 100, show_value: "value", width: 180, height: 180, border_width: 16 });
  if (name === "clock") add("shape", { text: "时间", binding: "device:current_time", binding_type: "state", width: 360, height: 82, font_size: 30, background_color: "#111820", border_width: 0 });
  if (name === "wifi") add("shape", { text: "WiFi", binding: "device:wifi_status", binding_type: "state", width: 220, height: 64, background_color: "#153A3D", border_width: 1 });
  if (name === "weather") add("shape", { text: "天气", binding: "weather.home", binding_type: "state", width: 300, height: 110, font_size: 26, background_color: "#24415A", border_width: 0, radius: 10 });
  if (name === "light") {
    add("shape", { text: "灯光", binding: "light.living_room", binding_type: "state", state_mapping: true, width: 240, height: 72, background_color: "#3B3520", state_on_color: "#B38A20", state_off_color: "#2A3037" });
    add("button", { text: "切换灯光", action: "light.toggle", action_entity: "light.living_room", width: 180, height: 54 });
  }
  if (name === "curtain") {
    add("button", { text: "打开窗帘", action: "cover.open_cover", action_entity: "cover.living_room", width: 180, height: 54 });
    add("button", { text: "关闭窗帘", action: "cover.close_cover", action_entity: "cover.living_room", width: 180, height: 54 });
  }
  if (name === "lock") add("shape", { text: "门锁", binding: "lock.front_door", binding_type: "state", state_mapping: true, state_on_value: "locked", state_on_text: "已锁", state_off_text: "未锁", width: 220, height: 72, state_on_color: "#245B3B", state_off_color: "#8B3D42" });
  if (name === "scene") ["回家", "离家", "观影", "睡眠"].forEach((text, index) => add("button", { text, action: "scene.turn_on", action_entity: `scene.${["home", "away", "movie", "sleep"][index]}`, width: 150, height: 58 }));
}

function applyTheme() {
  const presets = {
    graphite: { theme_accent: "#2F7DF6", theme_surface: "#182129", theme_text: "#FFFFFF", theme_radius: 8 },
    light: { theme_accent: "#1769AA", theme_surface: "#EEF2F5", theme_text: "#17202A", theme_radius: 6 },
    home: { theme_accent: "#00A67D", theme_surface: "#18302D", theme_text: "#F4FFFC", theme_radius: 10 },
    night: { theme_accent: "#D99B35", theme_surface: "#17191D", theme_text: "#F2EEE6", theme_radius: 4 },
  };
  const before = cloneProject(), preset = presets[state.project.theme_name] || presets.graphite;
  Object.assign(state.project, preset);
  state.project.widgets.filter((widget) => widgetOnPage(widget, state.activePageId)).forEach((widget) => {
    widget.text_color = preset.theme_text; widget.radius = preset.theme_radius;
    widget.background_color = ["button", "page_button"].includes(widget.kind) ? preset.theme_accent : preset.theme_surface;
  });
  $$('[data-project]').forEach((input) => { input.value = state.project[input.dataset.project] ?? ""; });
  recordHistory(before); renderCanvas(); markDirty(); saveProject(); toast("主题已应用到当前页面");
}

function createSettingsPage() {
  const existing = state.project.pages.find((page) => page.id === "device_settings");
  if (existing) {
    switchPage(existing.id);
    if (!window.confirm("本机设置页已存在。是否用新版布局替换该页面上的组件？")) return;
    state.project.widgets = state.project.widgets.filter((widget) => !widgetPages(widget).includes(existing.id));
  }
  const before = cloneProject();
  const page = existing || { id: "device_settings", name: "本机设置", background_color: "#0D1117", background_color_2: "#16212B", background_gradient: "vertical" };
  if (!existing) state.project.pages.push(page);
  Object.assign(page, { name: "本机设置", background_color: "#0B1016", background_color_2: "#17232D", background_gradient: "vertical" });
  state.activePageId = page.id; state.selectedId = null;
  recordHistory(before); renderPageTabs(); renderCanvas(); markDirty();
  newWidget("shape", { text: "设备设置", x: 28, y: 20, width: 744, height: 54, font_size: 25, text_align: "left", text_offset_x: 18, background_color: "#17232D", border_color: "#355064", border_width: 1, radius: 6 });
  const columns = [["设备状态", 28, 230], ["电池详情", 286, 230], ["显示控制", 544, 228]];
  columns.forEach(([text, x, width]) => newWidget("shape", { text, x, y: 88, width, height: 38, font_size: 16, text_align: "left", text_offset_x: 12, background_color: "#14202A", border_width: 0, radius: 5 }));
  const deviceRows = [["WiFi", "device:ssid", "state"], ["IP", "device:ip_address", "state"], ["信号", "device:wifi_signal", "number"], ["运行时间", "device:uptime", "number"], ["API", "device:api_status", "state"]];
  deviceRows.forEach(([text, binding, bindingType], index) => newWidget("shape", { text, binding, binding_type: bindingType, x: 28, y: 136 + index * 54, width: 230, height: 44, font_size: 14, text_align: "left", text_offset_x: 12, background_color: "#111920", border_color: "#293C49", border_width: 1, radius: 5 }));
  newWidget("battery", { text: "", binding: "device:battery_level", battery_display: "percent", x: 298, y: 138, width: 206, height: 46, font_size: 22, border_width: 5, background_color: "#26333D", progress_color: "#45C46A" });
  const batteryRows = [["电压", "device:battery_voltage", "V"], ["电流", "device:battery_current", "A"], ["功率", "device:battery_power", "W"], ["剩余", "device:battery_remaining", "h"]];
  batteryRows.forEach(([text, binding, suffix], index) => newWidget("shape", { text, binding, binding_type: "number", value_suffix: suffix, value_decimals: 2, x: 286, y: 194 + index * 54, width: 230, height: 44, font_size: 14, text_align: "left", text_offset_x: 12, background_color: "#111920", border_color: "#293C49", border_width: 1, radius: 5 }));
  newWidget("shape", { text: "亮度", x: 556, y: 136, width: 204, height: 24, font_size: 13, text_align: "left", background_opacity: 0, border_width: 0 });
  newWidget("slider", { text: "亮度", action: "device.brightness", x: 556, y: 164, width: 204, height: 40, progress_min: 10, progress_max: 100, progress_value: 70, progress_color: "#4DA3FF", background_color: "#293641" });
  newWidget("shape", { text: "自动息屏", x: 556, y: 216, width: 204, height: 24, font_size: 13, text_align: "left", background_opacity: 0, border_width: 0 });
  const timeoutValues = [0, 30, 60, 120, 300, 600, 1800];
  const timeoutIndex = Math.max(0, timeoutValues.indexOf(Number(state.project.auto_screen_off) || 0));
  newWidget("dropdown", { text: "息屏时间", action: "device.screen_timeout", x: 556, y: 244, width: 204, height: 44, control_options: "长亮\n30秒\n1分钟\n2分钟\n5分钟\n10分钟\n30分钟", control_selected: timeoutIndex, background_color: "#1B2934", border_color: "#3C586B", border_width: 1 });
  newWidget("button", { text: "立即息屏", action: "device.screen_off", x: 556, y: 306, width: 96, height: 44, background_color: "#303B45" });
  newWidget("button", { text: "安全模式", action: "device.safe_mode", x: 664, y: 306, width: 96, height: 44, background_color: "#66552D" });
  newWidget("button", { text: "重启设备", action: "device.restart", x: 556, y: 362, width: 204, height: 44, background_color: "#8C3940" });
  newWidget("shape", { text: "默认推荐 5 分钟", x: 556, y: 420, width: 204, height: 24, font_size: 12, text_color: "#91A4B3", background_opacity: 0, border_width: 0 });
  toast("已创建三栏设置页：设备、电池详情和显示控制");
}

function moveCurrentPage(offset) {
  const index = state.project.pages.findIndex((page) => page.id === state.activePageId), target = index + offset;
  if (target < 0 || target >= state.project.pages.length) return;
  const before = cloneProject();
  [state.project.pages[index], state.project.pages[target]] = [state.project.pages[target], state.project.pages[index]];
  recordHistory(before); renderPageTabs(); markDirty(); saveProject();
}

async function uploadImage(file) {
  if (!file) return;
  try {
    const dataUrl = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); });
    const result = await request("/api/upload", { method: "POST", body: JSON.stringify({ filename: file.name, data: dataUrl.split(",")[1] }) });
        const current = selectedWidget();
    const before = cloneProject();
    if (state.uploadMode === "content" && current) {
      current.content_asset_path = result.path; recordHistory(before); fillWidgetForm(); renderCanvas(); markDirty(); saveProject();
    } else if (state.uploadMode === "replace" && current?.kind === "image") {
      current.asset_path = result.path; recordHistory(before); fillWidgetForm(); renderCanvas(); markDirty(); saveProject();

    } else {
      const scale = Math.min(1, 420 / result.width, 280 / result.height);
      newWidget("image", { asset_path: result.path, width: Math.max(20, Math.round(result.width * scale)), height: Math.max(20, Math.round(result.height * scale)) });
    }
  } catch (error) { toast(error.message); }
  state.uploadMode = "new";
  $("#imageInput").value = "";
}

function markDirty() { state.dirty = true; storeRecoveryDraft(); $("#saveState").textContent = "未保存"; }

let saveTimer;
document.getElementById("exitStudioBtn").addEventListener("click", async () => {
  if (!window.confirm("保存并退出工作台？正在进行的编译、烧录和监视任务会被停止。")) return;
  const button = document.getElementById("exitStudioBtn");
  button.disabled = true;
  try {
    clearTimeout(saveTimer);
    await request("/api/project", { method: "POST", body: JSON.stringify(state.project) });
    await request("/api/exit", { method: "POST", body: JSON.stringify({ exit: true }) });
    state.dirty = false;
    clearRecoveryDraft();
    document.body.replaceChildren();
    const message = document.createElement("p");
    message.textContent = "工作台正在退出，后台任务将一并停止。可以关闭此页面。";
    document.body.append(message);
  } catch (error) {
    button.disabled = false;
    toast(error.message);
  }
});

function saveProject() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
                try { await request("/api/project", { method: "POST", body: JSON.stringify(state.project) }); state.dirty = false; clearRecoveryDraft(); $("#saveState").textContent = "已保存"; }


    catch (error) { $("#saveState").textContent = "保存失败"; toast(error.message); }
  }, 250);
}

async function exportProject() {
  try {
    const project = await request("/api/project/export");
    const blob = new Blob([JSON.stringify(project, null, 2)], { type: "application/json;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${project.device_name || "mijia-panel"}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
    toast("项目已导出，敏感密钥未包含在文件中");
  } catch (error) { toast(error.message); }
}

async function importProject(file) {
  if (!file) return;
  try {
    const raw = JSON.parse(await file.text());
    if (!window.confirm("导入项目会替换当前工作台内容，是否继续？")) return;
    await request("/api/project/import", { method: "POST", body: JSON.stringify({ project: raw }) });
    window.location.reload();
  } catch (error) { toast(`导入失败：${error.message}`); }
  $("#projectFileInput").value = "";
}

async function restoreProject() {
  try {
    const backups = await request("/api/backups");
    if (!backups.length) { toast("还没有可恢复的项目备份"); return; }
    const choices = backups.map((item, index) => `${index + 1}. ${item.label}`).join("\n");
    const input = window.prompt(`选择要恢复的备份编号：\n${choices}`, "1");
    if (input === null) return;
    const backup = backups[Number(input) - 1];
    if (!backup) { toast("备份编号无效"); return; }
    if (!window.confirm(`恢复 ${backup.label} 的项目备份？当前内容会先自动备份。`)) return;
    await request("/api/project/restore", { method: "POST", body: JSON.stringify({ name: backup.name }) });
    window.location.reload();
  } catch (error) { toast(`恢复失败：${error.message}`); }
}

async function generate() {
  try { const result = await request("/api/generate", { method: "POST", body: JSON.stringify(state.project) }); toast(`配置已生成：${result.path}`); return true; }
  catch (error) { toast(error.message); return false; }
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

async function analyzeResources() {
  try {
    await request("/api/project", { method: "POST", body: JSON.stringify(state.project) });
    const report = await request("/api/resources");
    const firmware = report.firmware.bytes ? `${formatBytes(report.firmware.bytes)} (${report.flash_percent}% / 16 MB)` : "尚未编译";
    const lines = [
      "资源分析",
      `图片：${report.images.count} 个，${formatBytes(report.images.bytes)}`,
      `字体：${report.fonts.file || "未使用"}，${formatBytes(report.fonts.bytes)}`,
      `配置：${report.yaml.file}，${formatBytes(report.yaml.bytes)}`,
      `固件：${firmware}`,
      ...(report.warnings.length ? ["", "提示：", ...report.warnings.map((warning) => `- ${warning}`)] : ["", "资源占用正常"]),
    ];
    $("#console").classList.remove("collapsed");
    $("#logOutput").textContent = lines.join("\n");
    $("#taskState").textContent = report.status === "ok" ? "分析完成" : "需要关注";
    $("#taskProgress").value = 100;
    toast(report.status === "ok" ? "资源分析完成" : "资源分析发现需要关注的项目");
  } catch (error) { toast(error.message); }
}


async function refreshPorts() {
  try {
    const ports = await request("/api/ports");
        const select = $("#portSelect"), current = select.value;
    select.innerHTML = '<option value="">选择串口</option>' + ports.map((item) => `<option value="${item.device}">${item.label}</option>`).join("");
    const currentPort = ports.find((item) => item.device === current);
    const preferred = ports.find((item) => /CH340|USB-SERIAL|CP210|ESP32/i.test(item.label));
    select.value = currentPort && !(/USB 串行设备/i.test(currentPort.label) && preferred && preferred.device !== current) ? current : preferred?.device || current;

  } catch (error) { toast(error.message); }
}

async function inspectDevice(showResult = true) {
  const port = $("#portSelect").value;
  if (!port) throw new Error("请选择要识别的串口");
  $("#deviceInfo").textContent = "识别中...";
  try {
    const info = await request("/api/device/info", { method: "POST", body: JSON.stringify({ port }) });
    $("#deviceInfo").textContent = `${info.chip} · ${info.flash}`;
    if (showResult) window.alert(`端口：${info.label}\n芯片：${info.chip}\nMAC：${info.mac}\nFlash：${info.flash}\n晶振：${info.crystal}\n序列号：${info.serial}`);
    return info;
  } catch (error) {
    $("#deviceInfo").textContent = "识别失败";
    throw error;
  }
}

async function inspectRuntime() {
  $("#deviceInfo").textContent = "查询版本中...";
  try {
    const address = $("#uploadMode").value === "ota" ? $("#otaTarget").value.trim() : "";
    const info = await request("/api/device/runtime", { method: "POST", body: JSON.stringify({ address }) });
    const matches = info.project_name === "mijia.display_studio" && info.project_version === state.project.firmware_version;
    $("#deviceInfo").textContent = `${info.project_version || "未知版本"} · ${matches ? "匹配" : "不匹配"}`;
    window.alert(`地址：${info.address}\n设备：${info.name}\nMAC：${info.mac}\n项目：${info.project_name}\n运行版本：${info.project_version}\n工作台版本：${state.project.firmware_version}\nESPHome：${info.esphome_version}\n\n${matches ? "版本匹配" : "版本不匹配"}`);
  } catch (error) {
    $("#deviceInfo").textContent = "版本查询失败";
    throw error;
  }
}




async function startTask(operation) {
  try {
    let confirmedPort = "";
    let confirmedTarget = "";
    if (operation === "upload") {
      if ($("#uploadMode").value === "ota") {
        const target = $("#otaTarget").value.trim() || `${state.project.device_name}.local`;
        $("#otaTarget").value = target;
        if (!window.confirm(`确认通过无线网络烧录？\n\n目标：${target}\n\n设备必须在线，烧录期间请勿断电。`)) return;
        confirmedTarget = target;
      } else {
        const info = await inspectDevice(false);
        const confirmed = window.confirm(`确认烧录到以下设备？\n\n端口：${info.label}\n芯片：${info.chip}\nMAC：${info.mac}\nFlash：${info.flash}\n\n烧录会覆盖设备当前固件。`);
        if (!confirmed) return;
        confirmedPort = info.port;
      }
    }
    await request("/api/task", { method: "POST", body: JSON.stringify({ operation, upload_mode: $("#uploadMode").value, port: $("#portSelect").value, ota_target: $("#otaTarget").value.trim(), confirmed_port: confirmedPort, confirmed_target: confirmedTarget, project: state.project }) });
    $("#console").classList.remove("collapsed"); pollTask();
  } catch (error) { toast(error.message); }
}


async function pollTask() {
  clearTimeout(state.taskTimer);
  try {
    const task = await request("/api/task");
    $("#taskState").textContent = task.running ? `${task.operation}中` : task.exit_code === null ? "空闲" : task.exit_code === 0 ? `${task.operation}完成` : `${task.operation}失败`;
    $("#taskProgress").value = task.progress;
    const log = $("#logOutput"); log.textContent = task.log || "等待任务..."; log.scrollTop = log.scrollHeight;
    if (task.running) state.taskTimer = setTimeout(pollTask, 700);
  } catch (error) { toast(error.message); }
}

async function loadKnownDevices(discover = false) {
  $("#deviceInfo").textContent = discover ? "发现设备中..." : "";
  try {
    const devices = await request(discover ? "/api/devices/discover" : "/api/devices", discover ? { method: "POST", body: "{}" } : {});
    $("#otaDevices").innerHTML = devices.map((item) => `<option value="${item.address}" label="${item.name}${item.mac ? ` · ${item.mac}` : ""}${item.version ? ` · ${item.version}` : ""}"></option>`).join("");
    if (discover) {
      $("#deviceInfo").textContent = `发现 ${devices.length} 台`;
      if (devices.length === 1) $("#otaTarget").value = devices[0].address;
    }
    return devices;
  } catch (error) {
    $("#deviceInfo").textContent = "设备发现失败";
    toast(error.message);
    return [];
  }
}

async function exportDiagnostics() {
  try {
    await saveProject();
    const report = await request("/api/diagnostics");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json;charset=utf-8" }));
    link.download = `diagnostics-${state.project.device_name}-${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
    toast("脱敏诊断报告已生成");
  } catch (error) { toast(error.message); }
}

async function serialAction(action, extra = {}) {
  const result = await request("/api/serial-monitor", { method: "POST", body: JSON.stringify({ action, ...extra }) });
  renderSerialMonitor(result);
  return result;
}

async function networkAction(action, extra = {}) {
  const result = await request("/api/network-monitor", { method: "POST", body: JSON.stringify({ action, ...extra }) });
  renderNetworkMonitor(result);
  return result;
}

function renderSerialMonitor(monitor) {
  const output = $("#serialOutput");
  output.textContent = monitor.log || monitor.error || "串口监视未启动";
  output.scrollTop = output.scrollHeight;
  $("#serialStart").textContent = monitor.running ? "停止" : "开始";
  $("#serialPause").textContent = monitor.paused ? "继续" : "暂停";
}

function renderNetworkMonitor(monitor) {
  const output = $("#networkOutput");
  output.textContent = monitor.log || monitor.error || "无线监视未启动";
  output.scrollTop = output.scrollHeight;
  $("#networkStart").textContent = monitor.running ? "停止" : "开始";
  $("#networkPause").textContent = monitor.paused ? "继续" : "暂停";
}

async function pollSerialMonitor() {
  clearTimeout(state.serialTimer);
  try {
    const monitor = await request("/api/serial-monitor");
    renderSerialMonitor(monitor);
    if (monitor.running) state.serialTimer = setTimeout(pollSerialMonitor, 500);
  } catch (error) { toast(error.message); }
}

async function pollNetworkMonitor() {
  clearTimeout(state.networkTimer);
  try {
    const monitor = await request("/api/network-monitor");
    renderNetworkMonitor(monitor);
    if (monitor.running) state.networkTimer = setTimeout(pollNetworkMonitor, 500);
  } catch (error) { toast(error.message); }
}

function selectConsoleTab(tab) {
  const serial = tab === "serial";
  const network = tab === "network";
  $$('[data-console-tab]').forEach((button) => button.classList.toggle("active", button.dataset.consoleTab === tab));
  $("#logOutput").classList.toggle("hidden", serial || network);
  $("#serialOutput").classList.toggle("hidden", !serial);
  $("#networkOutput").classList.toggle("hidden", !network);
  $("#serialControls").classList.toggle("hidden", !serial);
  $("#networkControls").classList.toggle("hidden", !network);
  $("#taskState").classList.toggle("hidden", serial || network);
  $("#taskProgress").classList.toggle("hidden", serial || network);
  if (serial) pollSerialMonitor(); else if (network) {
    if (!$("#networkTarget").value) $("#networkTarget").value = $("#otaTarget").value.trim() || `${state.project.device_name}.local`;
    pollNetworkMonitor();
  } else pollTask();
}

async function copyLog(outputId, emptyText) {
  const value = $(outputId).textContent;
  if (!value || value === emptyText) { toast("暂无可复制的日志"); return; }
  try {
    await navigator.clipboard.writeText(value);
  } catch (_) {
    const field = document.createElement("textarea");
    field.value = value;
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.append(field);
    field.select();
    const copied = document.execCommand("copy");
    field.remove();
    if (!copied) throw new Error("浏览器未允许访问剪贴板");
  }
  toast("日志已复制");
}

function initializeCollapsibleSections() {
  ["#projectForm", "#widgetForm"].forEach((formSelector) => {
    $$(formSelector + " .form-section").forEach((section, index) => {
      const heading = section.querySelector("h2");
      if (!heading || heading.dataset.collapsible) return;
      heading.dataset.collapsible = "true";
      heading.tabIndex = 0;
      heading.setAttribute("role", "button");
      heading.setAttribute("aria-expanded", index < 2 ? "true" : "false");
      section.classList.toggle("collapsed", index >= 2);
      const toggle = () => {
        section.classList.toggle("collapsed");
        heading.setAttribute("aria-expanded", String(!section.classList.contains("collapsed")));
      };
      heading.addEventListener("click", toggle);
      heading.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggle(); }
      });
    });
  });
}

function bindEvents() {
  initializeCollapsibleSections();
  $("#addHaEntityControl").addEventListener("click", () => openHaControlWizard());
  $$('.tool[data-kind]').forEach((button) => button.addEventListener("click", () => newWidget(button.dataset.kind, { shape_type: button.dataset.shape })));
  $$('[data-template]').forEach((button) => button.addEventListener("click", () => addTemplate(button.dataset.template)));
  $("#replaceImage").addEventListener("click", () => { state.uploadMode = "replace"; $("#imageInput").click(); });
  $("#attachImage").addEventListener("click", () => { state.uploadMode = "content"; $("#imageInput").click(); });
    $("#removeContentImage").addEventListener("click", () => { const widget = selectedWidget(); if (!widget) return; const before = cloneProject(); widget.content_asset_path = ""; recordHistory(before); fillWidgetForm(); renderCanvas(); markDirty(); saveProject(); });

  $("#imageInput").addEventListener("change", (event) => uploadImage(event.target.files[0]));
  $("#videoTool").addEventListener("click", () => toast("该板卡可用静态图片；ESPHome没有通用MP4/H.264视频解码支持。"));
  $("#projectSettings").addEventListener("click", () => selectWidget(null));
  $("#saveTemplateBtn").addEventListener("click", saveUserTemplate);
  $("#loadTemplateBtn").addEventListener("click", loadUserTemplate);
  $("#applyThemeBtn").addEventListener("click", applyTheme);
  $("#exportProject").addEventListener("click", exportProject);
  $("#importProject").addEventListener("click", () => $("#projectFileInput").click());
  $("#projectFileInput").addEventListener("change", (event) => importProject(event.target.files[0]));
  $("#restoreProject").addEventListener("click", restoreProject);
  $("#refreshPorts").addEventListener("click", refreshPorts);
  $("#portSelect").addEventListener("change", () => { $("#deviceInfo").textContent = ""; });
  $("#uploadMode").addEventListener("change", () => {
    const wireless = $("#uploadMode").value === "ota";
    $("#portSelect").classList.toggle("hidden", wireless);
    $("#otaTarget").classList.toggle("hidden", !wireless);
    $("#inspectDeviceBtn").classList.toggle("hidden", wireless);
    $("#discoverDevicesBtn").classList.toggle("hidden", !wireless);
    $("#flashBtn").textContent = wireless ? "无线烧录" : "烧录";
    if (wireless && !$("#otaTarget").value) $("#otaTarget").value = `${state.project.device_name}.local`;
    $("#deviceInfo").textContent = "";
    if (wireless) loadKnownDevices(true);
  });
  $("#discoverDevicesBtn").addEventListener("click", () => loadKnownDevices(true));
  $("#inspectDeviceBtn").addEventListener("click", () => inspectDevice().catch((error) => toast(error.message)));
  $("#inspectRuntimeBtn").addEventListener("click", () => inspectRuntime().catch((error) => toast(error.message)));


    $("#activePageSelect").addEventListener("change", (event) => switchPage(event.target.value));
  $$('[data-page]').forEach((input) => input.addEventListener("input", () => {
    const page = activePage(); if (!page) return;
    const before = cloneProject(); page[input.dataset.page] = input.value;
    recordHistory(before); renderPageTabs(); renderCanvas(); markDirty(); saveProject();
  }));

    $("#deletePageBtn").addEventListener("click", () => {
    if (state.project.pages.length <= 1) { toast("项目至少需要保留一个界面"); return; }
    const page = activePage();
    const destination = state.project.pages.find((item) => item.id !== page.id);
    if (!page || !destination || !window.confirm(`删除界面“${page.name}”？该界面上的组件会移动到“${destination.name}”。`)) return;
    const before = cloneProject();
    state.project.widgets.forEach((widget) => {
      if (widgetOnPage(widget, page.id)) {
        widget.pages = widgetPages(widget).map((pageId) => pageId === page.id ? destination.id : pageId);
        widget.page = widget.pages[0];
      }
      if (widget.kind === "page_button" && widget.target_page === page.id) widget.target_page = destination.id;
    });
    state.project.pages = state.project.pages.filter((item) => item.id !== page.id);
    if (state.project.default_page === page.id) state.project.default_page = destination.id;
    state.activePageId = destination.id;
    state.selectedId = null;
    recordHistory(before); renderPageTabs(); renderCanvas(); selectWidget(null); markDirty(); saveProject();
  });

  $("#duplicatePageBtn").addEventListener("click", () => {
    const source = activePage(); if (!source) return;
    const before = cloneProject(), id = `page_${Date.now().toString(36)}`;
    state.project.pages.splice(state.project.pages.indexOf(source) + 1, 0, { ...source, id, name: `${source.name} 副本` });
    const copies = state.project.widgets.filter((widget) => widgetOnPage(widget, source.id)).map((widget, index) => ({ ...JSON.parse(JSON.stringify(widget)), id: `widget_${Date.now().toString(36)}_${index}`, page: id, pages: [id], locked: false }));
    state.project.widgets.push(...copies); state.activePageId = id; state.selectedId = null;
    recordHistory(before); renderPageTabs(); renderCanvas(); markDirty(); saveProject();
  });
  $("#movePageLeftBtn").addEventListener("click", () => moveCurrentPage(-1));
  $("#movePageRightBtn").addEventListener("click", () => moveCurrentPage(1));
  $("#defaultPage").addEventListener("change", () => {
    if (!$("#defaultPage").checked) { $("#defaultPage").checked = true; return; }
    const before = cloneProject(); state.project.default_page = state.activePageId;
    recordHistory(before); markDirty(); saveProject();
  });

  $("#addPageBtn").addEventListener("click", () => {

    const number = state.project.pages.length + 1;
    const name = window.prompt("界面名称", `界面${number}`);
    if (!name) return;
        const page = { id: `page_${Date.now().toString(36)}`, name, background_color: "#080B10", background_color_2: "#080B10", background_gradient: "none" };
    const before = cloneProject();
    state.project.pages.push(page); switchPage(page.id); recordHistory(before); markDirty(); saveProject();

  });
    $("#deleteBtn").addEventListener("click", () => { if (!state.selectedIds.length) return; const before = cloneProject(), ids = new Set(state.selectedIds); state.project.widgets = state.project.widgets.filter((item) => !ids.has(item.id)); selectWidget(null); recordHistory(before); markDirty(); saveProject(); });

  $("#copyBtn").addEventListener("click", copyComponentsToClipboard);
  $("#pasteBtn").addEventListener("click", pasteCopiedWidgets);
  $("#copyStyleBtn").addEventListener("click", copySelectedStyle);
  $("#pasteStyleBtn").addEventListener("click", pasteCopiedStyle);
  $("#forceCenterBtn").addEventListener("click", () => {
    const widget = selectedWidget(); if (!widget) return;
  widget.trend_mode ||= "line";
  widget.matrix_buttons ||= [];
    const before = cloneProject();
    widget.text_align = "center"; widget.text_offset_x = 0; widget.text_offset_y = 0; widget.icon_offset_x = 0; widget.icon_offset_y = 0;
    recordHistory(before); fillWidgetForm(); renderCanvas(); markDirty(); saveProject();
  });
  $("#attachShapeIcon").addEventListener("click", () => {
    const widget = selectedWidget(); if (widget) openIconPicker(undefined, widget.id);
  });
  $("#selectStateOnIcon").addEventListener("click", () => { const widget = selectedWidget(); if (widget) openIconPicker("人员与作息", widget.id, "on"); });
  $("#selectStateOffIcon").addEventListener("click", () => { const widget = selectedWidget(); if (widget) openIconPicker("人员与作息", widget.id, "off"); });
  $("#removeShapeIcon").addEventListener("click", () => {
    const widget = selectedWidget(); if (!widget || !widget.icon_glyph) return;
    const before = cloneProject(); widget.icon_name = ""; widget.icon_glyph = "";
    recordHistory(before); fillWidgetForm(); renderCanvas(); markDirty(); saveProject();
  });
  $("#lockBtn").addEventListener("click", () => { const widget = selectedWidget(); if (!widget) return; const before = cloneProject(); widget.locked = !widget.locked; recordHistory(before); renderCanvas(); markDirty(); saveProject(); });
  $("#hideBtn").addEventListener("click", () => { const widget = selectedWidget(); if (!widget) return; const before = cloneProject(); widget.hidden = !widget.hidden; recordHistory(before); renderCanvas(); markDirty(); saveProject(); });
  $("#groupBtn").addEventListener("click", () => { if (state.selectedIds.length < 2) return; const before = cloneProject(), group = `group_${Date.now().toString(36)}`; selectedWidgets().forEach((widget) => { widget.group_id = group; }); recordHistory(before); renderCanvas(); markDirty(); saveProject(); });
  $("#ungroupBtn").addEventListener("click", () => { const before = cloneProject(); selectedWidgets().forEach((widget) => { widget.group_id = ""; }); recordHistory(before); renderCanvas(); markDirty(); saveProject(); });
  $("#layerSearch").addEventListener("input", renderLayerTree);
  $("#screen").addEventListener("pointerdown", beginMarquee);
  $("#screen").addEventListener("wheel", (event) => { if (state.project.pages.length < 2) return; event.preventDefault(); cyclePage(event.deltaY > 0 ? 1 : -1); }, { passive: false });
  window.addEventListener("pointermove", movePointer);
  window.addEventListener("pointerup", endPointer);
  window.addEventListener("pointercancel", endPointer);
    $$('[data-project]').forEach((input) => input.addEventListener("input", () => {
      const before = cloneProject();
      let value = input.value;
      if (input.dataset.projectType === "boolean") value = value === "true";
      else if (input.dataset.projectType === "number") value = Number(value);
      else if (input.type === "number") value = Number(value);
      state.project[input.dataset.project] = value; recordHistory(before); markDirty(); saveProject();
    }));

    $$('[data-widget]').forEach((input) => input.addEventListener("input", () => {
    const widget = selectedWidget(); if (!widget) return;
    const before = cloneProject();
    widget[input.dataset.widget] = input.dataset.widgetType === "boolean" ? input.value === "true" : input.value;

    if (input.dataset.widget === "pages") {
      widget.pages = [...input.selectedOptions].map((option) => option.value);
      if (!widget.pages.length) widget.pages = [state.activePageId];
      widget.page = widget.pages[0];
    }
        if (input.dataset.widget === "shape_type") clamp(widget);
    if (input.dataset.widget === "battery_style") {
      if (widget.battery_style === "vertical") { widget.width = 110; widget.height = 240; }
      else if (widget.battery_style === "ring") { widget.width = 180; widget.height = 180; }
      else { widget.width = 300; widget.height = 86; }
    }
    if (input.dataset.widget === "battery_display") {
      if (widget.battery_display === "full") { widget.width = Math.max(widget.width, 280); widget.height = Math.max(widget.height, 60); }
      else if (widget.battery_display === "percent") { widget.width = Math.max(widget.width, 90); widget.height = Math.max(widget.height, 32); }
      widget.x = Math.min(widget.x, 800 - widget.width); widget.y = Math.min(widget.y, 480 - widget.height);
    }
    recordHistory(before); fillWidgetForm(); renderCanvas(); markDirty(); saveProject();

  }));
  $$('[data-widget-number]').forEach((input) => input.addEventListener("input", () => {
        const widget = selectedWidget(); if (!widget) return;
    const before = cloneProject();
    const property = input.dataset.widgetNumber, value = Number(input.value);

    widget[property] = value;
    if (widget.kind === "shape" && ["ellipse", "circle"].includes(widget.shape_type)) {
      if (property === "width") widget.ellipse_radius_x = value / 2;
      if (property === "height") widget.ellipse_radius_y = value / 2;
    }
        recordHistory(before); clamp(widget); fillWidgetForm(); renderCanvas(); markDirty(); saveProject();

  }));
  [$("#projectForm"), $("#widgetForm")].forEach((form) => form.addEventListener("wheel", (event) => {
    const input = event.target.matches?.('input[type="number"], input[type="range"]') ? event.target : null;
    if (!input || input.disabled || document.activeElement !== input) return;
    event.preventDefault(); event.stopPropagation();
    const step = Number(input.step) || 1, min = input.min === "" ? -Infinity : Number(input.min), max = input.max === "" ? Infinity : Number(input.max);
    input.value = Math.max(min, Math.min(max, (Number(input.value) || 0) + (event.deltaY < 0 ? step : -step)));
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }, { passive: false }));
  $$('[data-layer]').forEach((button) => button.addEventListener("click", () => {
        const widget = selectedWidget(); if (!widget) return;
    const before = cloneProject();
    const siblings = state.project.widgets.filter((item) => widgetOnPage(item, state.activePageId)).sort((a, b) => a.z_index - b.z_index);

    siblings.forEach((item, index) => { item.z_index = index + 1; });
    const index = siblings.indexOf(widget), action = button.dataset.layer;
    if (action === "top") widget.z_index = siblings.length + 1;
    if (action === "bottom") widget.z_index = 0;
    if (action === "up" && index < siblings.length - 1) [widget.z_index, siblings[index + 1].z_index] = [siblings[index + 1].z_index, widget.z_index];
        if (action === "down" && index > 0) [widget.z_index, siblings[index - 1].z_index] = [siblings[index - 1].z_index, widget.z_index];
    recordHistory(before); renderCanvas(); markDirty(); saveProject();

  }));
  $$('[data-align]').forEach((button) => button.addEventListener("click", () => {
    const widgets = selectedWidgets().filter((widget) => !widget.locked); if (!widgets.length) return;
    const before = cloneProject(), action = button.dataset.align;
    const anchor = widgets[0];
    widgets.forEach((widget) => {
      if (action === "left") widget.x = widgets.length > 1 ? anchor.x : 0;
      if (action === "center") widget.x = widgets.length > 1 ? Math.round(anchor.x + (anchor.width - widget.width) / 2) : Math.round((800 - widget.width) / 2);
      if (action === "right") widget.x = widgets.length > 1 ? anchor.x + anchor.width - widget.width : 800 - widget.width;
      if (action === "top") widget.y = widgets.length > 1 ? anchor.y : 0;
      if (action === "middle") widget.y = widgets.length > 1 ? Math.round(anchor.y + (anchor.height - widget.height) / 2) : Math.round((480 - widget.height) / 2);
      if (action === "bottom") widget.y = widgets.length > 1 ? anchor.y + anchor.height - widget.height : 480 - widget.height;
      clamp(widget);
    });
    recordHistory(before); fillWidgetForm(); renderCanvas(); markDirty(); saveProject();
  }));
  $$('[data-distribute]').forEach((button) => button.addEventListener("click", () => {
    const horizontal = button.dataset.distribute === "horizontal";
    const widgets = selectedWidgets().filter((widget) => !widget.locked).sort((a, b) => horizontal ? a.x - b.x : a.y - b.y);
    if (widgets.length < 3) { toast("等间距分布至少需要选择3个组件"); return; }
    const before = cloneProject(), first = widgets[0], last = widgets.at(-1);
    const used = widgets.reduce((sum, widget) => sum + (horizontal ? widget.width : widget.height), 0);
    const span = horizontal ? last.x + last.width - first.x : last.y + last.height - first.y;
    const gap = (span - used) / (widgets.length - 1); let cursor = horizontal ? first.x : first.y;
    widgets.forEach((widget) => { if (horizontal) widget.x = Math.round(cursor); else widget.y = Math.round(cursor); cursor += (horizontal ? widget.width : widget.height) + gap; });
    recordHistory(before); renderCanvas(); markDirty(); saveProject();
  }));
  $$('.segmented button').forEach((button) => button.addEventListener("click", () => { state.zoom = Number(button.dataset.zoom); $$('.segmented button').forEach((item) => item.classList.toggle("active", item === button)); $("#screenShell").style.setProperty("--zoom", state.zoom); renderCanvas(); }));
  $("#undoBtn").addEventListener("click", undo);
  $("#redoBtn").addEventListener("click", redo);
  $("#generateBtn").addEventListener("click", generate); $("#validateBtn").addEventListener("click", () => startTask("validate")); $("#resourceBtn").addEventListener("click", analyzeResources); $("#diagnosticBtn").addEventListener("click", exportDiagnostics); $("#compileBtn").addEventListener("click", () => startTask("compile")); $("#flashBtn").addEventListener("click", () => startTask("upload"));
  $("#toggleConsole").addEventListener("click", () => { const collapsed = $("#console").classList.toggle("collapsed"); $("#toggleConsole").textContent = collapsed ? "展开" : "收起"; });
  $$('[data-console-tab]').forEach((button) => button.addEventListener("click", () => selectConsoleTab(button.dataset.consoleTab)));
  $("#serialStart").addEventListener("click", async () => {
    try {
      const current = await request("/api/serial-monitor");
      if (current.running) await serialAction("stop");
      else await serialAction("start", { port: $("#portSelect").value, baudrate: Number($("#serialBaud").value) });
      pollSerialMonitor();
    } catch (error) { toast(error.message); }
  });
  $("#serialPause").addEventListener("click", () => serialAction("pause").catch((error) => toast(error.message)));
  $("#serialClear").addEventListener("click", () => serialAction("clear").catch((error) => toast(error.message)));
  $("#serialLevel").addEventListener("change", () => serialAction("configure", { level: $("#serialLevel").value }).catch((error) => toast(error.message)));
  $("#serialSearch").addEventListener("input", () => serialAction("configure", { search: $("#serialSearch").value }).catch((error) => toast(error.message)));
  $("#serialIna226").addEventListener("click", async () => {
    try {
      selectConsoleTab("serial");
      $("#serialSearch").value = "0x40";
      const monitor = await serialAction("configure", { search: "0x40", level: "all" });
      if (!monitor.running) {
        await serialAction("start", { port: $("#portSelect").value, baudrate: Number($("#serialBaud").value) });
      }
      toast("正在查找INA226地址 0x40；请重启开发板，日志出现 Found i2c device 即表示模块在线");
    } catch (error) { toast(error.message); }
  });
  $("#serialCopy").addEventListener("click", () => copyLog("#serialOutput", "串口监视未启动").catch((error) => toast(error.message)));
  $("#serialSave").addEventListener("click", async () => {
    try {
      const monitor = await request("/api/serial-monitor");
      const link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([monitor.log], { type: "text/plain;charset=utf-8" }));
      link.download = `serial-${monitor.port || "log"}-${Date.now()}.txt`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (error) { toast(error.message); }
  });
  $("#networkStart").addEventListener("click", async () => {
    try {
      const current = await request("/api/network-monitor");
      if (current.running) await networkAction("stop");
      else {
        const target = $("#networkTarget").value.trim() || $("#otaTarget").value.trim() || `${state.project.device_name}.local`;
        $("#networkTarget").value = target;
        await networkAction("start", { target });
      }
      pollNetworkMonitor();
    } catch (error) { toast(error.message); }
  });
  $("#networkPause").addEventListener("click", () => networkAction("pause").catch((error) => toast(error.message)));
  $("#networkClear").addEventListener("click", () => networkAction("clear").catch((error) => toast(error.message)));
  $("#networkLevel").addEventListener("change", () => networkAction("configure", { level: $("#networkLevel").value }).catch((error) => toast(error.message)));
  $("#networkSearch").addEventListener("input", () => networkAction("configure", { search: $("#networkSearch").value }).catch((error) => toast(error.message)));
  $("#networkIna226").addEventListener("click", async () => {
    try {
      selectConsoleTab("network");
      $("#networkSearch").value = "0x40";
      const monitor = await networkAction("configure", { search: "0x40", level: "all" });
      if (!monitor.running) {
        const target = $("#networkTarget").value.trim() || $("#otaTarget").value.trim() || `${state.project.device_name}.local`;
        $("#networkTarget").value = target;
        await networkAction("start", { target });
      }
      toast("正在无线查找 INA226 地址 0x40；请重启开发板，出现 Found i2c device 即表示模块在线");
    } catch (error) { toast(error.message); }
  });
  $("#networkCopy").addEventListener("click", () => copyLog("#networkOutput", "无线监视未启动").catch((error) => toast(error.message)));
    window.addEventListener("keydown", (event) => {
    const editing = ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName) || document.activeElement.isContentEditable;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") { event.preventDefault(); event.shiftKey ? redo() : undo(); return; }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") { event.preventDefault(); redo(); return; }
    if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "c" && state.selectedId && !editing) { event.preventDefault(); copySelectedStyle(); return; }
    if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "v" && state.selectedId && !editing) { event.preventDefault(); pasteCopiedStyle(); return; }
    if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === "c" && state.selectedId && !editing) { event.preventDefault(); copyComponentsToClipboard(); return; }
    if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === "v" && !editing) { event.preventDefault(); pasteCopiedWidgets(); return; }
    if ((event.key === "Delete" || event.key === "Backspace") && state.selectedId && !editing) $("#deleteBtn").click();
    if (state.selectedId && !editing && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
      event.preventDefault();
      const before = cloneProject(), step = event.shiftKey ? 10 : 1;
      const dx = event.key === "ArrowLeft" ? -step : event.key === "ArrowRight" ? step : 0;
      const dy = event.key === "ArrowUp" ? -step : event.key === "ArrowDown" ? step : 0;
      selectedWidgets().filter((widget) => !widget.locked).forEach((widget) => { widget.x += dx; widget.y += dy; clamp(widget); });
      recordHistory(before); fillWidgetForm(); renderCanvas(); markDirty(); saveProject();
    }
  });

}

async function initialize() {
  try {
        const serverProject = await request("/api/project");
    state.project = takeRecoveryDraft(serverProject);

        state.project.pages ||= [{ id: "main_page", name: "主界面", background_color: "#080B10", background_color_2: "#080B10", background_gradient: "none" }];
    state.project.pages.forEach((page) => { const loaded = { ...page }; Object.assign(page, { background_color: "#080B10", background_color_2: page.background_color || "#080B10", background_gradient: "none" }, loaded); });
    state.project.default_page = state.project.pages.some((page) => page.id === state.project.default_page) ? state.project.default_page : state.project.pages[0].id;
    Object.assign(state.project, { battery_monitor: false, battery_chip: "ina219", battery_address: "0x40", battery_full_voltage: 4.2, battery_low_voltage: 3.3, battery_voltage_offset: 0, battery_sample_interval: 10, battery_shunt_resistance: 0.1, battery_max_current: 3.2, battery_capacity_mah: 3000, battery_capacity_mwh: 11100, battery_initial_percent: 100, battery_current_inverted: false, bluetooth_proxy: false, auto_screen_off: 300, theme_name: "graphite", theme_accent: "#2F7DF6", theme_surface: "#182129", theme_text: "#FFFFFF", theme_radius: 8 }, { ...state.project });

    for (const widget of state.project.widgets) {
      if (widget.kind === "label") widget.kind = "shape";
      // State-bound sensors use the unified basic surface editor. Older
      // projects stored these as icon widgets, which hid geometry and image
      // controls even though they had the same state/interaction behavior.
      if (widget.kind === "icon" && String(widget.binding || "").startsWith("sensor.")) {
        widget.kind = "shape";
      }
      if (widget.binding === "device:wifi_signal" && widget.binding_type === "state") widget.binding = "device:wifi_status";
      const loadedWidget = { ...widget };
            Object.assign(widget, {
        z_index: 1, image_fit: "fill", image_offset_x: 50, image_offset_y: 50, shape_type: "rectangle",
                border_color: "#FFFFFF", border_width: 0, radius: 4, content_asset_path: "", line_angle: 0, background_opacity: 100, opacity: 100, text_opacity: 100, border_opacity: 100, image_opacity: 100, image_tint: "#FFFFFF", image_tint_opacity: 0, image_grayscale: 0, image_brightness: 100, image_blur: 0,

        line_length: 160, ellipse_radius_x: Math.max(10, (widget.width || 160) / 2), ellipse_radius_y: Math.max(10, (widget.height || 100) / 2),

        text_align: "center", text_offset_x: 0, text_offset_y: 0, auto_fit_text: true, icon_name: "", icon_glyph: "", state_icon_enabled: false, state_icon_on_name: "", state_icon_on_glyph: "", state_icon_off_name: "", state_icon_off_glyph: "", icon_size: 32, icon_offset_x: 0, icon_offset_y: 0, click_effect: "scale", tap_mode: widget.kind === "page_button" ? "page" : widget.kind === "button" ? "ha" : "none", binding_type: "number", progress_min: 0, progress_max: 100, progress_value: 50,
        progress_color: "#2F7DF6", show_value: "percent", value_suffix: "", value_decimals: 0, battery_style: "horizontal", battery_display: "percent", battery_low_color: "#E5534B", battery_warning_color: "#F5A623", battery_charge_color: "#45C46A", battery_discharge_color: "#2F7DF6", trend_axis_color: "#AEB7C2", group_id: "", state_mapping: false, state_on_value: "on", state_on_text: "开启", state_off_text: "关闭", state_on_color: "#45C46A", state_off_color: "#58616B", state_on_bg_opacity: 100, state_off_bg_opacity: 72, state_visual: "color", state_preview: "off", visibility_mode: "always", visible_state: "on", locked: false, hidden: false,
      }, loadedWidget);
      widget.pages = widgetPages(widget);
      widget.page = widget.pages[0];
      if (!widget.page) widget.page = state.project.pages[0].id;
      if (widget.kind === "page_button" && !state.project.pages.some((page) => page.id === widget.target_page)) {
        widget.target_page = state.project.pages.find((page) => page.id !== widget.page)?.id || widget.page;
      }

    }
    state.activePageId = state.project.pages[0].id;
    $$('[data-project]').forEach((input) => { input.value = state.project[input.dataset.project] ?? ""; });
    bindEvents(); initializeRangeValues(); renderUserTemplates(); renderPageTabs(); renderCanvas(); updateHistoryButtons(); refreshPorts(); pollTask();
    if (state.project !== serverProject) { markDirty(); saveProject(); }

  } catch (error) { toast(error.message); }
}
initialize();
