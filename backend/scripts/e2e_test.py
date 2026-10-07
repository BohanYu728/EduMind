"""EduMind 端到端验收：Playwright 驱动真实 Chrome，stub 网关全链路（不触外部服务）。

前置：后端 :8000（LLM_PROVIDER=stub / ASR_PROVIDER=stub）、前端 :5173（vite dev，/api 代理）。
运行：backend 目录下 `uv run python scripts/e2e_test.py`。
失败时截图到 e2e-artifacts/。
"""

import contextlib
import tempfile
import traceback
from pathlib import Path

from docx import Document
from playwright.sync_api import expect, sync_playwright

BASE = "http://localhost:5173"
ARTIFACTS = Path(__file__).resolve().parent.parent.parent / "e2e-artifacts"
RESULTS: list[tuple[str, bool, str]] = []


def scenario(name: str):
    """场景包装：记录结果，失败全页截图。"""

    def deco(fn):
        def run(page):
            try:
                fn(page)
                RESULTS.append((name, True, ""))
                print(f"  PASS  {name}")
            except Exception as exc:  # noqa: BLE001 — 测试跑包装器，任何场景异常都要记录并截图后继续
                ARTIFACTS.mkdir(parents=True, exist_ok=True)
                with contextlib.suppress(Exception):
                    page.screenshot(path=str(ARTIFACTS / f"FAIL_{name}.png"), full_page=True)
                RESULTS.append((name, False, traceback.format_exc(limit=5)))
                print(f"  FAIL  {name}: {exc}")
                print(traceback.format_exc(limit=5))

        return run

    return deco


def new_session(page, name="TCP握手教案"):
    page.locator(".session-new").click()
    dialog = page.get_by_role("dialog", name="新建备课", exact=True)
    dialog.get_by_role("textbox", name="会话名称").fill(name)
    dialog.get_by_role("button", name="创建会话", exact=True).click()
    expect(dialog).to_have_count(0)
    expect(page.locator(".thread-title")).to_have_text(name)


@scenario("S1 冒烟：工作区加载与材料入口")
def s1_smoke(page):
    page.goto(BASE, timeout=60000)
    expect(page.locator(".logo")).to_have_text("EduMind")
    new_session(page)
    expect(page.locator(".blank-thread")).to_be_visible()
    expect(page.locator(".welcome-shell")).to_have_count(0)
    tabs = page.locator(".tabs button")
    expect(tabs).to_have_count(3)
    for tab in ("知识库", "产物预览", "冲突审核"):
        expect(page.locator(".tabs button", has_text=tab)).to_be_visible()


@scenario("S2 知识库：上传解析 → 图谱预览、缩放与下载")
def s2_upload(page):
    docx = Path(tempfile.gettempdir()) / "edumind_e2e_tcp讲义.docx"
    doc = Document()
    doc.add_heading("TCP 三次握手讲义", 0)
    doc.add_paragraph("TCP 三次握手：客户端发 SYN，服务端回 SYN+ACK，客户端再发 ACK。")
    doc.add_paragraph("释放连接需要四次挥手；滑动窗口机制实现流量控制。")
    doc.save(str(docx))

    page.get_by_role("button", name="知识库", exact=True).click()
    page.locator("input[type=file]").set_input_files(str(docx))
    item = page.locator(".doc-item", has_text="edumind_e2e_tcp讲义.docx").first
    expect(item).to_be_visible(timeout=30000)
    expect(item.locator(".doc-status")).to_have_text("已完成", timeout=60000)
    expect(page.locator(".node-item").first).to_be_visible(timeout=30000)

    page.get_by_role("button", name="生成知识图谱", exact=True).click()
    dialog = page.get_by_role("dialog", name="知识图谱", exact=True)
    expect(dialog).to_be_visible()
    session_id = page.evaluate("JSON.parse(localStorage.getItem('edumind.sessions.v1')).activeId")
    graph = page.request.get(BASE + "/api/v1/knowledge/graph", headers={"X-EduMind-Session": session_id}).json()
    expect(dialog.locator(".graph-node")).to_have_count(len(graph["nodes"]))
    expect(dialog.locator(".graph-edge")).to_have_count(len(graph["edges"]))
    dialog.locator(".graph-node").first.click()
    expect(dialog.locator(".graph-detail strong")).to_have_text(graph["nodes"][0]["title"])
    dialog.get_by_role("button", name="放大图谱", exact=True).click()
    expect(dialog.locator(".graph-toolbar")).to_contain_text("150%")
    dialog.get_by_role("button", name="重置视图", exact=True).click()
    expect(dialog.locator(".graph-toolbar")).to_contain_text("100%")
    with page.expect_download() as download:
        dialog.get_by_role("button", name="下载图谱 SVG", exact=True).click()
    svg_path = ARTIFACTS / download.value.suggested_filename
    download.value.save_as(str(svg_path))
    from xml.etree import ElementTree
    root = ElementTree.parse(svg_path).getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    svg_text = svg_path.read_text(encoding="utf-8")
    assert all(node["title"] in svg_text for node in graph["nodes"])
    page.screenshot(path=str(ARTIFACTS / "knowledge-graph-desktop.png"))
    page.set_viewport_size({"width": 390, "height": 844})
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
    expect(dialog.get_by_role("button", name="关闭知识图谱")).to_be_visible()
    page.screenshot(path=str(ARTIFACTS / "knowledge-graph-mobile.png"))
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    page.set_viewport_size({"width": 1440, "height": 900})


