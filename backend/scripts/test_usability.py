"""轻量 UI 回归验收，模拟 API，不产生云端费用。"""

import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        calls = []

        def route_api(route):
            path = route.request.url.split("/api/v1/")[1]
            calls.append(path)
            payload = {"documents": [], "nodes": [], "edges": [], "conflicts": []}
            route.fulfill(content_type="application/json", body=json.dumps(payload))

        page.route("**/api/v1/**", route_api)
        page.goto("http://127.0.0.1:5173", wait_until="networkidle")
        expect(page.locator(".blank-thread")).to_be_visible()
        expect(page.locator(".welcome-shell")).to_have_count(0)
        expect(page.locator(".session-item")).to_have_count(0)
        expect(page.get_by_role("textbox", name="教学需求")).to_have_count(0)
        page.locator(".session-new").click()
        dialog = page.get_by_role("dialog", name="新建备课", exact=True)
        expect(dialog.get_by_role("textbox", name="会话名称")).to_be_focused()
        dialog.get_by_role("textbox", name="会话名称").fill("   ")
        expect(dialog.get_by_role("button", name="创建会话")).to_be_disabled()
        page.keyboard.press("Escape")
        expect(page.locator(".session-item")).to_have_count(0)
        page.locator(".session-new").click()
        dialog = page.get_by_role("dialog", name="新建备课", exact=True)
        expect(dialog.get_by_role("button", name="创建会话")).to_be_disabled()
        dialog.get_by_role("textbox", name="会话名称").fill("七年级一元一次方程")
        dialog.get_by_role("button", name="创建会话").click()
        page.locator(".session-item.active .session-delete").click()
        page.locator(".session-item.active .session-delete").click()
        expect(page.locator(".blank-thread")).to_be_visible()
        expect(page.locator(".composer")).to_have_count(0)
        page.locator(".session-new").click()
        dialog = page.get_by_role("dialog", name="新建备课", exact=True)
        expect(dialog.get_by_role("button", name="创建会话")).to_be_disabled()
        dialog.get_by_role("textbox", name="会话名称").fill("七年级一元一次方程")
        dialog.get_by_role("button", name="创建会话").click()
        page.get_by_placeholder("输入教学需求").fill("为七年级设计一节45分钟的一元一次方程课，包含生活案例和课堂练习。")
        assert "chat" not in calls
        page.get_by_role("button", name="知识库", exact=True).click()
        expect(page.get_by_role("button", name="上传资料", exact=True)).to_be_visible()
        expect(page.locator(".documents-toolbar").get_by_role("button", name="上传资料", exact=True)).to_be_visible()
        expect(page.locator(".composer").get_by_role("button", name="上传资料", exact=True)).to_have_count(0)
        expect(page.get_by_role("checkbox", name="使用参考资料", exact=True)).to_be_visible()
        page.get_by_role("button", name="使用帮助", exact=True).click()
        expect(page.get_by_role("dialog", name="使用帮助")).to_be_visible()
        expect(page.get_by_text("语音输入由浏览器提供")).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.get_by_role("dialog", name="使用帮助")).to_have_count(0)
        expect(page.locator(".topbar .mode-selector")).to_have_count(0)
        page.get_by_role("button", name="备课模式：标准", exact=True).click()
        expect(page.get_by_role("menu", name="选择备课模式")).to_be_visible()
        page.get_by_role("menuitemradio", name="快速", exact=True).click()
        expect(page.get_by_role("menu", name="选择备课模式")).to_have_count(0)
        page.get_by_role("button", name="备课模式：快速", exact=True).click()
        page.keyboard.press("Escape")
        expect(page.get_by_role("menu", name="选择备课模式")).to_have_count(0)
        expect(page.get_by_role("button", name="备课模式：快速", exact=True)).to_be_focused()
        expect(page.locator(".mode-description")).to_contain_text("少量追问")
        page.get_by_role("button", name="产物预览", exact=True).click()
        expect(page.get_by_text("生成后，你的教学材料会出现在这里")).to_be_visible()
        expect(page.get_by_role("button", name="会话信息", exact=True)).to_have_count(0)
        expect(page.locator(".tabs button")).to_have_count(3)
        expect(page.get_by_text("开发中", exact=False)).to_have_count(0)
        page.get_by_role("button", name="关闭教学材料", exact=True).click()
        page.screenshot(path=str(ROOT / ".local" / "after-desktop.png"), full_page=True)
        print("PASS: onboarding, examples, readable controls and help")

        for width in (390, 768):
            page.set_viewport_size({"width": width, "height": 844})
            page.get_by_role("button", name="知识库", exact=True).click()
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), (
                f"horizontal overflow at {width}px"
            )
            expect(page.get_by_role("button", name="上传资料", exact=True)).to_be_visible()
            page.get_by_role("button", name="关闭教学材料", exact=True).click()
            page.get_by_role("button", name="打开会话列表", exact=True).click()
            expect(page.locator(".conversation-sidebar.open")).to_be_visible()
            page.locator(".session-item.active .session-rename").click()
            rename_dialog = page.get_by_role("dialog", name="重命名备课", exact=True)
            expect(rename_dialog.get_by_role("textbox", name="会话名称")).to_have_value("七年级一元一次方程")
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
            page.keyboard.press("Escape")
            expect(rename_dialog).to_have_count(0)
            page.get_by_role("button", name="关闭会话列表", exact=True).click()
            expect(page.get_by_role("button", name="发送", exact=True)).to_be_visible()
            assert page.locator(".composer").bounding_box()["y"] > 400, "输入框应位于手机工作区底部"
            page.get_by_role("button", name="备课模式：快速", exact=True).click()
            expect(page.get_by_role("menu", name="选择备课模式")).to_be_visible()
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
            page.screenshot(path=str(ROOT / ".local" / f"after-{width}.png"), full_page=True)
            page.keyboard.press("Escape")
        print("PASS: mobile and tablet layout")
        teaching_input = page.get_by_role("textbox", name="教学需求")
        teaching_input.press("Shift+Enter")
        assert "chat" not in calls, "Shift+Enter 应换行而不发送"
        teaching_input.dispatch_event("keydown", {"key": "Enter", "isComposing": True})
        assert "chat" not in calls, "中文输入法确认不能误发送"
        teaching_input.press("Enter")
        expect(teaching_input).to_have_value("")
        expect(page.get_by_role("heading", name="从一节课的想法开始")).to_have_count(0)
        expect(page.get_by_role("button", name="发送", exact=True)).to_be_disabled()
        assert calls.count("chat") == 1
        expect(page.locator(".thread-title")).to_have_text("七年级一元一次方程")
        page.reload(wait_until="networkidle")
        expect(page.locator(".thread-title")).to_have_text("七年级一元一次方程")
        print("PASS: composition-safe send and empty input guard")
        browser.close()


if __name__ == "__main__":
    main()
