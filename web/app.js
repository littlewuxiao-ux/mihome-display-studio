const state = { project: null, selectedId: null, zoom: 1, dirty: false, taskTimer: null };
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
  widget.width = Math.max(20, Math.min(800, Number(widget.width) || 20));
  widget.height = Math.max(20, Math.min(480, Number(widget.height) || 20));
  widget.x = Math.max(0, Math.min(800 - widget.width, Number(widget.x) || 0));
  widget.y = Math.max(0, Math.min(480 - widget.height, Number(widget.y) || 0));
  widget.font_size = Math.max(8, Math.min(96, Number(widget.font_size) || 28));
}

function assetUrl(path) {
  if (!path) return "";
  return `/asset/${encodeURIComponent(path.replaceAll("\\", "/").split("/").pop())}`;
}

function renderCanvas() {
  const screen = $("#screen");
  screen.replaceChildren();
  for (const widget of state.project.widgets) {
    clamp(widget);
    const node = document.createElement("div");
    node.className = `canvas-widget ${widget.kind}${widget.id === state.selectedId ? " selected" : ""}`;
    node.dataset.id = widget.id;
    Object.assign(node.style, {
      left: `${widget.x * state.zoom}px`, top: `${widget.y * state.zoom}px`,
      width: `${widget.width * state.zoom}px`, height: `${widget.height * state.zoom}px`,
      color: widget.text_color, backgroundColor: widget.kind === "image" ? "#171b20" : widget.background_color,
      fontSize: `${widget.font_size * state.zoom}px`, zIndex: widget.id === state.selectedId ? 1000 : 1,
    });
    if (widget.kind === "image") {
      const image = document.createElement("img");
      image.src = assetUrl(widget.asset_path);
      image.alt = widget.text || "图片";
      node.append(image);
    } else {
      node.textContent = widget.binding ? `${widget.text || "实体"}  --` : widget.text;
    }
    if (widget.id === state.selectedId) {
      const handle = document.createElement("span");
      handle.className = "resize-handle";
      node.append(handle);
    }
    node.addEventListener("pointerdown", beginPointerAction);
    screen.append(node);
  }
  const selected = selectedWidget();
  $("#selectionInfo").textContent = selected ? `${selected.text || "图片"} · ${selected.x}, ${selected.y} · ${selected.width} × ${selected.height}` : "未选择组件";
  $("#deleteBtn").disabled = !selected;
}

function beginPointerAction(event) {
  event.preventDefault();
  const node = event.currentTarget;
  selectWidget(node.dataset.id);
  const widget = selectedWidget();
  const resizing = event.target.classList.contains("resize-handle");
  const start = { x: event.clientX, y: event.clientY, wx: widget.x, wy: widget.y, width: widget.width, height: widget.height };
  node.setPointerCapture(event.pointerId);
  const move = (next) => {
    const dx = (next.clientX - start.x) / state.zoom;
    const dy = (next.clientY - start.y) / state.zoom;
    if (resizing) {
      widget.width = Math.round(start.width + dx); widget.height = Math.round(start.height + dy);
    } else {
      widget.x = Math.round(start.wx + dx); widget.y = Math.round(start.wy + dy);
    }
    clamp(widget); renderCanvas(); fillWidgetForm(); markDirty();
  };
  const end = () => { node.removeEventListener("pointermove", move); node.removeEventListener("pointerup", end); saveProject(); };
  node.addEventListener("pointermove", move); node.addEventListener("pointerup", end);
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
  $$('[data-widget]').forEach((input) => { input.value = widget[input.dataset.widget] ?? ""; });
  $$('[data-widget-number]').forEach((input) => { input.value = widget[input.dataset.widgetNumber] ?? 0; });
  const image = widget.kind === "image";
  $("#assetRow").classList.toggle("hidden", !image);
  $("#textRow").classList.toggle("hidden", image);
  $("#bindingRow").classList.toggle("hidden", image);
  $("#styleSection").classList.toggle("hidden", image);
  $("#actionSection").classList.toggle("hidden", widget.kind !== "button");
  if (image) $("#assetPreview").src = assetUrl(widget.asset_path);
}