@scenario("S3 备课对话：追问粒度 + 生成课件/教案/提纲")
def s3_chat(page):
    page.get_by_role("button", name="备课模式：标准", exact=True).click()
    page.get_by_role("menuitemradio", name="精细", exact=True).click()
    expect(page.get_by_role("button", name="备课模式：精细", exact=True)).to_be_visible()

    inp = page.get_by_role("textbox", name="教学需求")
    inp.fill("给大二学生讲 TCP 三次握手，45 分钟，学术风格")
    before = page.locator(".msg").count()
    page.locator("button", has_text="发送").click()

    # 备课完成 = 发送按钮恢复可用（sending 状态解除）
    expect(page.locator("button", has_text="备课中…")).to_have_count(0, timeout=120000)
    expect(inp).to_be_editable()
    expect(page.locator("button", has_text="发送")).to_be_disabled()  # 输入为空时阻止空发送
    assert page.locator(".msg").count() >= before + 2, "对话轮数未增加"

    # 意图不完整时后端先追问：补全要素再答，直至产物下发（stub 最多两三轮）
    page.locator(".tabs button", has_text="产物预览").click()
    answer = "主题：TCP 三次握手；学段：大二；时长：45 分钟；风格：学术"
    for _ in range(3):
        if page.locator(".artifact-title", has_text="当前版本").count():
            break
        inp = page.get_by_role("textbox", name="教学需求")
        inp.fill(answer)
        page.locator("button", has_text="发送").click()
        expect(page.locator("button", has_text="备课中…")).to_have_count(0, timeout=120000)
        page.locator(".tabs button", has_text="产物预览").click()
    expect(page.locator(".artifact-title", has_text="当前版本")).to_be_visible()
    expect(page.locator("a.btn", has_text="PPT（")).to_be_visible()
    expect(page.locator("a.btn", has_text="Word 教案")).to_be_visible()


@scenario("S4 修改闭环（课件）：意见 → 重排 → 当前版本更新")
def s4_revise_ppt(page):
    rev = page.locator(".revise-area input")
    rev.fill("把要点再精简一些")
    page.locator(".revise-area button", has_text="修改").click()
    expect(rev).to_have_value("", timeout=60000)  # 成功后才清空输入


@scenario("S5 修改闭环（教案）：双入口第二入口")
def s5_revise_word(page):
    page.locator(".target-toggle button", has_text="教案").click()
    rev = page.locator(".revise-area input")
    expect(rev).to_have_attribute("placeholder", "修改教案：调整环节 / 增加活动 / 改作业")
    rev.fill("增加一个课堂提问环节")
    page.locator(".revise-area button", has_text="修改").click()
    expect(rev).to_have_value("", timeout=60000)


