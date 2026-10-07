import {
  useEffect,
  useRef,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import "./App.css";
import HelpDialog from "./HelpDialog";
import NewSessionDialog from "./NewSessionDialog";
import KnowledgeGraph, {
  type GraphNode,
  type GraphEdge,
} from "./KnowledgeGraph";
import ModeSelector from "./ModeSelector";
import { MODE_DESCRIPTIONS } from "./modeOptions";
import { sessionFetch, fileUrl } from "./sessionApi";
import type { Artifacts, Message, ExamPaper, OutputType } from "./types";
import {
  createSession,
  freshStore,
  loadSessionStore,
  removeSession,
  saveSessionStore,
  sessionName,
  type SessionStore,
  type StoredSession,
} from "./sessionStore";

interface Doc {
  id: string;
  filename: string;
  file_type: string;
  status: string;
  is_reference?: boolean;
}

interface ConflictItem {
  id: string;
  diff_description: string;
  status: string;
  new_knowledge: { title?: string; content?: string } | null;
  existing_knowledge: { title?: string; content?: string } | null;
}

// 试卷按需生成（产物区一键）：每题标注考查知识点；生成题目自动入题库（来源=自编）

const TABS = ["知识库", "产物预览", "冲突审核"] as const;
const OUTPUT_OPTIONS: { id: OutputType; label: string }[] = [
  { id: "ppt", label: "PPT 课件" },
  { id: "word", label: "Word 教案" },
  { id: "outline", label: "教学提纲" },
  { id: "interactive", label: "互动内容" },
];

type ReviseTarget = "课件" | "教案";

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// 预览面板（双入口口径）：只展示会话内最新产物（当前版本）；历史产物仅落盘不展示；
// 修改意见只作用单个产物，方向性调整提示回对话区说明。
function PreviewPanel({
  artifacts,
  sessionId,
  exam,
  setExam,
  onBusy,
  disabledBusy,
  referencePolicy,
  revising,
  generatingInteractive,
  onRevise,
  onGenerateInteractive,
}: {
  referencePolicy: {
    use_reference_materials: boolean;
    reference_doc_ids: string[];
  };
  disabledBusy: boolean;
  sessionId: string;
  exam: ExamPaper | null;
  setExam: (exam: ExamPaper | null) => void;
  onBusy: (busy: boolean) => void;
  artifacts: Artifacts | null;
  revising: boolean;
  generatingInteractive: boolean;
  onRevise: (target: ReviseTarget, feedback: string) => Promise<boolean>;
  onGenerateInteractive: () => Promise<boolean>;
}) {
  const [feedback, setFeedback] = useState("");
  const [target, setTarget] = useState<ReviseTarget>(
    artifacts?.ppt ? "课件" : "教案",
  );
  const reviseTarget: ReviseTarget =
    target === "课件"
      ? artifacts?.ppt
        ? "课件"
        : "教案"
      : artifacts?.word
        ? "教案"
        : "课件";
  const fetch = (url: string, options?: RequestInit) =>
    sessionFetch(sessionId, url, options);
  const [generatingExam, setGeneratingExam] = useState(false);
  const [examError, setExamError] = useState("");

  if (!artifacts) {
    return (
      <div className="empty-state">
        <span className="empty-icon" aria-hidden="true">
          ▤
        </span>
        <h3>生成后，你的教学材料会出现在这里</h3>
        <p>
          先在对话区说明主题、年级和时长。材料生成后，在这里下载课件、教案，或继续修改。
        </p>
        <div className="empty-checklist">PPT 课件 · Word 教案 · 教学提纲</div>
      </div>
    );
  }

  // 一键生成试卷：透传本次备课意图，后端检索知识内容自编出题并入题库
  async function generateExam() {
    if (disabledBusy || generatingExam || !artifacts) return;
    setGeneratingExam(true);
    onBusy(true);
    setExamError("");
    try {
      const res = await fetch("/api/v1/exam/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ intent: artifacts.intent, ...referencePolicy }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setExam(await res.json());
    } catch {
      setExam(null);
      setExamError("试卷生成失败，请重试");
    } finally {
      setGeneratingExam(false);
      onBusy(false);
    }
  }

  async function revise() {
    const text = feedback.trim();
    if (!text || revising) return;
    const ok = await onRevise(reviseTarget, text);
    if (ok) setFeedback("");
  }

  return (
    <div className="artifacts">
      <div className="artifact-title">
        📦 当前版本（
        {artifacts.knowledge_hits ? "已融合知识库" : "AI 直接生成"}）
      </div>
      <div className="artifact-buttons">
        {artifacts.ppt && (
          <a
            className="btn"
            href={fileUrl(sessionId, artifacts.ppt.filename)}
            download
          >
            ⬇ PPT（{artifacts.ppt.slides.length} 页）
          </a>
        )}
        {artifacts.word && (
          <a
            className="btn"
            href={fileUrl(sessionId, artifacts.word.filename)}
            download
          >
            ⬇ Word 教案
          </a>
        )}
        <button
          className="btn"
          onClick={generateExam}
          disabled={disabledBusy || generatingExam}
          title="根据本次备课意图与知识库自编试卷，题目自动收入题库"
        >
          {generatingExam ? "出题中…" : "📝 生成试卷"}
        </button>
        {exam && (
          <a className="btn" href={fileUrl(sessionId, exam.filename)} download>
            ⬇ 试卷（{exam.questions.length} 题）
          </a>
        )}
        {artifacts.interactive && (
          <a
            className="btn"
            href={fileUrl(sessionId, artifacts.interactive.filename, true)}
            target="_blank"
            rel="noreferrer"
            title="在新标签页打开互动内容（HTML5 小游戏/动画）"
          >
            ▶ 互动内容
          </a>
        )}
        <button
          className="btn"
          onClick={() => void onGenerateInteractive()}
          disabled={disabledBusy || generatingInteractive}
          title="按本次备课意图生成本节课的互动内容（HTML5 小游戏/知识点动画）"
        >
          {generatingInteractive ? "生成中…" : "✨ 生成互动内容"}
        </button>
      </div>
      {examError && <p className="placeholder">{examError}</p>}
      {exam && (
        <details className="artifact-outline" open>
          <summary>
            预览试卷（{exam.questions.length} 题，已入库 {exam.bank_saved} 题）
          </summary>
          <ol className="exam-preview">
            {exam.questions.map((q, i) => (
              <li key={i}>
                <span className="tag">[{q.type}]</span>{" "}
                {q.knowledge_point && (
                  <span className="tag">考查知识点：{q.knowledge_point}</span>
                )}
                <div>{q.content}</div>
              </li>
            ))}
          </ol>
        </details>
      )}
      {(artifacts.ppt || artifacts.word) && (
        <>
          <div className="target-toggle" role="group" aria-label="修改对象">
            {(["课件", "教案"] as ReviseTarget[])
              .filter((t) =>
                t === "课件" ? !!artifacts.ppt : !!artifacts.word,
              )
              .map((t) => (
                <button
                  key={t}
                  className={t === reviseTarget ? "active" : ""}
                  onClick={() => setTarget(t)}
                >
                  {t}
                </button>
              ))}
          </div>
          <div className="revise-area">
            <input
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && revise()}
              placeholder={
                reviseTarget === "课件"
                  ? "修改课件：简化某页 / 增加一个案例 / 调整顺序"
                  : "修改教案：调整环节 / 增加活动 / 改作业"
              }
            />
            <button
              onClick={revise}
              disabled={
                disabledBusy ||
                revising ||
                (reviseTarget === "教案" && !artifacts.word?.data)
              }
            >
              {revising ? "调整中…" : "修改"}
            </button>
          </div>
          <p className="revise-hint">
            💡 方向性调整（主题/学段/目标级变化）请回对话区说明
          </p>
        </>
      )}
      {artifacts.outline && (
        <details className="artifact-outline">
          <summary>查看教学提纲</summary>
          <pre>{artifacts.outline}</pre>
        </details>
      )}
    </div>
  );
}

function useSessionDocuments(sessionId: string, refreshKey: number) {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    async function load() {
      try {
        const response = await sessionFetch(sessionId, "/api/v1/documents");
        if (!response.ok) throw new Error("资料列表加载失败，请稍后重试");
        const data = await response.json();
        if (cancelled) return;
        setDocs(data.documents ?? []);
        setError("");
        if (
          (data.documents ?? []).some((doc: Doc) =>
            ["处理中", "解析中"].includes(doc.status),
          )
        )
          timer = window.setTimeout(load, 2000);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "资料列表加载失败");
          timer = window.setTimeout(load, 3000);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [sessionId, refreshKey]);
  return { docs, error };
}

function KnowledgePanel({
  refreshKey,
  sessionId,
  disabled,
  onChange,
  docs,
  useReferences,
  selectedIds,
  onToggleReference,
  onUpload,
  uploading,
}: {
  onUpload: () => void;
  uploading: boolean;
  docs: Doc[];
  useReferences: boolean;
  selectedIds: string[];
  onToggleReference: (id: string) => void;
  refreshKey: number;
  sessionId: string;
  disabled: boolean;
  onChange: (deletedId: string) => void;
}) {
  const [pendingDelete, setPendingDelete] = useState<Doc | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  async function deleteDoc() {
    if (!pendingDelete || deleting) return;
    setDeleting(true);
    setError("");
    try {
      const res = await sessionFetch(
        sessionId,
        `/api/v1/documents/${pendingDelete.id}`,
        { method: "DELETE" },
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "删除失败，请重试");
      setPendingDelete(null);
      onChange(pendingDelete.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败，请重试");
    } finally {
      setDeleting(false);
    }
  }
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [graphOpen, setGraphOpen] = useState(false);
  const [graphError, setGraphError] = useState("");
  const [graphLoading, setGraphLoading] = useState(true);
  const [graphRefresh, setGraphRefresh] = useState(0);

  // refreshKey 变化（如刚完成上传）时重新拉取；存在「处理中」文档时轮询直至终态
  useEffect(() => {
    let cancelled = false;
    async function load() {
      setGraphLoading(true);
      setGraphError("");
      try {
        const response = await sessionFetch(
          sessionId,
          "/api/v1/knowledge/graph",
        );
        if (!response.ok) throw new Error("知识图谱加载失败，请重试");
        const data = await response.json();
        if (cancelled) return;
        setNodes(data.nodes ?? []);
        setEdges(data.edges ?? []);
      } catch {
        if (!cancelled) setGraphError("知识图谱加载失败，请重试");
      } finally {
        if (!cancelled) setGraphLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [refreshKey, sessionId, docs, graphRefresh]);

  return (
    <div className="panel">
      {graphOpen && (
        <KnowledgeGraph
          nodes={nodes}
          edges={edges}
          onClose={() => setGraphOpen(false)}
        />
      )}
      {pendingDelete && (
        <div
          className="delete-confirm"
          role="alertdialog"
          aria-label="删除资料确认"
        >
          <strong>删除「{pendingDelete.filename}」？</strong>
          <p>
            原文件和这份资料提取的知识将从当前会话移除，已生成的教学材料会保留。
          </p>
          {error && (
            <p role="alert" className="action-error">
              {error}
            </p>
          )}
          <div>
            <button onClick={() => setPendingDelete(null)} disabled={deleting}>
              取消
            </button>
            <button
              className="danger-button"
              onClick={() => void deleteDoc()}
              disabled={deleting}
            >
              {deleting ? "删除中…" : "确认删除资料"}
            </button>
          </div>
        </div>
      )}
      <p className="scope-note">
        {useReferences
          ? "勾选本次要参考的资料，解析完成后可选用"
          : "资料保存在当前会话，开启“使用参考资料”后可勾选"}
      </p>
      <div className="documents-toolbar">
        <h4>📁 已上传文档（{docs.length}）</h4>
        <button
          className="materials-upload"
          type="button"
          disabled={disabled}
          onClick={onUpload}
          aria-label="上传资料"
          title="上传资料并保存在当前会话"
        >
          {uploading ? "上传中…" : "＋ 上传资料"}
        </button>
      </div>
      {docs.length === 0 && (
        <p className="placeholder">
          暂时没有资料。点击“上传资料”添加教材或讲义，也可以直接开始备课。
        </p>
      )}
      {docs.map((d) => (
        <div key={d.id} className="doc-item">
          {useReferences ? (
            <label className="doc-reference">
              <input
                type="checkbox"
                aria-label={`参考 ${d.filename}`}
                checked={selectedIds.includes(d.id)}
                disabled={disabled || !["已完成", "有冲突"].includes(d.status)}
                onChange={() => onToggleReference(d.id)}
              />
              <span className="doc-name">{d.filename}</span>
            </label>
          ) : (
            <span className="doc-name">{d.filename}</span>
          )}
          {useReferences && selectedIds.includes(d.id) && (
            <span className="tag">已选参考</span>
          )}
          <span className={`doc-status ${d.status}`}>{d.status}</span>
          <button
            className="doc-delete"
            aria-label={`删除资料 ${d.filename}`}
            disabled={
              disabled || deleting || ["处理中", "解析中"].includes(d.status)
            }
            onClick={() => {
              setError("");
              setPendingDelete(d);
            }}
          >
            删除
          </button>
        </div>
      ))}
      <div className="knowledge-toolbar">
        <h4>
          提取的知识点（{nodes.length} 个 / {edges.length} 条关联）
        </h4>
        <button
          type="button"
          aria-haspopup="dialog"
          disabled={graphLoading || !nodes.length || !!graphError}
          onClick={() => setGraphOpen(true)}
        >
          {graphLoading ? "加载中…" : "生成知识图谱"}
        </button>
      </div>
      {graphError && (
        <p className="action-error" role="alert">
          {graphError}{" "}
          <button onClick={() => setGraphRefresh((n) => n + 1)}>
            重新加载图谱
          </button>
        </p>
      )}
      {nodes.length === 0 && (
        <p className="placeholder">上传资料后自动提取知识点</p>
      )}
      {nodes.slice(0, 30).map((n) => (
        <div key={n.id} className="node-item">
          {n.title}
          {n.difficulty && <span className="tag">{n.difficulty}</span>}
        </div>
      ))}
      {nodes.length > 30 && (
        <p className="placeholder">
          列表展示前 30 个知识点，生成图谱可查看全部知识点。
        </p>
      )}
    </div>
  );
}

function ConflictPanel({ sessionId }: { sessionId: string }) {
  const fetch = (url: string, options?: RequestInit) =>
    sessionFetch(sessionId, url, options);
  const [conflicts, setConflicts] = useState<ConflictItem[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    try {
      const r = await fetch("/api/v1/conflicts");
      const d = await r.json();
      setConflicts(d.conflicts ?? []);
    } catch {
      // 后端不可达时保留现有列表
    }
  }

  useEffect(() => {
    let cancelled = false;
    sessionFetch(sessionId, "/api/v1/conflicts")
      .then((r) => r.json())
      .then((d) => {
        if (!cancelled) setConflicts(d.conflicts ?? []);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // 教师三选一（ADR-0001）：接受新=替换旧节点；保留旧=丢弃新知；并存=双留并标注差异
  async function review(id: string, action: "接受新" | "保留旧" | "并存") {
    if (busyId) return;
    setBusyId(id);
    try {
      await fetch(`/api/v1/conflicts/${id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      await load();
    } catch {
      // 审核失败时保留待审状态，可重试
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="panel">
      <h4>
        ⚠️ 冲突待审（{conflicts.filter((c) => c.status === "待审").length}）
      </h4>
      {conflicts.length === 0 && (
        <p className="placeholder">
          暂时没有需要审核的知识差异。上传资料后，如果发现不同说法，会在这里提醒你。
        </p>
      )}
      {conflicts.map((c) => (
        <div key={c.id} className="conflict-item">
          <div className="conflict-titles">
            <span className="tag">{c.existing_knowledge?.title ?? "?"}</span>
            <span>→</span>
            <span className="tag">{c.new_knowledge?.title ?? "?"}</span>
            <span className="doc-status">{c.status}</span>
          </div>
          {c.diff_description && (
            <p className="conflict-desc">差异：{c.diff_description}</p>
          )}
          {(c.existing_knowledge?.content || c.new_knowledge?.content) && (
            <div className="conflict-body">
              <p>旧：{c.existing_knowledge?.content ?? "（无）"}</p>
              <p>新：{c.new_knowledge?.content ?? "（无）"}</p>
            </div>
          )}
          {c.status === "待审" && (
            <div className="conflict-actions">
              <button
                disabled={busyId === c.id}
                onClick={() => review(c.id, "接受新")}
                title="用新知识替换旧节点"
              >
                接受新
              </button>
              <button
                disabled={busyId === c.id}
                onClick={() => review(c.id, "保留旧")}
                title="丢弃新知，保留旧节点"
              >
                保留旧
              </button>
              <button
                disabled={busyId === c.id}
                onClick={() => review(c.id, "并存")}
                title="新旧双节点保留并标注差异"
              >
                并存
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function Workspace({
  store,
  setStore,
  initialDraft,
  active,
}: {
  active: StoredSession;
  store: SessionStore;
  setStore: Dispatch<SetStateAction<SessionStore>>;
  initialDraft: string;
}) {
  const [input, setInput] = useState(initialDraft);
  const [helpOpen, setHelpOpen] = useState(false);
  const [newSessionOpen, setNewSessionOpen] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const renamingSession = store.sessions.find((s) => s.id === renamingId);
  const [materialsOpen, setMaterialsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>("知识库");
  const [sending, setSending] = useState(false);
  const [listening, setListening] = useState(false);
  const [revising, setRevising] = useState(false);
  const [generatingInteractive, setGeneratingInteractive] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [examBusy, setExamBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deletingSession, setDeletingSession] = useState(false);
  const [sessionError, setSessionError] = useState("");
  const busy =
    sending ||
    revising ||
    generatingInteractive ||
    examBusy ||
    uploading ||
    deletingSession;
  const fetch = (url: string, options?: RequestInit) =>
    sessionFetch(active.id, url, options);
  const [kbRefresh, setKbRefresh] = useState(0);
  const { docs, error: documentsError } = useSessionDocuments(
    active.id,
    kbRefresh,
  );
  const selectedReferenceIds = active.referenceDocIds.filter((id) =>
    docs.some((d) => d.id === id && ["已完成", "有冲突"].includes(d.status)),
  );
  const referencePolicy = {
    use_reference_materials: active.useReferenceMaterials,
    reference_doc_ids: active.useReferenceMaterials ? selectedReferenceIds : [],
  };
  const referencesReady =
    !active.useReferenceMaterials ||
    (selectedReferenceIds.length > 0 && !documentsError);
  function toggleReference(id: string) {
    updateActive((s) => ({
      referenceDocIds: s.referenceDocIds.includes(id)
        ? s.referenceDocIds.filter((x) => x !== id)
        : [...s.referenceDocIds, id],
    }));
  }
  // 上传后触发知识库面板刷新
  const recognitionRef = useRef<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const teachingInputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => () => recognitionRef.current?.stop(), []);

  // 当前会话更新统一入口（消息/生成物/追问粒度），顺带刷新 updatedAt 供会话列表排序
  function updateActive(fn: (s: StoredSession) => Partial<StoredSession>) {
    setStore((st) => {
      const current = st.sessions.find((s) => s.id === active.id) ?? active;
      const updated = {
        ...current,
        ...fn(current),
        updatedAt: new Date().toISOString(),
      };
      return {
        ...st,
        activeId: active.id,
        sessions: st.sessions.some((s) => s.id === active.id)
          ? st.sessions.map((s) => (s.id === active.id ? updated : s))
          : [updated, ...st.sessions],
      };
    });
  }

  function appendMessages(...msgs: Message[]) {
    updateActive((s) => ({ messages: [...s.messages, ...msgs] }));
  }

  // 多会话：新建 / 切换 / 删除；删空后展示新建备课欢迎页
  function startNewSession(name: string) {
    if (busy) return;
    const s = { ...createSession(), name, nameManuallySet: true };
    setStore((st) => ({
      ...st,
      activeId: s.id,
      sessions: [s, ...st.sessions],
    }));
    setMenuOpen(false);
    setNewSessionOpen(false);
    setPendingDeleteId(null);
  }

  function switchTo(id: string) {
    if (busy) return;
    setStore((st) => ({ ...st, activeId: id }));
    setMenuOpen(false);
    setPendingDeleteId(null);
  }

  function renameSession(name: string) {
    if (busy || !renamingId) return;
    setStore((st) => ({
      ...st,
      sessions: st.sessions.map((s) =>
        s.id === renamingId
          ? {
              ...s,
              name,
              nameManuallySet: true,
              updatedAt: new Date().toISOString(),
            }
          : s,
      ),
    }));
    setRenamingId(null);
  }

  async function deleteSession(id: string) {
    if (busy) return;
    if (pendingDeleteId !== id) {
      setPendingDeleteId(id); // 两段式确认，防误删
      return;
    }
    setDeletingSession(true);
    setSessionError("");
    try {
      const res = await sessionFetch(id, `/api/v1/sessions/${id}`, {
        method: "DELETE",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "删除会话失败，请重试");
      setStore((st) => removeSession(st, id));
      setPendingDeleteId(null);
      setMenuOpen(false);
    } catch (e) {
      setSessionError(e instanceof Error ? e.message : "删除会话失败，请重试");
    } finally {
      setDeletingSession(false);
    }
  }

  async function send() {
    const text = input.trim();
    if (!text || busy || active.outputs.length === 0 || !referencesReady)
      return;
    const userMsg: Message = { role: "user", content: text };
    const history = [...active.messages, userMsg];
    // 首条教师消息到达时给会话命名，便于按班级/课程区分
    const isFirstUserMsg = active.messages.every((m) => m.role !== "user");
    updateActive((s) => ({
      messages: [...s.messages, userMsg],
      ...(isFirstUserMsg && !s.nameManuallySet
        ? { name: sessionName(history) ?? s.name }
        : {}),
    }));
    setInput("");
    setSending(true);
    try {
      const res = await fetch("/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: history.map((m) => ({ role: m.role, content: m.content })),
          granularity: active.granularity,
          ...referencePolicy,
          outputs: active.outputs,
        }),
      });
      const data = await res.json();
      const artifacts = data.artifacts;
      if (artifacts) {
        updateActive(() => ({ artifacts, exam: null }));
        setActiveTab("产物预览");
        setMaterialsOpen(true);
      }
      appendMessages({
        role: "assistant",
        content:
          data.content ?? data.detail ?? `（后端响应异常：${res.status}）`,
      });
    } catch {
      appendMessages({
        role: "assistant",
        content: "（无法连接后端，请先启动服务）",
      });
    } finally {
      setSending(false);
    }
  }

  // 修改闭环（双入口）：预览面板输入=修改意见，只作用单个产物；
  // 新文件落盘后替换当前版本（当前会话的生成物），历史文件仅留磁盘不展示。
  async function reviseArtifact(
    target: ReviseTarget,
    feedback: string,
  ): Promise<boolean> {
    const lastArtifacts = active.artifacts;
    if (!lastArtifacts || busy) return false;
    setRevising(true);
    try {
      if (target === "课件") {
        if (!lastArtifacts.ppt) return false;
        const res = await fetch("/api/v1/revise", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slides: lastArtifacts.ppt.slides, feedback }),
        });
        if (!res.ok) return false;
        const data = await res.json();
        updateActive(() => ({
          artifacts: {
            ...lastArtifacts,
            ppt: {
              ...lastArtifacts.ppt,
              path: data.path ?? lastArtifacts.ppt?.path ?? "",
              slides: data.slides,
              filename: data.filename,
            },
          },
        }));
      } else {
        if (!lastArtifacts.word) return false;
        const res = await fetch("/api/v1/revise/word", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            word: lastArtifacts.word.data,
            feedback,
            references: lastArtifacts.references,
          }),
        });
        if (!res.ok) return false;
        const data = await res.json();
        updateActive(() => ({
          artifacts: {
            ...lastArtifacts,
            word: {
              ...lastArtifacts.word,
              path: data.path ?? lastArtifacts.word?.path ?? "",
              data: data.word,
              filename: data.filename,
            },
          },
        }));
      }
      return true;
    } catch {
      // 修改失败时保持当前版本不变
      return false;
    } finally {
      setRevising(false);
    }
  }

  // 互动内容一键生成（产物区入口）：按上次备课意图生成单文件 HTML；
  // 对话中的互动诉求命中时由后端自动附带，无需教师额外操作。
  async function generateInteractive(): Promise<boolean> {
    const lastArtifacts = active.artifacts;
    if (!lastArtifacts || busy || !referencesReady) return false;
    setGeneratingInteractive(true);
    try {
      const res = await fetch("/api/v1/interactive/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          intent: lastArtifacts.intent,
          ...referencePolicy,
        }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      updateActive(() => ({
        artifacts: {
          ...lastArtifacts,
          interactive: { html: data.html, filename: data.filename },
        },
      }));
      return true;
    } catch {
      // 生成失败时保持当前版本不变
      return false;
    } finally {
      setGeneratingInteractive(false);
    }
  }

  async function uploadFile(file: File) {
    if (busy) return;
    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch("/api/v1/documents/upload", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "上传失败");
      appendMessages({
        role: "assistant",
        content: `已上传「${file.name}」，保存在当前会话。解析完成后可勾选为参考资料。`,
      });
      void data;
      setKbRefresh((n) => n + 1);
    } catch {
      appendMessages({
        role: "assistant",
        content: `上传「${file.name}」失败`,
      });
    } finally {
      setUploading(false);
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) uploadFile(file);
    e.target.value = "";
  }

  function toggleVoice() {
    const SR =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;
    if (!SR) {
      appendMessages({
        role: "assistant",
        content: "（当前浏览器不支持语音输入，请使用 Chrome）",
      });
      return;
    }
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }
    const recognition = new SR();
    recognition.lang = "zh-CN";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event: any) => {
      let transcript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      setInput(transcript);
    };
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  }

  // 会话列表按最近使用排序展示
  const sortedSessions = [...store.sessions].sort((a, b) =>
    b.updatedAt.localeCompare(a.updatedAt),
  );

  return (
    <div className="app">
      <aside
        className={`conversation-sidebar${menuOpen ? " open" : ""}`}
        aria-label="备课会话列表"
      >
        <div className="sidebar-brand">
          <div className="logo">EduMind</div>
          <button
            className="sidebar-close"
            aria-label="关闭会话列表"
            onClick={() => setMenuOpen(false)}
          >
            ×
          </button>
        </div>
        <button
          className="session-new"
          disabled={busy}
          onClick={() => setNewSessionOpen(true)}
          aria-haspopup="dialog"
        >
          ＋ 新建备课
        </button>
        <div className="session-wrap">
          <button
            className="ghost session-count"
            onClick={() => setPendingDeleteId(null)}
          >
            会话（{store.sessions.length}）
          </button>
        </div>
        <div className="session-list">
          {store.sessions.length === 0 && (
            <p className="sidebar-empty">你的备课会保存在这里</p>
          )}
          {sortedSessions.map((s) => (
            <div
              key={s.id}
              className={`session-item${s.id === active.id ? " active" : ""}`}
            >
              <div
                className="session-main"
                role="button"
                tabIndex={busy ? -1 : 0}
                aria-disabled={busy}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    switchTo(s.id);
                  }
                }}
                onClick={() => switchTo(s.id)}
              >
                <div className="session-name">
                  {s.name}
                  {s.id === active.id && <span className="tag">当前</span>}
                </div>
                <div className="session-meta">
                  {formatTime(s.updatedAt)} · {s.messages.length} 条消息
                  {s.artifacts ? " · 已有产物" : ""}
                </div>
              </div>
              <button
                disabled={busy}
                className="session-rename"
                aria-label={`重命名 ${s.name}`}
                aria-haspopup="dialog"
                onClick={() => {
                  setPendingDeleteId(null);
                  setRenamingId(s.id);
                }}
              >
                重命名
              </button>
              <button
                disabled={busy}
                className={`session-delete${pendingDeleteId === s.id ? " confirm" : ""}`}
                onClick={(e) => {
                  e.stopPropagation();
                  deleteSession(s.id);
                }}
              >
                {pendingDeleteId === s.id ? "确认删除资料及会话？" : "删除"}
              </button>
            </div>
          ))}
        </div>
        {sessionError && (
          <p className="action-error" role="alert">
            {sessionError}
          </p>
        )}
        {busy && <p className="sidebar-note">任务完成后可切换会话</p>}
        <button
          className="sidebar-help"
          aria-label="使用帮助"
          aria-haspopup="dialog"
          onClick={() => setHelpOpen(true)}
        >
          使用帮助
        </button>
      </aside>
      {menuOpen && (
        <div className="sidebar-overlay" onClick={() => setMenuOpen(false)} />
      )}
      <header className="topbar">
        <button
          className="sidebar-toggle"
          aria-label="打开会话列表"
          onClick={() => setMenuOpen(!menuOpen)}
        >
          ☰
        </button>
        <div className="thread-title">
          {store.sessions.some((s) => s.id === active.id)
            ? active.name
            : "新建备课"}
        </div>
        <div className="spacer" />
        {store.sessions.length > 0 && (
          <div className="tabs" aria-label="教学材料入口">
            {TABS.map((tab) => (
              <button
                key={tab}
                className={materialsOpen && tab === activeTab ? "active" : ""}
                onClick={() => {
                  setActiveTab(tab);
                  setMaterialsOpen(true);
                }}
              >
                {tab}
              </button>
            ))}
          </div>
        )}
      </header>

      {helpOpen && <HelpDialog onClose={() => setHelpOpen(false)} />}
      {newSessionOpen && (
        <NewSessionDialog
          onCreate={startNewSession}
          onClose={() => setNewSessionOpen(false)}
        />
      )}
      {renamingSession && (
        <NewSessionDialog
          key={renamingSession.id}
          editing
          initialName={renamingSession.name}
          onCreate={renameSession}
          onClose={() => setRenamingId(null)}
        />
      )}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.pptx,.png,.jpg,.jpeg,.mp4,.mp3,.wav,.m4a,.aac,.flac,.ogg,.oga,.opus,.wma,.amr"
        style={{ display: "none" }}
        onChange={handleFileChange}
      />

      <div className={`main${materialsOpen ? " with-materials" : ""}`}>
        <section className="chat-panel">
          <div
            className={`chat-history${active.messages.length === 1 ? " is-empty" : ""}`}
            role="log"
            aria-label="备课对话记录"
            aria-live="polite"
          >
            {active.messages.length === 1 ? (
              <div className="blank-thread">
                <h1>这节课，想怎么讲？</h1>
                <p>
                  {store.sessions.length > 0
                    ? "描述教学需求，选择要生成的材料。"
                    : "新建备课会话，开始准备这节课。"}
                </p>
              </div>
            ) : (
              active.messages.map((m, i) => (
                <div key={i} className={`msg ${m.role}`}>
                  <span className="message-author">
                    {m.role === "assistant" ? "EduMind" : "你"}
                  </span>
                  <div>{m.content}</div>
                </div>
              ))
            )}
          </div>
          {store.sessions.length > 0 && (
            <div className="composer">
              <fieldset className="output-options" disabled={busy}>
                <legend>
                  生成内容 <span>可多选</span>
                </legend>
                <div>
                  {OUTPUT_OPTIONS.map((option) => (
                    <label
                      key={option.id}
                      className={
                        active.outputs.includes(option.id) ? "selected" : ""
                      }
                    >
                      <input
                        type="checkbox"
                        checked={active.outputs.includes(option.id)}
                        onChange={() =>
                          updateActive((s) => ({
                            outputs: s.outputs.includes(option.id)
                              ? s.outputs.filter((x) => x !== option.id)
                              : [...s.outputs, option.id],
                          }))
                        }
                      />
                      {option.label}
                    </label>
                  ))}
                </div>
                {active.outputs.length === 0 && (
                  <p role="status">请至少选择一种生成内容</p>
                )}
              </fieldset>

              <div className="reference-controls">
                <label>
                  <input
                    type="checkbox"
                    checked={active.useReferenceMaterials}
                    disabled={busy}
                    onChange={(e) =>
                      updateActive(() => ({
                        useReferenceMaterials: e.target.checked,
                      }))
                    }
                  />
                  使用参考资料
                </label>
                {active.useReferenceMaterials ? (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        setActiveTab("知识库");
                        setMaterialsOpen(true);
                      }}
                    >
                      查看并勾选资料（已选 {selectedReferenceIds.length} 份）
                    </button>
                    <span>
                      {referencesReady
                        ? "仅参考勾选的文件"
                        : "请在知识库中勾选已解析的资料"}
                    </span>
                  </>
                ) : (
                  <span>关闭时根据教学需求直接生成</span>
                )}
                {documentsError && (
                  <span className="action-error" role="alert">
                    {documentsError}
                  </span>
                )}
              </div>
              <div className="input-area">
                <textarea
                  rows={3}
                  ref={teachingInputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) =>
                    e.key === "Enter" &&
                    !e.shiftKey &&
                    !e.nativeEvent.isComposing &&
                    (e.preventDefault(), send())
                  }
                  placeholder="输入教学需求"
                  aria-label="教学需求"
                />
                <ModeSelector
                  value={active.granularity}
                  disabled={busy}
                  onChange={(granularity) =>
                    updateActive(() => ({ granularity }))
                  }
                />
                <button
                  onClick={send}
                  disabled={
                    busy ||
                    !input.trim() ||
                    active.outputs.length === 0 ||
                    !referencesReady
                  }
                >
                  {sending ? "备课中…" : "发送"}
                </button>
              </div>
              <div className="composer-footer">
                <div className="composer-tools">
                  <button
                    className={listening ? "voice listening" : "voice"}
                    onClick={toggleVoice}
                    title="使用浏览器语音识别，将说话内容填入输入框"
                    aria-label={listening ? "停止语音输入" : "语音输入"}
                  >
                    {listening ? "停止录入" : "语音输入"}
                  </button>
                </div>
                <div className="composer-caption">
                  <span className="mode-description">
                    {MODE_DESCRIPTIONS[active.granularity]}
                  </span>
                  <span className="keyboard-hint">
                    Enter 发送 · Shift + Enter 换行
                  </span>
                </div>
              </div>
            </div>
          )}
        </section>

        {materialsOpen && (
          <aside className="context-panel">
            <div className="materials-heading">
              <h2>{activeTab}</h2>
              <button
                className="materials-close"
                aria-label="关闭教学材料"
                onClick={() => setMaterialsOpen(false)}
                disabled={examBusy}
              >
                ×
              </button>
            </div>
            <div className="tab-content">
              {activeTab === "知识库" && (
                <KnowledgePanel
                  onUpload={() => fileInputRef.current?.click()}
                  uploading={uploading}
                  key={active.id}
                  sessionId={active.id}
                  refreshKey={kbRefresh}
                  disabled={busy}
                  docs={docs}
                  useReferences={active.useReferenceMaterials}
                  selectedIds={selectedReferenceIds}
                  onToggleReference={toggleReference}
                  onChange={(id) => {
                    updateActive((s) => ({
                      referenceDocIds: s.referenceDocIds.filter(
                        (x) => x !== id,
                      ),
                    }));
                    setKbRefresh((n) => n + 1);
                  }}
                />
              )}
              {activeTab === "产物预览" && (
                <PreviewPanel
                  key={active.id}
                  referencePolicy={referencePolicy}
                  disabledBusy={busy || !referencesReady}
                  sessionId={active.id}
                  exam={active.exam ?? null}
                  setExam={(exam) => updateActive(() => ({ exam }))}
                  onBusy={setExamBusy}
                  artifacts={active.artifacts}
                  revising={revising}
                  generatingInteractive={generatingInteractive}
                  onRevise={reviseArtifact}
                  onGenerateInteractive={generateInteractive}
                />
              )}
              {activeTab === "冲突审核" && (
                <ConflictPanel key={active.id} sessionId={active.id} />
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}

function App() {
  const [store, setStore] = useState<SessionStore>(
    () => loadSessionStore() ?? freshStore(),
  );
  const [migrationError, setMigrationError] = useState("");
  const [ready, setReady] = useState(false);
  useEffect(() => {
    saveSessionStore(store);
  }, [store]);
  useEffect(() => {
    let cancelled = false;
    async function migrate() {
      try {
        const stored = loadSessionStore() ?? freshStore();
        for (const session of stored.sessions) {
          const a = session.artifacts;
          const filenames = [
            a?.ppt?.filename,
            a?.word?.filename,
            a?.interactive?.filename,
            session.exam?.filename,
          ].filter((x): x is string => !!x);
          if (filenames.length) {
            const res = await sessionFetch(
              session.id,
              "/api/v1/sessions/import-files",
              {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ filenames }),
              },
            );
            if (!res.ok)
              throw new Error("旧教学材料暂时无法恢复，请检查后端服务后刷新。");
          }
        }
        const response = await window.fetch("/api/v1/sessions/legacy");
        if (!response.ok)
          throw new Error("资料服务暂时不可用，请启动后端后刷新。");
        const legacy = await response.json();
        if (cancelled) return;
        if (legacy.document_count > 0)
          setStore((st) => {
            if (st.sessions.some((s) => s.id === "legacy")) return st;
            const archive = {
              ...createSession(),
              id: "legacy",
              name: "以前的资料",
            };
            return {
              ...st,
              activeId: st.activeId || archive.id,
              sessions: [...st.sessions, archive],
            };
          });
        setReady(true);
      } catch (e) {
        if (!cancelled)
          setMigrationError(
            e instanceof Error ? e.message : "资料恢复失败，请刷新重试。",
          );
      }
    }
    void migrate();
    return () => {
      cancelled = true;
    };
  }, []);
  const active = store.sessions.find((s) => s.id === store.activeId);
  const isEmpty = store.sessions.length === 0;
  const blank = useMemo(() => (isEmpty ? createSession() : null), [isEmpty]);
  if (!ready)
    return (
      <div className="startup-state">
        <div className="logo">EduMind</div>
        <p role={migrationError ? "alert" : "status"}>
          {migrationError || "正在准备你的备课空间…"}
        </p>
        {migrationError && (
          <button onClick={() => window.location.reload()}>重新加载</button>
        )}
      </div>
    );
  const current = active ?? blank!;
  return (
    <Workspace
      key={current.id}
      active={current}
      store={store}
      setStore={setStore}
      initialDraft=""
    />
  );
}

export default App;
