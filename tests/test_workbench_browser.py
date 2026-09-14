"""Browser regression checks. All API calls are intercepted; no user project is saved."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from app.models import ProjectModel, PageModel, WidgetModel


class WorkbenchBrowserTests(unittest.TestCase):
    def test_inspector_and_preview(self):
        project = ProjectModel(wifi_ssid="test", pages=[PageModel(id="main_page"), PageModel(id="details")], widgets=[
            WidgetModel(id="number", kind="shape", text="人数", binding="input_number.guests", width=170, height=60, x=20),
            WidgetModel(id="adult", kind="icon", text="成人", show_fixed_title=False, icon_glyph="\U000F0004", icon_size=48, x=220, width=70),
            WidgetModel(id="local", kind="shape", binding="device:wifi_status", binding_type="state", y=160),
            WidgetModel(id="choice", kind="dropdown", binding="input_select.mode", binding_type="state", y=240),
            WidgetModel(id="state_icon", kind="icon", binding="input_boolean.person", binding_type="state", x=340, show_fixed_title=False, show_fixed_icon=False,
                        state_variants=[dict(value="off", label="", icon_glyph="\U000F0004", depth="inset", background_color="#333333"), dict(value="on", label="", icon_glyph="\U000F0004", depth="raised", background_color="#00AA00")]),
        ]).to_dict()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, channel="msedge")
            page = browser.new_page(viewport={"width": 1550, "height": 980})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            def api(route):
                path = route.request.url.split("/api/")[-1].split("?")[0]
                data = project if path == "project" and route.request.method == "GET" else [] if path in {"ports", "devices", "backups"} else {"ok": True, "running": False, "log": "", "progress": 0, "exit_code": None, "operation": ""}
                route.fulfill(status=200, content_type="application/json", body=json.dumps(data))
            page.route("**/api/**", api)
            page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
            page.evaluate("selectWidget('number')")
            page.click('[data-inspector-mode="ha"]')
            self.assertEqual(page.locator("#haEntityId").input_value(), "input_number.guests")
            self.assertEqual(page.locator("#haPrimaryAction").input_value(), "")
            page.select_option("#haPrimaryAction", "set_value")
            page.fill("#haActionParameter", "7")
            self.assertEqual(page.evaluate("selectedWidget().action_data.value"), 7)
            page.select_option("#numberAppearanceMode", "slider_value")
            self.assertEqual(page.evaluate("selectedWidget().kind"), "slider")
            page.select_option("#numberAppearanceMode", "number")
            self.assertEqual(page.evaluate("[selectedWidget().action, selectedWidget().tap_mode]"), ["", "none"])
            page.click('[data-inspector-mode="visual"]')
            if not page.locator("#pageSwitchEnabled").is_visible():
                page.locator("#pageSwitchEnabled").locator("xpath=ancestor::section[1]").locator("h2").click()
            page.select_option("#pageSwitchEnabled", "true")
            self.assertEqual(page.evaluate("[selectedWidget().tap_mode, selectedWidget().target_page]"), ["page", "details"])
            page.select_option("#pageSwitchEnabled", "false")
            self.assertEqual(page.evaluate("selectedWidget().tap_mode"), "none")
            page.evaluate("selectWidget('local')")
            page.click('[data-inspector-mode="ha"]')
            self.assertEqual(page.locator("#haEntityDomain").input_value(), "device")
            self.assertFalse(page.locator("#haPrimaryActionRow").is_visible())
            page.evaluate("selectWidget('choice')")
            page.select_option("#haPrimaryAction", "select_option")
            self.assertEqual(page.evaluate("selectedWidget().action"), "input_select.select_option")
            self.assertFalse(page.locator("#haActionParameterRow").is_visible())
            page.click('[data-inspector-mode="visual"]')
            page.evaluate("selectWidget('state_icon')")
            self.assertEqual(page.evaluate("selectedWidget().state_variants.length"), 2)
            self.assertTrue(page.evaluate("selectedWidget().state_style_enabled"))
            page.evaluate("selectWidget('adult')")
            icon = page.locator('[data-id="adult"] .shape-accessory-icon')
            self.assertEqual(icon.text_content(), "\U000F0004")
            if not page.locator("#visualShowFixedIcon").is_visible():
                page.locator("#styleSection h2").click()
            page.select_option("#visualShowFixedIcon", "false")
            self.assertEqual(page.locator('[data-id="adult"] .shape-accessory-icon').text_content(), "")
            page.select_option("#visualShowFixedIcon", "true")
            page.screenshot(path="build/workbench-optimized-preview.png")
            self.assertEqual(errors, [])
            browser.close()


if __name__ == "__main__":
    unittest.main()
