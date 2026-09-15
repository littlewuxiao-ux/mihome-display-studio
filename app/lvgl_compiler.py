"""Compile the editor's appearance and bindings into the same LVGL objects.

Decorations never receive input. Numeric subscriptions update controls without
sending HA commands; commands are attached to user interaction events only.
"""
from __future__ import annotations

from dataclasses import replace
import json
import math
import string

import yaml

from .models import ProjectModel, WidgetModel


class Lambda(str):
    pass


class Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


Dumper.add_representer(Lambda, lambda d, v: d.represent_scalar("!lambda", v, style="|"))


def dump(data):
    return yaml.dump(data, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=120)


def cpp(value):
    return json.dumps(str(value), ensure_ascii=False)


def rgb(value):
    return int(value.lstrip("#"), 16)


def opa(value):
    return f"{max(0, min(100, int(value)))}%"


def variants(w):
    if not w.state_style_enabled:
        return []
    if w.state_variants:
        return w.state_variants
    # Automatic on/off variants only make sense for widgets that receive a
    # state value. Action-only widgets (for example +/- buttons) may still
    # carry the editor's default state_mapping flag, but applying those
    # variants would replace their configured colour with the off-state
    # colour at startup.
    if not w.binding:
        return []
    if not (w.state_mapping or w.state_icon_enabled):
        return []
    return [dict(value=value, label=label, icon_glyph=glyph, text_color=colour if w.state_icon_enabled else w.text_color,
                 background_color=colour if w.state_visual in {"color", "both"} else w.background_color,
                 depth=depth if w.state_visual in {"depth", "both"} else "flat")
            for value, label, glyph, colour, depth in [
                ("off", w.state_off_text, w.state_icon_off_glyph, w.state_off_color, "inset"),
                ("on", w.state_on_text, w.state_icon_on_glyph, w.state_on_color, "raised")]]


def icon_specs(w):
    result = [(w.icon_glyph, w.icon_size)] if w.show_fixed_icon and w.icon_glyph else []
    result += [(v["icon_glyph"], int(v.get("icon_size") or w.icon_size)) for v in variants(w) if v.get("icon_glyph")]
    if w.kind == "battery":
        result += [("\U000F0079\U000F0084", min(24, max(12, w.height - 4)))]
    return result


def font_size(w):
    if not w.auto_fit_text or (w.binding_type == "state" and (w.state_mapping or w.state_variants)):
        return w.font_size
    title = w.text.strip() if w.show_fixed_title else ""
    sample = title
    if w.binding:
        sample = title + " " + ("unavailable" if w.binding_type == "state" else f"-888{'.' + '8' * w.value_decimals if w.value_decimals else ''} {w.value_suffix}")
        local_sample = {"device:current_time": "2026-09-15 23:59", "device:ip_address": "192.168.100.255", "device:ssid": "WWWWWWWWWWWW", "device:wifi_status": "已连接"}.get(w.binding)
        if local_sample: sample = title + " " + local_sample
    if w.kind == "battery":
        sample = "100%" if w.battery_display != "full" else "100% 4.20V 1.00A 4.20W 12.0h"
    units = sum(1 if ord(c) > 255 else .58 for c in sample.strip()) or 1
    return max(8, min(w.font_size, int(max(8, w.width - 12) / units), int(max(8, w.height - 6) / 1.15)))


def glyphs(project):
    text = string.ascii_letters + string.digits + " .,:;!?+-_/()[]%|°℃←→▼--充电放电亮灯盏数量全关未知已连接未连接正常运行主界面空界面"
    for w in project.widgets:
        text += w.text + w.value_suffix + w.state_on_text + w.state_off_text + w.control_options + w.control_text + w.view_items
        text += "".join(str(v.get("label", "")) for v in variants(w))
    return "".join(sorted(set(text.replace("\n", "").replace("\r", ""))))