@scenario("S6 试卷：一键生成 → 题目预览 → docx 可下载")
def s6_exam(page):
    page.locator("button", has_text="生成试卷").click()
    expect(page.locator("summary", has_text="预览试卷（")).to_be_visible(timeout=120000)
    expect(page.locator(".exam-preview li").first).to_be_visible()
    expect(page.locator(".exam-preview .tag", has_text="考查知识点").first).to_contain_text(
        "考查知识点"
    )

    with page.expect_download(timeout=30000) as dl:
        page.locator("a.btn", has_text="试卷（").click()
    target = ARTIFACTS / dl.value.suggested_filename
    dl.value.save_as(str(target))
    assert target.stat().st_size > 1000, "试卷 docx 过小"


@scenario("S7 互动内容：一键生成 → 内联入口出现")
def s7_interactive(page):
    page.locator("button", has_text="生成互动内容").click()
    expect(page.locator("a.btn", has_text="互动内容").first).to_be_visible(timeout=120000)


@scenario("S8 会话持久化：刷新恢复消息/产物/粒度/会话名")
def s8_persist(page):
    page.reload(timeout=60000)
    expect(page.locator(".msg.assistant").first).to_contain_text("教学智能体")
    assert page.locator(".msg", has_text="给大二学生讲").count() >= 1, "教师消息未恢复"
    page.locator(".tabs button", has_text="产物预览").click()
    expect(page.locator(".artifact-title", has_text="当前版本")).to_be_visible()
    expect(page.get_by_role("button", name="备课模式：精细", exact=True)).to_be_visible()

    expect(page.locator("a.btn", has_text="试卷（")).to_be_visible()
    expect(page.locator(".thread-title")).to_contain_text("握手")  # 自定义名称刷新后保留


@scenario("S9 多会话：新建 / 切换 / 两段式删除")
def s9_sessions(page):
    page.locator(".session-wrap button.ghost", has_text="会话").click()
    new_session(page)
    expect(page.locator(".msg")).to_have_count(0, timeout=10000)  # 新会话直接显示输入工作区

    # 切回旧会话：菜单内点击旧会话条目
    page.locator(".session-wrap button.ghost", has_text="会话").click()
    items = page.locator(".session-item")
    expect(items).to_have_count(2)
    items.nth(1).locator(".session-main").click()
    expect(page.locator(".msg", has_text="给大二学生讲").first).to_be_visible(timeout=10000)

    # 删除当前（旧）会话：两段式确认（点击条目后菜单已关，先重新打开）
    page.locator(".session-wrap button.ghost", has_text="会话").click()
    expect(page.locator(".session-item.active")).to_have_count(1)
    page.locator(".session-item.active .session-delete").click()
    expect(page.locator(".session-item.active .session-delete")).to_have_text(
        "确认删除资料及会话？"
    )
    page.locator(".session-item.active .session-delete").click()
    expect(page.locator(".msg")).to_have_count(0, timeout=10000)  # 回落到空白会话
    expect(page.locator(".session-wrap button.ghost")).to_contain_text("会话（1）")


@scenario("S10 冲突审核：面板可用（全新库暂无冲突）")
def s10_conflicts(page):
    page.locator(".tabs button", has_text="冲突审核").click()
    expect(page.locator(".panel", has_text="冲突待审")).to_be_visible()