function newWidget(kind, extra = {}) {
  const index = state.project.widgets.length + 1;
  const widget = {
    id: `widget_${Date.now().toString(36)}_${index}`, kind,
    text: kind === "button" ? "触摸按钮" : kind === "image" ? "图片" : "文本显示",
    x: 40 + (index * 18) % 260, y: 40 + (index * 18) % 160,
    width: kind === "image" ? 240 : 180, height: kind === "image" ? 140 : 60,
    font_size: 28, text_color: "#FFFFFF", background_color: kind === "button" ? "#1976D2" : "#151A22",
    binding: "", action: "", action_entity: "", action_value: 1, animation: "无", asset_path: "", ...extra,
  };
  clamp(widget); state.project.widgets.push(widget); selectWidget(widget.id); markDirty(); saveProject();
}

async function uploadImage(file) {
  if (!file) return;
  try {
    const dataUrl = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); });
    const result = await request("/api/upload", { method: "POST", body: JSON.stringify({ filename: file.name, data: dataUrl.split(",")[1] }) });
    const current = selectedWidget();
    if (current?.kind === "image") {
      current.asset_path = result.path; current.width = Math.min(800, result.width); current.height = Math.min(480, result.height); clamp(current); fillWidgetForm(); renderCanvas(); markDirty(); saveProject();
    } else {
      const scale = Math.min(1, 420 / result.width, 280 / result.height);
      newWidget("image", { asset_path: result.path, width: Math.max(20, Math.round(result.width * scale)), height: Math.max(20, Math.round(result.height * scale)) });
    }
  } catch (error) { toast(error.message); }
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
  $$('.tool[data-kind]').forEach((button) => button.addEventListener("click", () => newWidget(button.dataset.kind)));
  $("#imageTool").addEventListener("click", () => $("#imageInput").click());
  $("#replaceImage").addEventListener("click", () => $("#imageInput").click());
  $("#imageInput").addEventListener("change", (event) => uploadImage(event.target.files[0]));
  $("#videoTool").addEventListener("click", () => toast("该板卡可用静态图片；ESPHome没有通用MP4/H.264视频解码支持。"));
  $("#projectSettings").addEventListener("click", () => selectWidget(null));
  $("#refreshPorts").addEventListener("click", refreshPorts);
  $("#deleteBtn").addEventListener("click", () => { if (!state.selectedId) return; state.project.widgets = state.project.widgets.filter((item) => item.id !== state.selectedId); selectWidget(null); markDirty(); saveProject(); });
  $("#screen").addEventListener("pointerdown", (event) => { if (event.target === event.currentTarget) selectWidget(null); });
  $$('[data-project]').forEach((input) => input.addEventListener("input", () => { state.project[input.dataset.project] = input.value; markDirty(); saveProject(); }));
  $$('[data-widget]').forEach((input) => input.addEventListener("input", () => { const widget = selectedWidget(); if (!widget) return; widget[input.dataset.widget] = input.value; renderCanvas(); markDirty(); saveProject(); }));
  $$('[data-widget-number]').forEach((input) => input.addEventListener("input", () => { const widget = selectedWidget(); if (!widget) return; widget[input.dataset.widgetNumber] = Number(input.value); clamp(widget); renderCanvas(); markDirty(); saveProject(); }));
  $$('.segmented button').forEach((button) => button.addEventListener("click", () => { state.zoom = Number(button.dataset.zoom); $$('.segmented button').forEach((item) => item.classList.toggle("active", item === button)); $("#screenShell").style.setProperty("--zoom", state.zoom); renderCanvas(); }));
  $("#generateBtn").addEventListener("click", generate); $("#validateBtn").addEventListener("click", () => startTask("validate")); $("#compileBtn").addEventListener("click", () => startTask("compile")); $("#flashBtn").addEventListener("click", () => startTask("upload"));
  $("#toggleConsole").addEventListener("click", () => { const collapsed = $("#console").classList.toggle("collapsed"); $("#toggleConsole").textContent = collapsed ? "展开" : "收起"; });
  window.addEventListener("keydown", (event) => { if ((event.key === "Delete" || event.key === "Backspace") && state.selectedId && !["INPUT", "SELECT"].includes(document.activeElement.tagName)) $("#deleteBtn").click(); });
}

async function initialize() {
  try {
    state.project = await request("/api/project");
    $$('[data-project]').forEach((input) => { input.value = state.project[input.dataset.project] ?? ""; });
    bindEvents(); renderCanvas(); refreshPorts(); pollTask();
  } catch (error) { toast(error.message); }
}
initialize();
