import { useEffect, useMemo, useRef, useState } from "react";

export interface GraphNode {
  id: string;
  title: string;
  difficulty: string;
}
export interface GraphEdge {
  from: string;
  to: string;
  relation_type: string;
}

const RELATION_COLORS: Record<string, string> = {
  前置依赖: "#3977bc",
  父子包含: "#278b82",
  推导关系: "#8964bd",
  相关关联: "#7088a6",
};
function relationColor(type: string) {
  return RELATION_COLORS[type] ?? "#7088a6";
}
function nodeTone(difficulty: string) {
  if (difficulty.includes("进阶"))
    return { color: "#8061ad", tint: "#f4effa", border: "#dacdec" };
  if (difficulty.includes("高") || difficulty.includes("难"))
    return { color: "#b47b32", tint: "#fbf4e8", border: "#ead8b9" };
  return { color: "#3977bc", tint: "#edf4fc", border: "#cbdff1" };
}

// Lay out each connected component separately, with its most connected point in the centre.
function layout(nodes: GraphNode[], edges: GraphEdge[]) {
  const links = new Map(nodes.map((n) => [n.id, new Set<string>()]));
  for (const e of edges) {
    links.get(e.from)?.add(e.to);
    links.get(e.to)?.add(e.from);
  }
  const pending = new Set(nodes.map((n) => n.id));
  const points = new Map<string, { x: number; y: number }>();
  let offset = 60;
  while (pending.size) {
    const first = pending.values().next().value!;
    const group = [first];
    pending.delete(first);
    for (let i = 0; i < group.length; i++) {
      for (const id of links.get(group[i]) ?? []) {
        if (pending.delete(id)) group.push(id);
      }
    }
    group.sort((a, b) => (links.get(b)?.size ?? 0) - (links.get(a)?.size ?? 0));
    const radius =
      group.length > 1 ? Math.max(170, (group.length - 1) * 36) : 0;
    const centre = { x: radius + 160, y: offset + radius + 40 };
    points.set(group[0], centre);
    group.slice(1).forEach((id, index) => {
      const angle = (index * Math.PI * 2) / (group.length - 1) - Math.PI / 2;
      points.set(id, {
        x: centre.x + radius * Math.cos(angle),
        y: centre.y + radius * Math.sin(angle),
      });
    });
    offset += 2 * radius + 140;
  }
  const positions = [...points.values()];
  const minX = Math.min(...positions.map((p) => p.x), 0);
  const minY = Math.min(...positions.map((p) => p.y), 0);
  const maxX = Math.max(...positions.map((p) => p.x), 0);
  const maxY = Math.max(...positions.map((p) => p.y), 0);
  const left = positions.length ? Math.min(...positions.map((p) => p.x)) : minX;
  const top = positions.length ? Math.min(...positions.map((p) => p.y)) : minY;
  for (const point of points.values()) {
    point.x -= left - 125;
    point.y -= top - 80;
  }
  return {
    points,
    width: Math.max(300, maxX - left + 250),
    height: Math.max(300, maxY - top + 160),
  };
}