@scenario("S11 资料删除、会话隔离与零会话工作区")
def s11_materials(page):
    page.locator(".tabs button", has_text="知识库").click()
    page.get_by_role("button", name="知识库", exact=True).click()
    page.locator("input[type=file]").set_input_files(
        str(Path(tempfile.gettempdir()) / "edumind_e2e_tcp讲义.docx")
    )
    expect(page.locator(".doc-item .doc-status").first).to_have_text("已完成", timeout=30000)
    page.get_by_role("button", name="会话（1）", exact=True).click()
    new_session(page)
    expect(page.locator(".doc-item")).to_have_count(0)
    page.get_by_role("button", name="会话（2）", exact=True).click()
    page.locator(".session-item:not(.active) .session-main").click()
    page.get_by_role("button", name="知识库", exact=True).click()
    expect(page.locator(".doc-item")).to_have_count(1)
    page.locator(".doc-delete").click()
    expect(page.get_by_role("alertdialog", name="删除资料确认")).to_contain_text(
        "edumind_e2e_tcp讲义.docx"
    )
    page.get_by_role("button", name="取消", exact=True).click()
    expect(page.locator(".doc-item")).to_have_count(1)
    page.locator(".doc-delete").click()
    page.get_by_role("button", name="确认删除资料", exact=True).click()
    expect(page.locator(".doc-item")).to_have_count(0)
    expect(page.locator(".node-item")).to_have_count(0)
    expect(page.get_by_role("button", name="生成知识图谱", exact=True)).to_be_disabled()
    for count in (2, 1):
        page.get_by_role("button", name=f"会话（{count}）", exact=True).click()
        page.locator(".session-item.active .session-delete").click()
        page.locator(".session-item.active .session-delete").click()
    expect(page.locator(".blank-thread")).to_be_visible()
    page.reload()
    expect(page.locator(".blank-thread")).to_be_visible()
    expect(page.locator(".composer")).to_have_count(0)
    expect(page.locator(".session-item")).to_have_count(0)
    expect(page.locator(".context-panel")).to_have_count(0)
    page.screenshot(path=str(ARTIFACTS / "workspace-desktop.png"), full_page=True)
    for width in (390, 768):
        page.set_viewport_size({"width": width, "height": 844})
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
        page.screenshot(path=str(ARTIFACTS / f"workspace-{width}.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 900})
    new_session(page)
    expect(page.get_by_role("textbox", name="教学需求")).to_have_value("")
    expect(page.locator(".msg.user")).to_have_count(0)


@scenario("S12 旧资料集中迁移且新会话保持空库")
def s12_legacy(page):
    content = (Path(tempfile.gettempdir()) / "edumind_e2e_tcp讲义.docx").read_bytes()
    response = page.request.post(
        BASE + "/api/v1/documents/upload",
        multipart={
            "file": {
                "name": "以前的讲义.docx",
                "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "buffer": content,
            }
        },
    )
    assert response.ok
    page.reload()
    page.get_by_role("button", name="会话（2）", exact=True).click()
    page.locator(".session-item", has_text="以前的资料").locator(".session-main").click()
    page.get_by_role("button", name="知识库", exact=True).click()
    expect(page.locator(".doc-item")).to_contain_text("以前的讲义.docx")
    page.get_by_role("button", name="会话（2）", exact=True).click()
    new_session(page)
    expect(page.locator(".doc-item")).to_have_count(0)


@scenario("S13 生成内容多选与单份材料持久化")
def s13_outputs(page):
    for label in ("Word 教案", "教学提纲"):
        page.get_by_role("checkbox", name=label, exact=True).uncheck()
    page.get_by_role("textbox", name="教学需求").fill("讲TCP，开始生成")
    page.get_by_role("button", name="发送", exact=True).click()
    expect(page.locator("button", has_text="备课中…")).to_have_count(0, timeout=60000)
    page.get_by_role("button", name="产物预览", exact=True).click()
    expect(page.locator("a.btn", has_text="PPT（")).to_be_visible()
    expect(page.locator("a.btn", has_text="Word 教案")).to_have_count(0)
    expect(page.locator("summary", has_text="查看教学提纲")).to_have_count(0)
    page.reload()
    expect(page.get_by_role("checkbox", name="Word 教案", exact=True)).not_to_be_checked()
    page.get_by_role("button", name="产物预览", exact=True).click()
    expect(page.locator("a.btn", has_text="PPT（")).to_be_visible()
    page.get_by_role("checkbox", name="PPT 课件", exact=True).uncheck()
    page.get_by_role("textbox", name="教学需求").fill("开始生成")
    expect(page.get_by_role("button", name="发送", exact=True)).to_be_disabled()
    page.get_by_role("checkbox", name="Word 教案", exact=True).check()
    page.get_by_role("button", name="发送", exact=True).click()
    expect(page.locator("button", has_text="备课中…")).to_have_count(0, timeout=60000)
    expect(page.locator("a.btn", has_text="Word 教案")).to_be_visible()
    expect(page.locator("a.btn", has_text="PPT（")).to_have_count(0)
    page.reload()
    page.get_by_role("button", name="产物预览", exact=True).click()
    expect(page.locator("a.btn", has_text="Word 教案")).to_be_visible()
    expect(page.locator(".target-toggle button.active")).to_have_text("教案")


@scenario("S14 参考资料开关、文件勾选与会话保存")
def s14_reference_selection(page):
    page.get_by_role("button", name="知识库", exact=True).click()
    page.get_by_role("button", name="知识库", exact=True).click()
    page.locator("input[type=file]").set_input_files(
        str(Path(tempfile.gettempdir()) / "edumind_e2e_tcp讲义.docx")
    )
    expect(page.locator(".doc-item .doc-status").first).to_have_text("已完成", timeout=30000)
    page.get_by_role("checkbox", name="使用参考资料", exact=True).check()
    page.get_by_role("textbox", name="教学需求").fill("讲TCP，开始生成")
    expect(page.get_by_role("button", name="发送", exact=True)).to_be_disabled()
    page.get_by_role("checkbox", name="参考 edumind_e2e_tcp讲义.docx", exact=True).check()
    expect(page.get_by_role("button", name="发送", exact=True)).to_be_enabled()
    page.reload()
    expect(page.get_by_role("checkbox", name="使用参考资料", exact=True)).to_be_checked()
    page.get_by_role("button", name="知识库", exact=True).click()
    expect(
        page.get_by_role("checkbox", name="参考 edumind_e2e_tcp讲义.docx", exact=True)
    ).to_be_checked()
    page.get_by_role("textbox", name="教学需求").fill("讲TCP，开始生成")
    page.get_by_role("button", name="发送", exact=True).click()
    expect(page.locator("button", has_text="备课中…")).to_have_count(0, timeout=60000)
    expect(page.locator(".msg.assistant").last).to_contain_text("本次命中的来源文档")
    page.get_by_role("checkbox", name="使用参考资料", exact=True).uncheck()
    page.get_by_role("textbox", name="教学需求").fill("开始生成")
    page.get_by_role("button", name="发送", exact=True).click()
    expect(page.locator("button", has_text="备课中…")).to_have_count(0, timeout=60000)
    expect(page.locator(".msg.assistant").last).to_contain_text("未使用上传资料")
    page.get_by_role("button", name="会话（3）", exact=True).click()
    new_session(page)
    expect(page.get_by_role("checkbox", name="使用参考资料", exact=True)).not_to_be_checked()
    expect(page.locator(".doc-item")).to_have_count(0)
    page.get_by_role("button", name="知识库", exact=True).click()
    page.locator("input[type=file]").set_input_files(
        str(Path(tempfile.gettempdir()) / "edumind_e2e_tcp讲义.docx")
    )
    expect(page.locator(".doc-item .doc-status").first).to_have_text("已完成", timeout=30000)
    page.get_by_role("checkbox", name="使用参考资料", exact=True).check()
    page.get_by_role("checkbox", name="参考 edumind_e2e_tcp讲义.docx", exact=True).check()
    page.locator(".doc-delete").click()
    page.get_by_role("button", name="确认删除资料", exact=True).click()
    expect(page.locator(".doc-item")).to_have_count(0)
    expect(
        page.get_by_role("button", name="查看并勾选资料（已选 0 份）", exact=True)
    ).to_be_visible()


@scenario("S15 无会话时隐藏输入框，新建后上传和发送可用")
def s15_direct_start(page):
    while page.locator(".session-item").count():
        page.locator(".session-item.active .session-delete").click()
        page.locator(".session-item.active .session-delete").click()
        expect(page.locator(".session-delete.confirm")).to_have_count(0)
    expect(page.locator(".blank-thread")).to_be_visible()
    expect(page.get_by_role("textbox", name="教学需求")).to_have_count(0)
    new_session(page)
    page.get_by_role("button", name="知识库", exact=True).click()
    page.locator("input[type=file]").set_input_files(
        str(Path(tempfile.gettempdir()) / "edumind_e2e_tcp讲义.docx")
    )
    expect(page.locator(".doc-item .doc-status").first).to_have_text("已完成", timeout=30000)
    expect(page.locator(".session-item")).to_have_count(1)
    page.reload()
    page.get_by_role("button", name="知识库", exact=True).click()
    expect(page.locator(".doc-item")).to_have_count(1)
    page.locator(".session-item.active .session-delete").click()
    page.locator(".session-item.active .session-delete").click()
    expect(page.locator(".session-item")).to_have_count(0)
    expect(page.locator(".composer")).to_have_count(0)
    new_session(page)
    page.get_by_role("textbox", name="教学需求").fill("讲TCP，开始生成")
    page.get_by_role("button", name="发送", exact=True).click()
    expect(page.locator("button", has_text="备课中…")).to_have_count(0, timeout=60000)
    expect(page.locator(".session-item")).to_have_count(1)
    expect(page.locator(".artifact-title", has_text="当前版本")).to_be_visible()
    page.reload()
    expect(page.locator(".msg.user")).to_contain_text("讲TCP")
    expect(page.locator(".thread-title")).to_have_text("TCP握手教案")


@scenario("S16 重命名当前及其他会话，取消和刷新保持内容")
def s16_rename(page):
    original = page.evaluate("JSON.parse(localStorage.getItem('edumind.sessions.v1')).sessions[0]")
    page.locator(".session-item.active .session-rename").click()
    dialog = page.get_by_role("dialog", name="重命名备课", exact=True)
    expect(dialog.get_by_role("textbox", name="会话名称")).to_have_value("TCP握手教案")
    dialog.get_by_role("textbox", name="会话名称").fill("   ")
    expect(dialog.get_by_role("button", name="保存名称")).to_be_disabled()
    dialog.get_by_role("button", name="取消", exact=True).click()
    expect(page.locator(".thread-title")).to_have_text("TCP握手教案")
    page.locator(".session-item.active .session-rename").click()
    dialog.get_by_role("textbox", name="会话名称").fill("  TCP三次握手 · 演示课  ")
    dialog.get_by_role("button", name="保存名称").click()
    expect(page.locator(".thread-title")).to_have_text("TCP三次握手 · 演示课")
    renamed = page.evaluate("JSON.parse(localStorage.getItem('edumind.sessions.v1')).sessions[0]")
    for key in ("id", "messages", "artifacts", "outputs", "referenceDocIds"):
        assert renamed[key] == original[key], f"重命名不应改变 {key}"
    new_session(page, "第二节课")
    page.locator(".session-item:not(.active) .session-rename").click()
    dialog.get_by_role("textbox", name="会话名称").fill("TCP备课定稿")
    dialog.get_by_role("button", name="保存名称").click()
    expect(page.locator(".thread-title")).to_have_text("第二节课")
    page.locator(".session-item:not(.active) .session-main").click()
    expect(page.locator(".thread-title")).to_have_text("TCP备课定稿")
    page.reload()
    expect(page.locator(".thread-title")).to_have_text("TCP备课定稿")
    page.get_by_role("button", name="产物预览", exact=True).click()
    expect(page.locator(".artifact-title", has_text="当前版本")).to_be_visible()


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_default_timeout(15000)
        for fn in (
            s1_smoke,
            s2_upload,
            s3_chat,
            s4_revise_ppt,
            s5_revise_word,
            s6_exam,
            s7_interactive,
            s8_persist,
            s9_sessions,
            s10_conflicts,
            s11_materials,
            s12_legacy,
            s13_outputs,
            s14_reference_selection,
            s15_direct_start,
            s16_rename,
        ):
            fn(page)
        browser.close()

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n===== E2E 结果：{len(RESULTS) - len(failed)}/{len(RESULTS)} 通过 =====")
    for name, _ok, err in failed:
        print(f"  FAIL {name}\n{err}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