class LvglCompiler:
    def __init__(self, project: ProjectModel, legacy):
        self.p = project
        self.legacy = legacy
        self.instances = []
        self.numeric = {}
        self.textual = {}

    def label(self, w):
        title = w.text.strip() if w.show_fixed_title else ""
        text = title
        if w.binding:
            text = (title + " " if title else "") + "--" + (w.value_suffix or "")
        if w.kind in {"progress_circle", "progress_bar"}:
            value = (w.progress_value - w.progress_min) * 100 / (w.progress_max - w.progress_min) if w.show_value == "percent" else w.progress_value
            text = (title + " " if title else "") + ("--" if w.binding else f"{value:.{w.value_decimals}f}") + ("%" if w.show_value == "percent" else w.value_suffix)
        if w.binding_type == "state" and variants(w):
            v = next((v for v in variants(w) if v["value"] == w.state_preview), variants(w)[0])
            text = " ".join(s for s in [title, v.get("label", "")] if s)
        if w.kind == "battery":
            text = "" if w.battery_display == "icon" else "--%" if w.battery_display == "percent" else "--% --V --A --W --h"
        vs = variants(w)
        initial = next((v for v in vs if v["value"] == w.state_preview), vs[0] if vs else {})
        return {"label": dict(id=w.id + "_label", align={"left": "LEFT_MID", "right": "RIGHT_MID"}.get(w.text_align, "CENTER"),
                              x=w.text_offset_x, y=w.text_offset_y, text=text, text_color=rgb(initial.get("text_color") or w.text_color), text_opa=opa(w.text_opacity),
                              text_font=f"ui_font_{font_size(w)}", width="100%", text_align=w.text_align.upper(), long_mode="CLIP", clickable=False)}

    def decorations(self, w):
        result = [self.label(w)]
        vs = variants(w)
        # Always create the state icon, including when the initial state has an
        # explicitly empty glyph. Later states can then safely show it.
        if vs or (w.show_fixed_icon and w.icon_glyph):
            v = next((v for v in vs if v["value"] == w.state_preview), vs[0] if vs else {})
            glyph = v.get("icon_glyph", w.icon_glyph if w.show_fixed_icon else "")
            size = int(v.get("icon_size") or w.icon_size)
            if icon_specs(w):
                result += [{"label": dict(id=w.id + "_icon", align="CENTER", text=glyph, text_color=rgb(v.get("text_color") or w.text_color),
                                          text_font=f"mdi_font_{size}", text_opa=opa(w.text_opacity),
                                          x=int(v.get("icon_offset_x", w.icon_offset_x)), y=int(v.get("icon_offset_y", w.icon_offset_y)), clickable=False)}]
        return result

    def depth(self, w, body):
        vs = variants(w)
        if not vs:
            return
        v = next((v for v in vs if v["value"] == w.state_preview), vs[0])
        body.update(bg_color=rgb(v.get("background_color") or w.background_color), bg_opa=opa(w.background_opacity), clip_corner=True)
        body.update(shadow_width=9 if v.get("depth") == "raised" else 0, shadow_offset_y=4, shadow_color=0,
                    shadow_opa="55%" if v.get("depth") == "raised" else "0%")
        for side, align, direction, first, last in [("top", "TOP_MID", "VER", "68%", "0%"), ("left", "LEFT_MID", "HOR", "68%", "0%"),
                                                   ("bottom", "BOTTOM_MID", "VER", "0%", "28%"), ("right", "RIGHT_MID", "HOR", "0%", "28%")]:
            horizontal = side in {"top", "bottom"}
            body.setdefault("widgets", []).append({"obj": dict(id=f"{w.id}_bevel_{side}", align=align,
                width="100%" if horizontal else max(2, round(w.width / 4)), height=max(2, round(w.height / 4)) if horizontal else "100%",
                bg_color=0 if side in {"top", "left"} else 0xFFFFFF, bg_grad_color=0 if side in {"top", "left"} else 0xFFFFFF,
                bg_opa=first, bg_grad_opa=last, bg_grad_dir=direction, radius=0, border_width=0, pad_all=0,
                hidden=v.get("depth") != "inset", clickable=False, scrollable=False)})

    def action(self, w, value=None):
        entity = w.action_entity or w.binding
        action = w.action
        if not action and w.kind == "slider" and entity.startswith(("input_number.", "number.")):
            action = entity.split(".")[0] + ".set_value"
        if action.startswith("device."):
            if action in {"device.restart", "device.safe_mode"}:
                return [{"button.press": "restart_button" if action.endswith("restart") else "safe_mode_button"}]
            if action == "device.screen_off":
                return [{"light.turn_off": "backlight"}]
            if action == "device.brightness" and value:
                return [{"light.turn_on": {"id": "backlight", "brightness": Lambda(f"return ({value}) / 100.0f;"), "transition_length": "0s"}}]
            return []
        if not action or not entity or entity.startswith("device:"):
            return []
        data = {"entity_id": entity}
        data.update({k: str(v) for k, v in w.action_data.items()})
        if action.endswith(".set_value"):
            data["value"] = Lambda(f"return {value};") if value else str(w.action_data.get("value", w.action_value))
        elif value and action == "light.turn_on":
            data["brightness"] = Lambda(f"return {value};")
        return [{"homeassistant.action": {"action": action, "data": data}}]

    def widget(self, w, source_id=None):
        self.instances.append(w)
        if w.binding:
            store = self.textual if w.binding_type == "state" and w.kind not in {"progress_circle", "progress_bar", "slider", "battery", "spinbox"} else self.numeric
            store.setdefault((w.binding, w.binding_attribute), []).append(w)
        interactive_shape = w.kind in {"shape", "icon", "image"} and w.tap_mode == "ha" and bool(w.action)
        component = "button" if w.kind in {"button", "page_button"} or interactive_shape else "obj"
        body = dict(id=w.id + "_root", x=w.x, y=w.y, width=w.width, height=w.height, pad_all=0,
                    radius=200 if w.shape_type in {"ellipse", "circle"} else w.radius,
                    bg_color=rgb(w.background_color), bg_opa=opa(w.background_opacity), opa=opa(w.opacity),
                    border_width=w.border_width, border_color=rgb(w.border_color), border_opa=opa(w.border_opacity),
                    scrollable=False, clickable=False, hidden=w.hidden)
        children = []
        control = None
        scale = 10 ** w.value_decimals
        if w.kind in {"progress_circle", "progress_bar", "battery", "slider"}:
            control = "arc" if w.kind == "progress_circle" or (w.kind == "battery" and w.battery_style == "ring") else "slider" if w.kind == "slider" else "bar"
            c = dict(id=w.id + "_control", align="CENTER", width="100%", height="100%", min_value=round(w.progress_min * scale), max_value=round(w.progress_max * scale),
                     value=round(w.progress_value * scale), pad_all=0, border_width=0, radius=w.radius, clickable=w.kind == "slider" and w.tap_mode != "page", scrollable=False)
            body.update(bg_opa="0%", border_width=0)
            if control == "arc":
                c.update(start_angle=270 if w.kind == "battery" else 135, end_angle=269 if w.kind == "battery" else 45, adjustable=False,
                         arc_color=rgb(w.background_color), arc_opa=opa(w.background_opacity), arc_width=max(3, w.border_width), bg_opa="0%",
                         indicator=dict(arc_color=rgb(w.progress_color), arc_width=max(3, w.border_width), arc_opa=opa(w.border_opacity)), knob=dict(bg_opa="0%"))
            else:
                c.update(bg_color=rgb(w.background_color), bg_opa=opa(w.background_opacity), indicator=dict(bg_color=rgb(w.progress_color), radius=w.radius))
            if w.kind == "slider":
                margin = min(12, max(2, w.width // 8))
                c.update(width=max(12, w.width - margin * 2), height=min(8, w.height), radius=4,
                         knob=dict(bg_color=rgb(w.text_color), width=22, height=22, radius=11, pad_all=0, border_width=0, shadow_width=0))
                actions = self.action(w, f"x / {scale}.0f")
                if actions and w.tap_mode != "page":
                    c["on_release"] = actions
                c["on_value"] = [{"lambda": f"lv_label_set_text_fmt(id({w.id}_label), {cpp('%.' + str(w.value_decimals) + 'f' + w.value_suffix.replace('%','%%'))}, x / {scale}.0f);"}]
            if w.kind == "battery":
                c["indicator"] = dict(bg_color=rgb(w.battery_discharge_color), arc_color=rgb(w.battery_discharge_color), arc_width=max(3, w.border_width)) if control == "arc" else dict(bg_color=rgb(w.battery_discharge_color), radius=w.radius)
            children.append({control: c})
        elif w.kind in {"switch", "checkbox", "dropdown", "roller", "spinbox", "textarea", "led", "spinner", "qrcode"}:
            component = w.kind
            body.update(clickable=not w.binding or w.tap_mode != "none", text_font=f"ui_font_{font_size(w)}", text_color=rgb(w.text_color))
            if component in {"switch", "checkbox"}:
                body["state"] = {"checked": w.control_checked}
                if component == "checkbox": body["text"] = w.text
                target = w.action_entity or w.binding
                if target and not target.startswith("device:") and not w.action and w.tap_mode == "ha":
                    domain = target.split(".")[0]
                    body["on_click"] = [{"if": {"condition": {"lambda": "return x;"},
                        "then": [{"homeassistant.action": {"action": domain + ".turn_on", "data": {"entity_id": target}}}],
                        "else": [{"homeassistant.action": {"action": domain + ".turn_off", "data": {"entity_id": target}}}]}}]
            elif component in {"dropdown", "roller"}:
                body.update(options=w.control_options.splitlines(), selected_index=w.control_selected)
                if component == "dropdown": body["symbol"] = "▼"
                target = w.action_entity or w.binding
                if target.startswith(("input_select.", "select.")) and w.tap_mode == "ha":
                    body["on_change"] = [{"homeassistant.action": {"action": target.split(".")[0] + ".select_option", "data": {"entity_id": target, "option": Lambda("return text;")}}}]
            elif component == "spinbox":
                body.update(range_from=w.progress_min, range_to=w.progress_max, value=w.progress_value, digits=w.control_digits, decimal_places=w.control_decimals)
                target = w.action_entity or w.binding
                if target.startswith(("input_number.", "number.")) and w.tap_mode == "ha":
                    body["on_change"] = [{"homeassistant.action": {"action": target.split(".")[0] + ".set_value", "data": {"entity_id": target, "value": Lambda("return x;")}}}]
            elif component in {"textarea", "qrcode"}: body["text"] = w.control_text
            elif component == "spinner": body.update(spin_time="1s", arc_length="60deg")
        elif w.kind == "shape" and w.shape_type == "line":
            angle = math.radians(w.line_angle)
            dx, dy = round(math.cos(angle) * w.line_length), round(math.sin(angle) * w.line_length)
            children.append({"line": dict(id=w.id + "_line", points=[f"{max(0,-dx)}, {max(0,-dy)}", f"{max(0,dx)}, {max(0,dy)}"], line_width=max(1, w.border_width), line_color=rgb(w.border_color), clickable=False)})
            body.update(bg_opa="0%", border_width=0)
        elif w.kind == "trend_chart":
            # Preserve the pre-existing trend renderer; its runtime history is
            # independent of the controls repaired here.
            loader = type("Loader", (yaml.SafeLoader,), {})
            loader.add_constructor("!lambda", lambda l, n: Lambda(l.construct_scalar(n)))
            return yaml.load("\n".join(self.legacy._widget_lines(w, self.p.page_animation)), Loader=loader)[0]
        if (w.kind == "image" and w.asset_path) or w.content_asset_path:
            children.append({"image": dict(id=w.id + "_content", align="CENTER", src=(source_id or w.id) + ("_asset" if w.kind == "image" else "_content_asset"), clickable=False, image_opa=opa(w.image_opacity))})
        self.depth(w, body)
        children += body.pop("widgets", [])
        if w.kind not in {"switch", "checkbox", "dropdown", "roller", "spinbox", "textarea", "qrcode", "spinner", "led"}:
            children += self.decorations(w)
        if w.kind == "slider":
            # Slider captions belong above/below the rail, never across its knob.
            label = next(c["label"] for c in children if "label" in c)
            label.update(hidden=w.ha_visual_mode != "slider_value", y=-(w.height // 2) + 8)
        if w.kind == "battery":
            children.append({"label": dict(id=w.id + "_battery_status_icon", align="LEFT_MID", x=3, text="\U000F0079", text_color=rgb(w.text_color),
                                           text_font=f"mdi_font_{min(24, max(12, w.height - 4))}", clickable=False)})
        if children: body["widgets"] = children
        if w.tap_mode == "page":
            body["on_click"] = [{"lvgl.page.show": dict(id=w.target_page, animation=self.p.page_animation, time="0ms" if self.p.page_animation == "NONE" else "300ms")}]
        elif w.tap_mode == "ha" or w.action.startswith("device."):
            selection_action = w.kind in {"dropdown", "roller"} and w.action.endswith(".select_option")
            if w.kind != "slider" and not selection_action and (actions := self.action(w)):
                body["on_click"] = actions
        if "on_click" in body:
            body["clickable"] = True
            body["on_click"] = {"then": body["on_click"]}
        if body["clickable"] and w.click_effect != "none":
            body["pressed"] = {"transform_width": -4, "transform_height": -4} if w.click_effect == "scale" else {"opa": "70%"} if w.click_effect == "darken" else {"outline_color": rgb(w.progress_color), "outline_width": 2}
        return {component: body}

    def numeric_update(self, w, expression="x"):
        if w.kind == "spinbox":
            return {"if": {"condition": {"lambda": f"return std::isfinite({expression});"},
                           "then": [{"lvgl.spinbox.update": {"id": w.id + "_root", "value": Lambda(f"return {expression};")}}]}}
        scale = 10 ** w.value_decimals
        statements = []
        if w.kind in {"progress_circle", "progress_bar", "battery", "slider"}:
            ctype = "arc" if w.kind == "progress_circle" or (w.kind == "battery" and w.battery_style == "ring") else "slider" if w.kind == "slider" else "bar"
            statements.append(f"if (std::isfinite({expression})) lv_{ctype}_set_value(id({w.id}_control), (int) lroundf(std::clamp({expression}, {float(w.progress_min)}f, {float(w.progress_max)}f) * {scale}), " + ("LV_ANIM_OFF);" if ctype != "arc" else "0);"))
            if ctype == "arc": statements[-1] = statements[-1].replace(", 0);", ");")
        title = w.text.strip() + " " if w.show_fixed_title and w.text.strip() and w.kind != "battery" else ""
        suffix = w.value_suffix
        value = expression
        if (w.kind in {"progress_circle", "progress_bar"} and w.show_value == "percent") or w.kind == "battery":
            suffix = "%"
            if w.kind != "battery": value = f"({expression} - {float(w.progress_min)}f) * 100.0f / {float(w.progress_max - w.progress_min)}f"
        fmt = title.replace("%", "%%") + f"%.{w.value_decimals}f" + suffix.replace("%", "%%")
        if w.kind not in {"spinbox", "switch", "dropdown", "roller"} and not (w.kind == "battery" and w.battery_display == "icon"):
            statements.append(f"if (std::isfinite({expression})) lv_label_set_text_fmt(id({w.id}_label), {cpp(fmt)}, {value}); else lv_label_set_text(id({w.id}_label), {cpp(title + '--' + suffix)});")
        if w.kind == "battery":
            current = "id(ina_battery_current).state" if self.p.battery_monitor else "NAN"
            clr = f"(!std::isfinite({expression}) ? {rgb(w.background_color)} : ({expression} <= 20.0f ? {rgb(w.battery_low_color)} : ({expression} <= 40.0f ? {rgb(w.battery_warning_color)} : ({current} > 0.005f ? {rgb(w.battery_charge_color)} : {rgb(w.battery_discharge_color)}))))"
            prop = "arc_color" if w.battery_style == "ring" else "bg_color"
            statements += [f"lv_obj_set_style_{prop}(id({w.id}_control), lv_color_hex({clr}), LV_PART_INDICATOR);",
                           f"lv_label_set_text(id({w.id}_battery_status_icon), {current} > 0.005f ? {cpp(chr(0xF0084))} : {cpp(chr(0xF0079))});"]
            if w.battery_display == "full" and self.p.battery_monitor:
                statements += [f"if (std::isfinite({expression})) lv_label_set_text_fmt(id({w.id}_label), \"%.0f%% %.2fV %.2fA %.2fW %.1fh\", {expression}, id(ina_battery_voltage).state, {current}, id(ina_battery_power).state, id(battery_remaining).state);"]
        return {"lambda": "\n".join(statements) or "// No numeric display"}

    def text_update(self, w):
        vs = variants(w)
        title = w.text.strip() + " " if w.show_fixed_title and w.text.strip() else ""
        code = []
        if w.kind in {"switch", "checkbox"}:
            code += [f'if (x == "on") lv_obj_add_state(id({w.id}_root), LV_STATE_CHECKED); else lv_obj_remove_state(id({w.id}_root), LV_STATE_CHECKED);']
        elif w.kind in {"dropdown", "roller"}:
            return {f"lvgl.{w.kind}.update": {"id": w.id + "_root", "selected_text": Lambda("return x;")}}
        else:
            expression = "x"
            sensor_state = w.binding.startswith("sensor.") and w.state_mapping
            if w.ha_state_profile not in {"sensor:light_status", "sensor:zero_off", "sensor:custom"} and not sensor_state:
                for v in reversed(vs):
                    test = f'x == {cpp(v["value"])}'
                    if not w.state_variants:
                        on = f'x {"!=" if w.state_match == "not_equals" else "=="} {cpp(w.state_on_value)}'
                        test = on if v["value"] == "on" else f"!({on})"
                    expression = f'({test} ? std::string({cpp(v.get("label", ""))}) : {expression})'
            code += [f"lv_label_set_text(id({w.id}_label), (std::string({cpp(title)}) + {expression}).c_str());"]
        if vs and w.kind not in {"switch", "checkbox", "dropdown", "roller"}:
            for index, v in enumerate(vs):
                test = f'x == {cpp(v["value"])}'
                if not w.state_variants:
                    on = f'x {"!=" if w.state_match == "not_equals" else "=="} {cpp(w.state_on_value)}'
                    test = on if v["value"] == "on" else f"!({on})"
                if w.ha_state_profile in {"sensor:light_status", "sensor:zero_off", "sensor:custom"} or (w.binding.startswith("sensor.") and w.state_mapping):
                    closed = f'x == {cpp(w.state_on_value)}'
                    test = f'({closed})' if v["value"] in {"off", "closed"} else f'!({closed})'
                code.append(("if" if index == 0 else "else if") + f" ({test}) {{")
                code += [f"lv_obj_set_style_bg_color(id({w.id}_root), lv_color_hex({rgb(v.get('background_color') or w.background_color)}), 0);",
                         f"lv_obj_set_style_text_color(id({w.id}_label), lv_color_hex({rgb(v.get('text_color') or w.text_color)}), 0);"]
                if icon_specs(w):
                    code += [f"lv_label_set_text(id({w.id}_icon), {cpp(v.get('icon_glyph', w.icon_glyph if w.show_fixed_icon else ''))});",
                             f"lv_obj_set_style_text_color(id({w.id}_icon), lv_color_hex({rgb(v.get('text_color') or w.text_color)}), 0);",
                             f"lv_obj_set_style_text_font(id({w.id}_icon), id(mdi_font_{int(v.get('icon_size') or w.icon_size)})->get_lv_font(), 0);",
                             f"lv_obj_set_x(id({w.id}_icon), {int(v.get('icon_offset_x', w.icon_offset_x))}); lv_obj_set_y(id({w.id}_icon), {int(v.get('icon_offset_y', w.icon_offset_y))});"]
                raised = v.get("depth") == "raised"
                code += [f"lv_obj_set_style_shadow_width(id({w.id}_root), {9 if raised else 0}, 0);", f"lv_obj_set_style_shadow_opa(id({w.id}_root), {140 if raised else 0}, 0);"]
                for side in ("top", "left", "bottom", "right"):
                    code.append(f"lv_obj_{'remove' if v.get('depth') == 'inset' else 'add'}_flag(id({w.id}_bevel_{side}), LV_OBJ_FLAG_HIDDEN);")
                code.append("}")
        if w.visibility_mode != "always":
            code += [f'if (x {"==" if w.visibility_mode == "state_equals" else "!="} {cpp(w.visible_state)}) lv_obj_remove_flag(id({w.id}_root), LV_OBJ_FLAG_HIDDEN); else lv_obj_add_flag(id({w.id}_root), LV_OBJ_FLAG_HIDDEN);']
        return {"lambda": "\n".join(code)}

    def sections(self):
        pages = []
        for page in sorted(self.p.pages, key=lambda p: p.id != self.p.default_page):
            widgets = []
            for original in sorted(self.p.widgets, key=lambda w: w.z_index):
                if page.id not in (original.pages or [original.page]): continue
                # Separate LVGL IDs per page, while subscriptions are shared.
                w = replace(original, id=original.id if page.id == original.page else original.id + "_" + page.id)
                widgets.append(self.widget(w, original.id))
            node = dict(id=page.id, bg_color=rgb(page.background_color), pad_all=0, scrollable=False,
                        widgets=widgets or [{"label": {"text": "空界面", "align": "CENTER"}}])
            if page.background_gradient != "none": node.update(bg_grad_color=rgb(page.background_color_2), bg_grad_dir="HOR" if page.background_gradient == "horizontal" else "VER")
            pages.append(node)
        result = {"lvgl": dict(displays=["main_display"], touchscreens=["touch_panel"], default_font=f"ui_font_{min(font_size(w) for w in self.p.widgets) if self.p.widgets else 28}", buffer_size="25%", pages=pages)}
        sensors, texts = [], []
        for i, ((binding, attr), ws) in enumerate(self.numeric.items()):
            if binding.startswith("device:"): continue
            node = dict(platform="homeassistant", id=f"ha_value_{i}", entity_id=binding, internal=True, on_value=[self.numeric_update(w) for w in ws])
            if attr: node["attribute"] = attr
            sensors.append(node)
        for i, ((binding, attr), ws) in enumerate(self.textual.items()):
            if binding.startswith("device:"): continue
            node = dict(platform="homeassistant", id=f"ha_text_{i}", entity_id=binding, internal=True, on_value=[self.text_update(w) for w in ws])
            if attr: node["attribute"] = attr
            texts.append(node)
        if self.p.battery_monitor:
            p = self.p
            sensors += [dict(platform=p.battery_chip, id="battery_meter", i2c_id="touch_i2c", address=p.battery_address, shunt_resistance=p.battery_shunt_resistance,
                             max_current=p.battery_max_current, update_interval=f"{p.battery_sample_interval}s",
                             bus_voltage=dict(id="ina_battery_voltage", internal=True, filters=[{"offset": p.battery_voltage_offset}]),
                             current=dict(id="ina_battery_current", internal=True, filters=[{"multiply": -1 if p.battery_current_inverted else 1}]),
                             power=dict(id="ina_battery_power", internal=True))]
            result.setdefault("globals", []).append(dict(id="battery_energy_wh", type="float", restore_value=True, initial_value=str(p.battery_capacity_mwh / 1000 * p.battery_initial_percent / 100)))
            sensors[-1]["current"]["on_value"] = [{"lambda": f"""static uint32_t last = 0;
const uint32_t now = millis();
const float voltage = id(ina_battery_voltage).state;
if (last && now - last <= {p.battery_sample_interval * 3000} && std::isfinite(x) && std::isfinite(voltage)) {{
  id(battery_energy_wh) = std::clamp(id(battery_energy_wh) + voltage * x * (now - last) / 3600000.0f, 0.0f, {p.battery_capacity_mwh / 1000.0}f);
}}
last = now;"""}]
            level = f"if (!std::isfinite(id(ina_battery_voltage).state) || !std::isfinite(id(ina_battery_current).state)) return NAN; return id(battery_energy_wh) * 100.0f / {p.battery_capacity_mwh / 1000.0}f;"
            sensors += [dict(platform="template", id="battery_level", internal=True, update_interval=f"{p.battery_sample_interval}s", lambda_=level),
                        dict(platform="template", id="battery_remaining", internal=True, update_interval=f"{p.battery_sample_interval}s",
                             lambda_=f"const float power = id(ina_battery_power).state; if (!std::isfinite(power) || power < 0.01f || id(ina_battery_current).state > 0.005f) return NAN; return {p.battery_capacity_mwh / 1000.0}f * id(battery_level).state / 100.0f / power;")]
            for sensor in sensors:
                if "lambda_" in sensor: sensor["lambda"] = sensor.pop("lambda_")
        device_sensors = {"device:battery_level": "battery_level", "device:battery_voltage": "ina_battery_voltage", "device:battery_current": "ina_battery_current", "device:battery_power": "ina_battery_power", "device:battery_remaining": "battery_remaining"}
        for (binding, _), ws in self.numeric.items():
            if binding in device_sensors:
                sid = device_sensors[binding]
                result.setdefault("interval", []).append({"interval": "1s", "then": [self.numeric_update(w, f"id({sid}).state") for w in ws]})
        self.device_bindings(result, sensors, texts)
        if sensors: result["sensor"] = sensors
        if texts: result["text_sensor"] = texts
        return result

    def device_bindings(self, result, sensors, texts):
        """Local readings use the same labels and formatting as HA readings."""
        for binding, platform in [("device:wifi_signal", "wifi_signal"), ("device:uptime", "uptime")]:
            ws = self.numeric.get((binding, ""), [])
            if ws:
                sensors.append(dict(platform=platform, id="local_" + platform, internal=True, update_interval="10s", on_value=[self.numeric_update(w) for w in ws]))
        wifi = {"platform": "wifi_info"}
        for binding, key in [("device:ip_address", "ip_address"), ("device:ssid", "ssid"), ("device:mac_address", "mac_address")]:
            ws = self.textual.get((binding, ""), [])
            if ws: wifi[key] = dict(id="local_" + key, internal=True, on_value=[self.text_update(w) for w in ws])
        if len(wifi) > 1: texts.append(wifi)
        expressions = {
            "device:firmware_version": f"return std::string({cpp(self.p.firmware_version)});",
            "device:chip_model": 'return std::string("ESP32-S3");',
            "device:flash_size": 'return std::string("16 MB");',
            "device:psram_size": 'return std::string("8 MB");',
            "device:wifi_status": 'return std::string(wifi::global_wifi_component->is_connected() ? "已连接" : "未连接");',
            "device:api_status": 'return std::string(id(native_api).is_connected() ? "已连接" : "未连接");',
            "device:current_time": 'auto now = id(local_clock).now(); if (!now.is_valid()) return std::string("--"); return now.strftime("%Y-%m-%d %H:%M");',
        }
        for binding, expression in expressions.items():
            ws = self.textual.get((binding, ""), [])
            if not ws: continue
            if binding == "device:current_time": result["time"] = [{"platform": "sntp", "id": "local_clock", "timezone": "Asia/Shanghai"}]
            texts.append(dict(platform="template", id="local_" + binding.split(":")[1], internal=True, update_interval="5s", lambda_=expression, on_value=[self.text_update(w) for w in ws]))
            texts[-1]["lambda"] = texts[-1].pop("lambda_")
