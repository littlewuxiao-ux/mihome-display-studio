const state = { project: null, selectedId: null, activePageId: "main_page", zoom: 1, dirty: false, taskTimer: null, pointer: null, uploadMode: "new" };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

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

function selectedWidget() {
  return state.project?.widgets.find((item) => item.id === state.selectedId) || null;
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
}

function progressPercent(widget) {
  return Math.max(0, Math.min(100, (widget.progress_value - widget.progress_min) * 100 / (widget.progress_max - widget.progress_min)));
}

function appendEditableText(node, widget, text) {
  const label = document.createElement("span");
  label.className = "widget-text"; label.textContent = text;
  label.style.textAlign = widget.text_align;
  if (widget.id === state.selectedId) {
    label.contentEditable = "true";
    label.addEventListener("pointerdown", (event) => event.stopPropagation());
    label.addEventListener("focus", () => { label.textContent = widget.text; });
    label.addEventListener("input", () => { widget.text = label.innerText.replace(/\n/g, " "); $('[data-widget="text"]').value = widget.text; markDirty(); });
    label.addEventListener("blur", () => { renderCanvas(); saveProject(); });
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
  $("#widgetPage").innerHTML = options;
  $('[data-widget="target_page"]').innerHTML = options;
}

function switchPage(pageId) {
  if (!state.project.pages.some((page) => page.id === pageId)) return;
  state.activePageId = pageId;
  state.selectedId = null;
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
  screen.style.backgroundColor = page?.background_color || "#080B10";
  screen.replaceChildren();
  const widgets = state.project.widgets.filter((widget) => widget.page === state.activePageId).sort((a, b) => a.z_index - b.z_index);
  for (const widget of widgets) {
    clamp(widget);
    const node = document.createElement("div");
    node.className = `canvas-widget ${widget.kind} shape-${widget.shape_type} effect-${widget.click_effect}${widget.id === state.selectedId ? " selected" : ""}`;
    node.dataset.id = widget.id;
    Object.assign(node.style, {
      left: `${widget.x * state.zoom}px`, top: `${widget.y * state.zoom}px`,
      width: `${widget.width * state.zoom}px`, height: `${widget.height * state.zoom}px`,
      color: widget.text_color, backgroundColor: widget.kind === "image" ? "transparent" : widget.background_color,
      borderColor: widget.border_color, borderWidth: `${widget.border_width * state.zoom}px`,
      borderRadius: ["ellipse", "circle"].includes(widget.shape_type) ? "50%" : `${widget.radius * state.zoom}px`,
      fontSize: `${widget.font_size * state.zoom}px`, zIndex: widget.z_index,
    });
    if (widget.kind === "shape" && widget.shape_type === "line") {
      node.style.background = "transparent"; node.style.border = "0"; node.style.overflow = "visible";
      const line = document.createElement("i"); line.className = "shape-line-segment";
      line.style.width = `${widget.line_length * state.zoom}px`; line.style.height = `${Math.max(1, widget.border_width) * state.zoom}px`;
      line.style.background = widget.border_color; line.style.transform = `rotate(${widget.line_angle}deg)`;
      node.append(line);
    } else if (widget.kind === "progress_circle") {
      const percent = progressPercent(widget);
      node.style.border = "0"; node.style.background = `conic-gradient(${widget.progress_color} ${percent}%, ${widget.background_color} 0)`;
      const hole = document.createElement("i"); hole.className = "progress-hole"; node.append(hole);
    } else if (widget.kind === "progress_bar") {
      const fill = document.createElement("i"); fill.className = "progress-fill"; fill.style.width = `${progressPercent(widget)}%`; fill.style.background = widget.progress_color; node.append(fill);
    } else if (widget.kind === "image") {
      const image = document.createElement("img");
      image.src = assetUrl(widget.asset_path); image.alt = widget.text || "图片";
      image.style.objectFit = widget.image_fit === "cover" ? "cover" : widget.image_fit === "contain" ? "contain" : "fill";
      image.style.objectPosition = `${widget.image_offset_x}% ${widget.image_offset_y}%`;
      node.append(image);
    } else if (widget.content_asset_path) {
      const image = document.createElement("img");
      image.className = "content-image"; image.src = assetUrl(widget.content_asset_path);
      image.style.objectFit = widget.image_fit === "cover" ? "cover" : widget.image_fit === "contain" ? "contain" : "fill";
      image.style.objectPosition = `${widget.image_offset_x}% ${widget.image_offset_y}%`;
      node.append(image);
    }
    let displayText = widget.binding ? `${widget.text || "实体"}  --` : widget.text;
    if (["progress_circle", "progress_bar"].includes(widget.kind)) displayText = widget.binding ? `${widget.text || "状态"} --` : `${widget.text ? `${widget.text} ` : ""}${widget.show_value === "percent" ? `${Math.round(progressPercent(widget))}%` : `${widget.progress_value}`}`;
    appendEditableText(node, widget, displayText);
    if (widget.id === state.selectedId) {
      const handle = document.createElement("span"); handle.className = "resize-handle"; node.append(handle);
    }
    node.addEventListener("pointerdown", beginPointerAction);
    screen.append(node);
  }
  const selected = selectedWidget();
  const estimateAsset = (path, widget) => path ? widget.width * widget.height * (/\.(png|webp)$/i.test(path) ? 3 : 2) : 0;
  const imageBytes = state.project.widgets.reduce((total, widget) => total + estimateAsset(widget.asset_path, widget) + estimateAsset(widget.content_asset_path, widget), 0);
  const mediaLabel = `图片约 ${(imageBytes / 1048576).toFixed(1)} MB${imageBytes > 6 * 1048576 ? "，建议减少" : ""}`;
  $("#selectionInfo").textContent = selected ? `${selected.text || "组件"} · ${selected.x}, ${selected.y} · ${selected.width} × ${selected.height}` : mediaLabel;
  $("#deleteBtn").disabled = !selected;
}

function beginPointerAction(event) {
  event.preventDefault();
  const id = event.currentTarget.dataset.id;
  const resizing = event.target.classList.contains("resize-handle");
  const wasSelected = state.selectedId === id;
  if (!wasSelected) selectWidget(id);
  const widget = selectedWidget();
  state.pointer = { id, resizing, wasSelected, moved: false, x: event.clientX, y: event.clientY, wx: widget.x, wy: widget.y, width: widget.width, height: widget.height };
}

function movePointer(event) {
  if (!state.pointer) return;
  const widget = selectedWidget();
  if (!widget || widget.id !== state.pointer.id) return;
  const dx = (event.clientX - state.pointer.x) / state.zoom;
  const dy = (event.clientY - state.pointer.y) / state.zoom;
  state.pointer.moved ||= Math.abs(dx) + Math.abs(dy) > 2;
  if (state.pointer.resizing) {
    const nextWidth = Math.round(state.pointer.width + dx), nextHeight = Math.round(state.pointer.height + dy);
    if (widget.kind === "shape" && ["ellipse", "circle"].includes(widget.shape_type)) {
      widget.ellipse_radius_x = Math.max(10, Math.round(nextWidth / 2));
      widget.ellipse_radius_y = widget.shape_type === "circle" ? widget.ellipse_radius_x : Math.max(10, Math.round(nextHeight / 2));
    } else if (widget.kind === "shape" && widget.shape_type === "line") {
      widget.line_length = Math.max(10, Math.round(Math.hypot(nextWidth, nextHeight)));
      widget.line_angle = Math.round(Math.atan2(nextHeight, nextWidth) * 180 / Math.PI);
    } else {
      widget.width = nextWidth; widget.height = nextHeight;
    }
  } else {
    widget.x = Math.round(state.pointer.wx + dx); widget.y = Math.round(state.pointer.wy + dy);
  }
  clamp(widget);
  const node = $(`.canvas-widget[data-id="${widget.id}"]`);
  if (node) Object.assign(node.style, { left: `${widget.x * state.zoom}px`, top: `${widget.y * state.zoom}px`, width: `${widget.width * state.zoom}px`, height: `${widget.height * state.zoom}px` });
  fillWidgetForm(); markDirty();
}

function endPointer() {
  if (!state.pointer) return;
  const pointer = state.pointer;
  const widget = selectedWidget();
  state.pointer = null;
  if (!pointer.moved && pointer.wasSelected && widget?.kind === "page_button") {
    switchPage(widget.target_page);
  } else {
    renderCanvas();
  }
  saveProject();
}

function selectWidget(id) {
  state.selectedId = id;
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
  renderPageTabs();
  $$('[data-widget]').forEach((input) => { input.value = widget[input.dataset.widget] ?? ""; });
  $$('[data-widget-number]').forEach((input) => { input.value = widget[input.dataset.widgetNumber] ?? 0; });
  const image = widget.kind === "image";
  const shape = widget.kind === "shape";
  const progress = ["progress_circle", "progress_bar"].includes(widget.kind);
  const canLoadImage = shape || ["label", "button", "page_button"].includes(widget.kind);
  $("#assetRow").classList.toggle("hidden", !image);
  $("#contentAssetRow").classList.toggle("hidden", !canLoadImage);
  $("#removeContentImage").disabled = !widget.content_asset_path;
  $("#textRow").classList.remove("hidden");
  $("#bindingRow").classList.toggle("hidden", widget.kind === "page_button");
  $("#bindingTypeRow").classList.toggle("hidden", widget.kind === "page_button" || progress);
  $("#targetPageRow").classList.toggle("hidden", widget.kind !== "page_button");
  $("#imageSection").classList.toggle("hidden", !image && !widget.content_asset_path);
  $("#geometrySection").classList.toggle("hidden", !shape || !["ellipse", "circle", "line"].includes(widget.shape_type));
  $("#ellipseGeometry").classList.toggle("hidden", !shape || !["ellipse", "circle"].includes(widget.shape_type));
  $("#lineGeometry").classList.toggle("hidden", !shape || widget.shape_type !== "line");
  $("#progressSection").classList.toggle("hidden", !progress);
  $("#styleSection").classList.remove("hidden");
  $("#shapeTypeRow").classList.toggle("hidden", !shape);
  $("#clickEffectRow").classList.toggle("hidden", !["button", "page_button"].includes(widget.kind));
  $("#actionSection").classList.toggle("hidden", widget.kind !== "button");
  if (image) $("#assetPreview").src = assetUrl(widget.asset_path);
}

function newWidget(kind, extra = {}) {
  const index = state.project.widgets.length + 1;
  const topLayer = Math.max(0, ...state.project.widgets.filter((item) => item.page === state.activePageId).map((item) => item.z_index || 0)) + 1;
  const labels = { button: "虚拟按钮", page_button: "切换界面", image: "图片", shape: "双击编辑", label: "文本显示", progress_circle: "50%", progress_bar: "50%" };
  const progress = ["progress_circle", "progress_bar"].includes(kind);
  const widget = {
    id: `widget_${Date.now().toString(36)}_${index}`, kind, text: labels[kind],
    x: 40 + (index * 18) % 260, y: 40 + (index * 18) % 160,
    width: kind === "image" ? 240 : kind === "shape" || kind === "progress_circle" ? 160 : 220,
    height: kind === "image" ? 140 : kind === "progress_circle" ? 160 : kind === "shape" ? 100 : kind === "progress_bar" ? 48 : 60,
    font_size: 28, text_color: "#FFFFFF", background_color: kind.includes("button") ? "#1976D2" : "#252B33",
    binding: "", binding_type: "number", action: "", action_entity: "", action_value: 1, animation: "无", asset_path: "", content_asset_path: "",
    page: state.activePageId, z_index: topLayer, image_fit: "fill", image_offset_x: 50, image_offset_y: 50,
    shape_type: extra.shape_type || "rectangle", border_color: "#FFFFFF", border_width: progress ? 12 : kind === "shape" ? 2 : 0, radius: 4,
    line_angle: 0, line_length: 160, ellipse_radius_x: 80, ellipse_radius_y: 50, text_align: "center", click_effect: "scale",
    progress_min: 0, progress_max: 100, progress_value: 50, progress_color: "#2F7DF6", show_value: "percent",
    target_page: state.project.pages.find((page) => page.id !== state.activePageId)?.id || state.activePageId, ...extra,
  };
  clamp(widget); state.project.widgets.push(widget); selectWidget(widget.id); markDirty(); saveProject();
}

async function uploadImage(file) {
  if (!file) return;
  try {
    const dataUrl = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); });
    const result = await request("/api/upload", { method: "POST", body: JSON.stringify({ filename: file.name, data: dataUrl.split(",")[1] }) });
    const current = selectedWidget();
    if (state.uploadMode === "content" && current) {
      current.content_asset_path = result.path; fillWidgetForm(); renderCanvas(); markDirty(); saveProject();
    } else if (state.uploadMode === "replace" && current?.kind === "image") {
      current.asset_path = result.path; fillWidgetForm(); renderCanvas(); markDirty(); saveProject();
    } else {
      const scale = Math.min(1, 420 / result.width, 280 / result.height);
      newWidget("image", { asset_path: result.path, width: Math.max(20, Math.round(result.width * scale)), height: Math.max(20, Math.round(result.height * scale)) });
    }
  } catch (error) { toast(error.message); }
  state.uploadMode = "new";
  $("#imageInput").value = "";
}