export default function KnowledgeGraph({
  nodes,
  edges,
  onClose,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const validEdges = useMemo(() => {
    const ids = new Set(nodes.map((n) => n.id));
    return edges.filter((e) => ids.has(e.from) && ids.has(e.to));
  }, [nodes, edges]);
  const graph = useMemo(() => layout(nodes, validEdges), [nodes, validEdges]);
  const selected = nodes.find((n) => n.id === selectedId);
  const related = validEdges.filter(
    (e) => e.from === selectedId || e.to === selectedId,
  );
  const highlighted = new Set([
    selectedId,
    ...related.flatMap((e) => [e.from, e.to]),
  ]);
  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  function download() {
    if (!svgRef.current) return;
    const copy = svgRef.current.cloneNode(true) as SVGSVGElement;
    copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    copy.setAttribute("width", String(graph.width));
    copy.setAttribute("height", String(graph.height));
    copy.removeAttribute("style");
    const url = URL.createObjectURL(
      new Blob([new XMLSerializer().serializeToString(copy)], {
        type: "image/svg+xml;charset=utf-8",
      }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "知识图谱.svg";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <dialog
      ref={dialogRef}
      className="graph-dialog"
      aria-labelledby="graph-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="graph-header">
        <div className="graph-title-lockup">
          <span className="graph-title-icon" aria-hidden="true">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path
                d="M6 6L18 6L12 18Z"
                stroke="currentColor"
                strokeWidth="1.5"
              />
              <circle cx="6" cy="6" r="3" fill="currentColor" />
              <circle cx="18" cy="6" r="3" fill="currentColor" />
              <circle cx="12" cy="18" r="3" fill="currentColor" />
            </svg>
          </span>
          <div>
            <h2 id="graph-title">知识图谱</h2>
            <p>
              {nodes.length} 个知识点 · {validEdges.length} 条关联 · 仅当前会话
            </p>
          </div>
        </div>
        <button aria-label="关闭知识图谱" onClick={onClose}>
          ×
        </button>
      </div>
      <div className="graph-toolbar">
        <button
          aria-label="缩小图谱"
          disabled={zoom <= 1}
          onClick={() => setZoom((z) => Math.max(1, z - 0.5))}
        >
          −
        </button>
        <span>{Math.round(zoom * 100)}%</span>
        <button
          aria-label="放大图谱"
          disabled={zoom >= 4}
          onClick={() => setZoom((z) => Math.min(4, z + 0.5))}
        >
          ＋
        </button>
        <button
          onClick={() => {
            setZoom(1);
            setSelectedId(null);
          }}
        >
          重置视图
        </button>
        <button
          className="graph-download"
          onClick={download}
          disabled={!nodes.length}
        >
          下载图谱 SVG
        </button>
      </div>
      {validEdges.length > 0 && (
        <div className="graph-legend" aria-label="关系图例">
          <span>关系图例</span>
          {[...new Set(validEdges.map((e) => e.relation_type))].map((type) => (
            <span key={type}>
              <i style={{ background: relationColor(type) }} />
              {type}
            </span>
          ))}
        </div>
      )}
      <div className="graph-canvas">
        {nodes.length ? (
          <svg
            ref={svgRef}
            viewBox={`0 0 ${graph.width} ${graph.height}`}
            style={{ width: `${zoom * 100}%`, height: `${zoom * 100}%` }}
            role="img"
            aria-label="当前会话知识点关系图"
            fontFamily="Segoe UI, Microsoft YaHei, sans-serif"
          >
            <title>当前会话知识点关系图</title>
            <rect width={graph.width} height={graph.height} fill="#f8fafc" />
            <rect
              width={graph.width}
              height={graph.height}
              fill="url(#graph-dots)"
            />
            <defs>
              <pattern
                id="graph-dots"
                width="18"
                height="18"
                patternUnits="userSpaceOnUse"
              >
                <circle cx="1" cy="1" r=".7" fill="#dce5ef" />
              </pattern>
              <filter
                id="graph-shadow"
                x="-25%"
                y="-40%"
                width="150%"
                height="180%"
              >
                <feDropShadow
                  dx="0"
                  dy="4"
                  stdDeviation="5"
                  floodColor="#24456b"
                  floodOpacity=".09"
                />
              </filter>
              <linearGradient id="graph-selected" x1="0" y1="0" x2="1" y2="1">
                <stop stopColor="#254569" />
                <stop offset="1" stopColor="#3b6490" />
              </linearGradient>
              {[...new Set(validEdges.map((e) => e.relation_type))].map(
                (type, index) => (
                  <marker
                    key={type}
                    id={`graph-arrow-${index}`}
                    viewBox="0 0 10 10"
                    refX="9"
                    refY="5"
                    markerWidth="6"
                    markerHeight="6"
                    orient="auto-start-reverse"
                  >
                    <path
                      d="M 0 0 L 10 5 L 0 10 z"
                      fill={relationColor(type)}
                    />
                  </marker>
                ),
              )}
            </defs>
            {validEdges.map((e, i) => {
              const a = graph.points.get(e.from)!;
              const b = graph.points.get(e.to)!;
              const distance = Math.hypot(b.x - a.x, b.y - a.y) || 1;
              const dx = (b.x - a.x) / distance;
              const dy = (b.y - a.y) / distance;
              const padding = Math.min(
                98 / Math.max(Math.abs(dx), 0.01),
                42 / Math.max(Math.abs(dy), 0.01),
              );
              const bend = Math.min(32, distance * 0.12);
              const midX = (a.x + b.x) / 2 - dy * bend;
              const midY = (a.y + b.y) / 2 + dx * bend;
              const color = relationColor(e.relation_type);
              const markerIndex = [
                ...new Set(validEdges.map((edge) => edge.relation_type)),
              ].indexOf(e.relation_type);
              const focus =
                !selectedId || e.from === selectedId || e.to === selectedId;
              return (
                <g key={i} opacity={focus ? 1 : 0.18}>
                  <path
                    className="graph-edge"
                    d={`M ${a.x + dx * padding} ${a.y + dy * padding} Q ${midX} ${midY} ${b.x - dx * padding} ${b.y - dy * padding}`}
                    fill="none"
                    stroke={color}
                    strokeOpacity=".75"
                    strokeWidth="1.8"
                    markerEnd={`url(#graph-arrow-${markerIndex})`}
                  />
                  <rect
                    x={midX - (e.relation_type.length * 10 + 16) / 2}
                    y={midY - 17}
                    width={e.relation_type.length * 10 + 16}
                    height="22"
                    rx="11"
                    fill="#fff"
                    stroke="#e5ebf3"
                  />
                  <text
                    x={midX}
                    y={midY - 2}
                    textAnchor="middle"
                    fontSize="11"
                    fill={color}
                  >
                    {e.relation_type}
                  </text>
                </g>
              );
            })}
            {nodes.map((n) => {
              const point = graph.points.get(n.id)!;
              const tone = nodeTone(n.difficulty);
              const lines =
                n.title.length > 13
                  ? [
                      n.title.slice(0, 13),
                      n.title.length > 26
                        ? n.title.slice(13, 25) + "…"
                        : n.title.slice(13),
                    ]
                  : [n.title];
              const active = selectedId === n.id;
              return (
                <g
                  key={n.id}
                  className="graph-node"
                  transform={`translate(${point.x},${point.y})`}
                  role="button"
                  tabIndex={0}
                  aria-label={`查看知识点 ${n.title}`}
                  onClick={() => setSelectedId(n.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedId(n.id);
                    }
                  }}
                  opacity={!selectedId || highlighted.has(n.id) ? 1 : 0.35}
                >
                  <title>
                    {n.title}
                    {n.difficulty ? ` · ${n.difficulty}` : ""}
                  </title>
                  <rect
                    x="-98"
                    y="-42"
                    width="196"
                    height="84"
                    rx="16"
                    fill={active ? "url(#graph-selected)" : "#fff"}
                    stroke={active ? "#254569" : tone.border}
                    strokeWidth="1.2"
                    filter="url(#graph-shadow)"
                  />
                  <rect
                    x="-87"
                    y="-31"
                    width="4"
                    height="62"
                    rx="2"
                    fill={active ? "#a4c8ed" : tone.color}
                  />
                  <text
                    textAnchor="middle"
                    y={lines.length > 1 ? -13 : -5}
                    fontSize="13"
                    fontWeight="600"
                    fill={active ? "#fff" : "#29405b"}
                  >
                    {lines.map((line, i) => (
                      <tspan x="0" dy={i ? 17 : 0} key={i}>
                        {line}
                      </tspan>
                    ))}
                  </text>
                  {n.difficulty && (
                    <>
                      <rect
                        x={-Math.max(22, n.difficulty.length * 5 + 9)}
                        y="13"
                        width={Math.max(44, n.difficulty.length * 10 + 18)}
                        height="19"
                        rx="9.5"
                        fill={active ? "#ffffff20" : tone.tint}
                      />
                      <text
                        textAnchor="middle"
                        y="26"
                        fontSize="10"
                        fill={active ? "#e1efff" : tone.color}
                      >
                        {n.difficulty}
                      </text>
                    </>
                  )}
                </g>
              );
            })}
          </svg>
        ) : (
          <p className="placeholder">
            暂无知识点，请先上传资料并等待解析完成。
          </p>
        )}
      </div>
      <div className="graph-detail" aria-live="polite">
        {selected ? (
          <>
            <strong>{selected.title}</strong>
            {selected.difficulty && <span> · {selected.difficulty}</span>}
            {related.length ? (
              <ul>
                {related.map((e, i) => (
                  <li key={i}>
                    {nodes.find((n) => n.id === e.from)?.title} →{" "}
                    {e.relation_type} →{" "}
                    {nodes.find((n) => n.id === e.to)?.title}
                  </li>
                ))}
              </ul>
            ) : (
              <p>该知识点暂未提取到关联。</p>
            )}
          </>
        ) : (
          <p>
            {validEdges.length
              ? "点击知识点查看完整名称和关联；放大后可滚动查看。"
              : "尚未提取到知识点之间的关联，当前仅展示知识点。"}
          </p>
        )}
      </div>
    </dialog>
  );
}