function markDirty() { state.dirty = true; $("#saveState").textContent = "未保存"; }
let saveTimer;
function saveProject() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    try { await request("/api/project", { method: "POST", body: JSON.stringify(state.project) }); state.dirty = false; $("#saveState").textContent = "已保存"; }
    catch (error) { $("#saveState").textContent = "保存失败"; toast(error.message); }
  }, 250);
}

async function generate() {
  try { const result = await request("/api/generate", { method: "POST", body: JSON.stringify(state.project) }); toast(`配置已生成：${result.path}`); return true; }
  catch (error) { toast(error.message); return false; }
}

async function refreshPorts() {
  try {
    const ports = await request("/api/ports");
    const select = $("#portSelect"), current = select.value;
    select.innerHTML = '<option value="">选择串口</option>' + ports.map((item) => `<option value="${item.device}">${item.label}</option>`).join("");
    select.value = current;
  } catch (error) { toast(error.message); }
}

async function startTask(operation) {
  try {
    await request("/api/task", { method: "POST", body: JSON.stringify({ operation, port: $("#portSelect").value, project: state.project }) });
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

function bindEvents() {
  $$('.tool[data-kind]').forEach((button) => button.addEventListener("click", () => newWidget(button.dataset.kind, { shape_type: button.dataset.shape })));
  $("#replaceImage").addEventListener("click", () => { state.uploadMode = "replace"; $("#imageInput").click(); });
  $("#attachImage").addEventListener("click", () => { state.uploadMode = "content"; $("#imageInput").click(); });
  $("#removeContentImage").addEventListener("click", () => { const widget = selectedWidget(); if (!widget) return; widget.content_asset_path = ""; fillWidgetForm(); renderCanvas(); markDirty(); saveProject(); });
  $("#imageInput").addEventListener("change", (event) => uploadImage(event.target.files[0]));
  $("#videoTool").addEventListener("click", () => toast("该板卡可用静态图片；ESPHome没有通用MP4/H.264视频解码支持。"));
  $("#projectSettings").addEventListener("click", () => selectWidget(null));
  $("#refreshPorts").addEventListener("click", refreshPorts);
  $("#addPageBtn").addEventListener("click", () => {
    const number = state.project.pages.length + 1;
    const name = window.prompt("界面名称", `界面${number}`);
    if (!name) return;
    const page = { id: `page_${Date.now().toString(36)}`, name, background_color: "#080B10" };
    state.project.pages.push(page); switchPage(page.id); markDirty(); saveProject();
  });
  $("#deleteBtn").addEventListener("click", () => { if (!state.selectedId) return; state.project.widgets = state.project.widgets.filter((item) => item.id !== state.selectedId); selectWidget(null); markDirty(); saveProject(); });
  $("#screen").addEventListener("pointerdown", (event) => { if (event.target === event.currentTarget) selectWidget(null); });
  $("#screen").addEventListener("wheel", (event) => { if (state.project.pages.length < 2) return; event.preventDefault(); cyclePage(event.deltaY > 0 ? 1 : -1); }, { passive: false });
  window.addEventListener("pointermove", movePointer);
  window.addEventListener("pointerup", endPointer);
  window.addEventListener("pointercancel", endPointer);
  $$('[data-project]').forEach((input) => input.addEventListener("input", () => { state.project[input.dataset.project] = input.value; markDirty(); saveProject(); }));
  $$('[data-widget]').forEach((input) => input.addEventListener("input", () => {
    const widget = selectedWidget(); if (!widget) return;
    widget[input.dataset.widget] = input.value;
    if (input.dataset.widget === "page") { state.activePageId = input.value; renderPageTabs(); }
    if (input.dataset.widget === "shape_type") clamp(widget);
    fillWidgetForm(); renderCanvas(); markDirty(); saveProject();
  }));
  $$('[data-widget-number]').forEach((input) => input.addEventListener("input", () => {
    const widget = selectedWidget(); if (!widget) return;
    const property = input.dataset.widgetNumber, value = Number(input.value);
    widget[property] = value;
    if (widget.kind === "shape" && ["ellipse", "circle"].includes(widget.shape_type)) {
      if (property === "width") widget.ellipse_radius_x = value / 2;
      if (property === "height") widget.ellipse_radius_y = value / 2;
    }
    clamp(widget); fillWidgetForm(); renderCanvas(); markDirty(); saveProject();
  }));
  $$('input[type="number"], input[type="range"]').forEach((input) => input.addEventListener("wheel", (event) => {
    if (document.activeElement !== input) input.focus();
    event.preventDefault(); event.stopPropagation();
    const step = Number(input.step) || 1, min = input.min === "" ? -Infinity : Number(input.min), max = input.max === "" ? Infinity : Number(input.max);
    input.value = Math.max(min, Math.min(max, (Number(input.value) || 0) + (event.deltaY < 0 ? step : -step)));
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }, { passive: false }));
  $$('[data-layer]').forEach((button) => button.addEventListener("click", () => {
    const widget = selectedWidget(); if (!widget) return;
    const siblings = state.project.widgets.filter((item) => item.page === widget.page).sort((a, b) => a.z_index - b.z_index);
    siblings.forEach((item, index) => { item.z_index = index + 1; });
    const index = siblings.indexOf(widget), action = button.dataset.layer;
    if (action === "top") widget.z_index = siblings.length + 1;
    if (action === "bottom") widget.z_index = 0;
    if (action === "up" && index < siblings.length - 1) [widget.z_index, siblings[index + 1].z_index] = [siblings[index + 1].z_index, widget.z_index];
    if (action === "down" && index > 0) [widget.z_index, siblings[index - 1].z_index] = [siblings[index - 1].z_index, widget.z_index];
    renderCanvas(); markDirty(); saveProject();
  }));
  $$('.segmented button').forEach((button) => button.addEventListener("click", () => { state.zoom = Number(button.dataset.zoom); $$('.segmented button').forEach((item) => item.classList.toggle("active", item === button)); $("#screenShell").style.setProperty("--zoom", state.zoom); renderCanvas(); }));
  $("#generateBtn").addEventListener("click", generate); $("#validateBtn").addEventListener("click", () => startTask("validate")); $("#compileBtn").addEventListener("click", () => startTask("compile")); $("#flashBtn").addEventListener("click", () => startTask("upload"));
  $("#toggleConsole").addEventListener("click", () => { const collapsed = $("#console").classList.toggle("collapsed"); $("#toggleConsole").textContent = collapsed ? "展开" : "收起"; });
  window.addEventListener("keydown", (event) => { if ((event.key === "Delete" || event.key === "Backspace") && state.selectedId && !["INPUT", "SELECT"].includes(document.activeElement.tagName)) $("#deleteBtn").click(); });
}

async function initialize() {
  try {
    state.project = await request("/api/project");
    state.project.pages ||= [{ id: "main_page", name: "主界面", background_color: "#080B10" }];
    for (const widget of state.project.widgets) {
      if (widget.kind === "label") widget.kind = "shape";
      Object.assign(widget, {
        page: "main_page", z_index: 1, image_fit: "fill", image_offset_x: 50, image_offset_y: 50, shape_type: "rectangle",
        border_color: "#FFFFFF", border_width: 0, radius: 4, target_page: "", content_asset_path: "", line_angle: 0,
        line_length: 160, ellipse_radius_x: Math.max(10, (widget.width || 160) / 2), ellipse_radius_y: Math.max(10, (widget.height || 100) / 2),
        text_align: "center", click_effect: "scale", binding_type: "number", progress_min: 0, progress_max: 100, progress_value: 50,
        progress_color: "#2F7DF6", show_value: "percent",
      }, widget);
    }
    state.activePageId = state.project.pages[0].id;
    $$('[data-project]').forEach((input) => { input.value = state.project[input.dataset.project] ?? ""; });
    bindEvents(); renderPageTabs(); renderCanvas(); refreshPorts(); pollTask();
  } catch (error) { toast(error.message); }
}
initialize();
