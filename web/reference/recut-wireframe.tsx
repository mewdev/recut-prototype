import { useState, useRef, useEffect, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Play,
  Pause,
  ZoomIn,
  ZoomOut,
  AudioLines,
  Code2,
  FileAudio,
  AlertTriangle,
  Info,
  MoreVertical,
  ChevronRight,
  CircleCheck,
  X,
  Lock,
  Copy,
  Check,
  Sparkles,
  Send,
  Wrench,
  Bot,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Waveform data: deterministic seeded generator, not Math.random(), so the
// same "song" renders identically every time. Real audio would replace this
// with actual sample peaks; the render path (canvas, mirrored bars, playhead,
// drag) is otherwise unchanged.
// ---------------------------------------------------------------------------

function mulberry32(seed) {
  let a = seed;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function generateWaveform(seed, numPoints, envFreq1, envFreq2) {
  const rand = mulberry32(seed);
  const points = [];
  for (let i = 0; i < numPoints; i++) {
    const env =
      0.35 +
      0.25 * Math.sin(i * envFreq1 * Math.PI * 2 + seed) +
      0.15 * Math.sin(i * envFreq2 * Math.PI * 2 + seed * 1.7);
    const noise = rand();
    const spike = Math.pow(rand(), 3);
    let v = Math.max(0.04, env * 0.55 + noise * 0.35 + spike * 0.3);
    points.push(Math.min(1, v));
  }
  return points.map((v, i, arr) => {
    const a = arr[Math.max(0, i - 1)];
    const b = arr[Math.min(arr.length - 1, i + 1)];
    return (a + v + v + b) / 4;
  });
}

function sliceByTime(data, duration, startSec, endSec) {
  const i0 = Math.max(0, Math.round((startSec / duration) * data.length));
  const i1 = Math.min(data.length, Math.round((endSec / duration) * data.length));
  return data.slice(i0, i1);
}

function formatTime(sec) {
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

function parseTimeToSeconds(str) {
  const trimmed = str.trim();
  if (/^\d+:\d{1,2}$/.test(trimmed)) {
    const [m, s] = trimmed.split(":").map(Number);
    return m * 60 + s;
  }
  if (/^\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed);
  return null;
}

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

// ---------------------------------------------------------------------------
// Source data
// ---------------------------------------------------------------------------

const AUDIO1_DURATION = 159;
const AUDIO2_DURATION = 184;

const AUDIO1_WAVEFORM = generateWaveform(11, AUDIO1_DURATION * 4, 0.01, 0.05);
const AUDIO2_WAVEFORM = generateWaveform(37, AUDIO2_DURATION * 4, 0.012, 0.04);

const SOURCE_DATA = { audio1: AUDIO1_WAVEFORM, audio2: AUDIO2_WAVEFORM };
const SOURCE_HEX = { audio1: "#38bdf8", audio2: "#fbbf24" };
const SOURCE_COLOR = {
  audio1: { dot: "bg-sky-500", text: "text-sky-700", chip: "bg-sky-50 text-sky-700 border-sky-200" },
  audio2: { dot: "bg-amber-500", text: "text-amber-700", chip: "bg-amber-50 text-amber-700 border-amber-200" },
};

const SOURCES = [
  { id: "audio1", name: "audio1.mp3", duration: AUDIO1_DURATION },
  { id: "audio2", name: "audio2.mp3", duration: AUDIO2_DURATION },
];

const SOURCE_SECTION_NAMES = {
  audio1: ["Intro", "Verse", "Chorus", "Bridge", "Outro"],
  audio2: ["Intro", "Verse", "Chorus", "Outro"],
};

const INITIAL_BOUNDARIES = {
  audio1: [8, 45, 90, 120],
  audio2: [10, 62, 140],
};

function sectionsFromBoundaries(source, boundaries) {
  const names = SOURCE_SECTION_NAMES[source];
  const dur = SOURCES.find((s) => s.id === source).duration;
  const bounds = [0, ...boundaries[source], dur];
  return names.map((label, i) => ({ label, start: bounds[i], end: bounds[i + 1] }));
}

// Composition edit plan (now stateful — this is the thing the Inspector edits
// and the Code tab renders, read-only, from).
const INITIAL_PLAN = [
  { id: "s1", label: "Intro", source: "audio1", srcStart: 0, srcEnd: 8, warning: null },
  {
    id: "s2",
    label: "Chorus",
    source: "audio2",
    srcStart: 62,
    srcEnd: 74,
    crossfadeCurve: "linear",
    crossfadeMs: 40,
    warning: {
      severity: "warn",
      rule: "adjacency",
      message: "feature-distance 0.71 — high severity cross-source splice",
      suggestedFix: { curve: "qsin", ms: 180 },
    },
  },
  {
    id: "s3",
    label: "Outro",
    source: "audio1",
    srcStart: 130,
    srcEnd: 138,
    crossfadeCurve: "qsin",
    crossfadeMs: 60,
    warning: { severity: "info", rule: "boundary", message: "cut not exactly on beat grid" },
  },
];

const CURVE_LABEL = { qsin: "equal-power (qsin)", linear: "linear", hsin: "hsin" };

function computeSegments(plan) {
  let cursor = 0;
  return plan.map((seg) => {
    const dur = seg.srcEnd - seg.srcStart;
    const bars = sliceByTime(
      SOURCE_DATA[seg.source],
      SOURCES.find((s) => s.id === seg.source).duration,
      seg.srcStart,
      seg.srcEnd
    );
    const out = { ...seg, compStart: cursor, compEnd: cursor + dur, bars };
    cursor += dur;
    return out;
  });
}

function editPlanCode(segments) {
  const hasCrossfade = segments.some((s, i) => i > 0 && s.crossfadeMs != null);
  const lines = segments.map((s, i) => {
    const parts = [`source: "${s.source}"`, `in: "${formatTime(s.srcStart)}"`, `out: "${formatTime(s.srcEnd)}"`];
    if (i > 0 && s.crossfadeMs != null) parts.push(`crossfadeMs: ${s.crossfadeMs}`);
    return `    Clip({ ${parts.join(", ")} }),   // ${s.label}`;
  });
  let code = `compose({\n  name: "billie_jean_recut",\n  clips: [\n${lines.join("\n")}\n  ],\n})`;
  if (hasCrossfade) {
    code += `\n\n// NOTE: crossfade_ms above requires xfade wiring into compose()\n// — currently a known gap, see ARCHITECTURE_CHECKLIST.md`;
  }
  return code;
}

const ZOOM_LEVELS = [0.5, 0.75, 1, 1.5, 2, 3];

// ---------------------------------------------------------------------------
// Waveform canvas — mirrored-bar rendering, explicit pixel width (no DOM
// measurement, so it's reliable at any zoom level).
// ---------------------------------------------------------------------------

function WaveformCanvas({ data, color, height = 64, widthPx }) {
  const ref = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !widthPx || widthPx < 1) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = widthPx * dpr;
    canvas.height = height * dpr;
    canvas.style.width = widthPx + "px";
    canvas.style.height = height + "px";
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, widthPx, height);
    const mid = height / 2;
    const n = data.length;
    const slot = widthPx / n;
    const barW = Math.max(1, slot * 0.7);
    ctx.fillStyle = color;
    for (let i = 0; i < n; i++) {
      const amp = data[i] * (height * 0.42);
      const x = i * slot;
      ctx.fillRect(x, mid - amp, barW, amp * 2);
    }
    ctx.globalAlpha = 0.3;
    ctx.strokeStyle = color;
    ctx.beginPath();
    ctx.moveTo(0, mid);
    ctx.lineTo(widthPx, mid);
    ctx.stroke();
    ctx.globalAlpha = 1;
  }, [data, color, height, widthPx]);
  return <canvas ref={ref} className="block" />;
}

function SeverityIcon({ severity }) {
  if (severity === "warn") return <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />;
  if (severity === "error") return <AlertTriangle className="h-3.5 w-3.5 text-red-600" />;
  return <Info className="h-3.5 w-3.5 text-slate-400" />;
}

// ---------------------------------------------------------------------------
// Fade / crossfade overlays — drawn on top of the composition waveform so
// gain ramps are visible the way they are in any DAW (a light scrim for a
// plain fade, two crossing curves for a splice between two clips). Purely
// visual: it does NOT shorten the timeline the way a real xfade render would
// (that's the same "xfade not wired into compose() yet" gap noted in the
// generated code — this overlay shows where it'll apply once it is).
// ---------------------------------------------------------------------------

function FadeOverlay({ side, leftPx, widthPx, topPx, heightPx }) {
  const w = widthPx,
    h = heightPx;
  if (w < 2) return null;
  // 'in': shadow wedge is heaviest at the start, tapering to nothing by the
  // box's far edge — diagonal runs from top-right down to bottom-left.
  // 'out': mirrored — shadow builds toward the end.
  const trianglePath = side === "in" ? `M0,0 L${w},0 L0,${h} Z` : `M0,0 L${w},0 L${w},${h} Z`;
  const lineD = side === "in" ? `M${w},0 L0,${h}` : `M0,0 L${w},${h}`;
  return (
    <svg className="absolute pointer-events-none" style={{ left: leftPx, top: topPx, width: w, height: h }}>
      <path d={trianglePath} fill="rgb(15,23,42)" fillOpacity={0.13} />
      <path d={lineD} stroke="rgba(15,23,42,0.45)" strokeWidth="1.5" fill="none" />
    </svg>
  );
}

function CrossfadeBowtie({ leftPx, widthPx, topPx, heightPx, prevColor, currColor }) {
  const w = widthPx,
    h = heightPx,
    mid = w / 2;
  if (w < 2) return null;
  return (
    <svg className="absolute pointer-events-none" style={{ left: leftPx, top: topPx, width: w, height: h }}>
      {/* shaded top + bottom wedges — the classic crossfade "hourglass";
          the clear band left/right is where both clips are audibly blending */}
      <path d={`M0,0 L${mid},${h / 2} L${w},0 Z`} fill="rgb(15,23,42)" fillOpacity={0.13} />
      <path d={`M0,${h} L${mid},${h / 2} L${w},${h} Z`} fill="rgb(15,23,42)" fillOpacity={0.13} />
      {/* outgoing (prev) envelope */}
      <path d={`M0,0 L${w},${h}`} stroke={prevColor} strokeWidth="1.5" opacity={0.8} />
      {/* incoming (curr) envelope */}
      <path d={`M0,${h} L${w},0`} stroke={currColor} strokeWidth="1.5" opacity={0.8} />
    </svg>
  );
}

const FADE_EDGE_MS = 500; // short edge fade — demo constant, not yet an editable field
const MIN_XFADE_PX = 10; // floor so a very short crossfade_ms is still visible

// small controlled text field for mm:ss / seconds entry, with draft state so
// typing doesn't fight the committed value until blur/Enter
function TimeField({ value, onCommit, className }) {
  const [draft, setDraft] = useState(formatTime(value));
  useEffect(() => setDraft(formatTime(value)), [value]);
  function commit() {
    const parsed = parseTimeToSeconds(draft);
    if (parsed != null) onCommit(parsed);
    else setDraft(formatTime(value));
  }
  return (
    <input
      type="text"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          commit();
          e.currentTarget.blur();
        }
      }}
      className={className}
    />
  );
}

// ---------------------------------------------------------------------------
// Assistant panel — mock conversation. Tool calls operate on the same
// update_segment/run_validator concepts the Inspector and Problems panel
// already use, since a real agent-skill layer would act on the same plan
// state, not a separate one.
// ---------------------------------------------------------------------------

const INITIAL_CHAT = [
  { type: "user", text: "the audio1→audio2 splice at the chorus feels rough, can you fix it?" },
  { type: "tool", name: "read_segment", args: 'id: "s2"', result: "Chorus · audio2 1:02–1:14 · linear crossfade, 40ms" },
  { type: "tool", name: "run_validator", args: 'scope: "s2"', result: "1 warning — adjacency, feature-distance 0.71" },
  {
    type: "tool",
    name: "update_segment",
    args: 'id: "s2", crossfadeCurve: "qsin", crossfadeMs: 180',
    result: "updated",
  },
  {
    type: "assistant",
    text:
      "Switched the Chorus splice to an equal-power crossfade at 180ms — should smooth the transition. Feature-distance is still 0.71 since that's structural (different song), not something a crossfade alone fixes; want me to look for a closer-matching in-point in audio2 instead?",
  },
];

function ChatTurn({ turn }) {
  if (turn.type === "user") {
    return (
      <div className="flex justify-end">
        <div className="bg-muted rounded-md px-2.5 py-1.5 text-xs" style={{ maxWidth: "75%" }}>
          {turn.text}
        </div>
      </div>
    );
  }
  if (turn.type === "tool") {
    return (
      <div className="flex items-start gap-2">
        <Wrench className="h-3 w-3 text-muted-foreground mt-1 shrink-0" />
        <div className="font-mono text-xs border border-border rounded-md px-2 py-1.5 bg-muted/30" style={{ maxWidth: "85%" }}>
          <div className="text-foreground">
            <span className="font-medium">{turn.name}</span>
            <span className="text-muted-foreground">({turn.args})</span>
          </div>
          <div className="text-muted-foreground pl-3 mt-0.5">⎿ {turn.result}</div>
        </div>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-2">
      <Bot className="h-3.5 w-3.5 text-muted-foreground mt-0.5 shrink-0" />
      <div className="text-xs leading-relaxed" style={{ maxWidth: "85%" }}>
        {turn.text}
      </div>
    </div>
  );
}

export default function RecutWireframe() {
  const [plan, setPlan] = useState(INITIAL_PLAN);
  const [openTabs, setOpenTabs] = useState([]);
  const [activeTab, setActiveTab] = useState("composition");
  const [view, setView] = useState("waveform");
  const [selectedSegmentId, setSelectedSegmentId] = useState("s2");
  const [hoveredSegmentId, setHoveredSegmentId] = useState(null);
  const [sourceMenuOpenId, setSourceMenuOpenId] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [zoomIndex, setZoomIndex] = useState(2);
  const [boundaries, setBoundaries] = useState(INITIAL_BOUNDARIES);
  const [dragging, setDragging] = useState(null);
  const [copied, setCopied] = useState(false);
  const [bottomTab, setBottomTab] = useState("problems");
  const [messages, setMessages] = useState(INITIAL_CHAT);
  const [chatInput, setChatInput] = useState("");
  const [thinking, setThinking] = useState(false);

  const sourceInnerRef = useRef(null);
  const chatEndRef = useRef(null);
  const zoom = ZOOM_LEVELS[zoomIndex];

  const segments = useMemo(() => computeSegments(plan), [plan]);
  const compositionDuration = segments.length ? segments[segments.length - 1].compEnd : 0;
  const durations = { composition: compositionDuration, audio1: AUDIO1_DURATION, audio2: AUDIO2_DURATION };

  const selectedIndex = segments.findIndex((s) => s.id === selectedSegmentId);
  const selectedSegment = selectedIndex >= 0 ? segments[selectedIndex] : null;
  const problems = segments.filter((s) => s.warning);
  const worstSeverity = problems.some((p) => p.warning.severity === "error")
    ? "error"
    : problems.some((p) => p.warning.severity === "warn")
    ? "warn"
    : "ok";

  const duration = durations[activeTab];
  const pxPerSec = (activeTab === "composition" ? 20 : 6) * zoom;

  useEffect(() => {
    setPlaying(false);
    setCurrentTime(0);
  }, [activeTab]);

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      setCurrentTime((t) => {
        const next = t + 0.12;
        if (next >= duration) {
          setPlaying(false);
          return duration;
        }
        return next;
      });
    }, 100);
    return () => clearInterval(id);
  }, [playing, duration]);

  useEffect(() => {
    if (!dragging) return;
    function onMove(e) {
      const rect = sourceInnerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const x = e.clientX - rect.left;
      let t = x / pxPerSec;
      const { source, index } = dragging;
      const bounds = boundaries[source];
      const dur = durations[source];
      const prevBound = index === 0 ? 1 : bounds[index - 1] + 1;
      const nextBound = index === bounds.length - 1 ? dur - 1 : bounds[index + 1] - 1;
      t = clamp(t, prevBound, nextBound);
      setBoundaries((b) => ({ ...b, [source]: b[source].map((v, i) => (i === index ? t : v)) }));
    }
    function onUp() {
      setDragging(null);
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [dragging, pxPerSec, boundaries, durations]);

  function updateSegment(id, patch) {
    setPlan((prev) => prev.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  }

  function handleSourceChange(seg, newSource) {
    const len = seg.srcEnd - seg.srcStart;
    const newDur = SOURCES.find((s) => s.id === newSource).duration;
    updateSegment(seg.id, { source: newSource, srcStart: 0, srcEnd: Math.min(len, newDur) });
  }

  function handleInCommit(seg, val) {
    updateSegment(seg.id, { srcStart: clamp(val, 0, seg.srcEnd - 1) });
  }

  function handleOutCommit(seg, val) {
    const dur = SOURCES.find((s) => s.id === seg.source).duration;
    updateSegment(seg.id, { srcEnd: clamp(val, seg.srcStart + 1, dur) });
  }

  function applySuggestedFix(seg) {
    const fix = seg.warning?.suggestedFix;
    if (!fix) return;
    updateSegment(seg.id, { crossfadeCurve: fix.curve, crossfadeMs: fix.ms });
  }

  useEffect(() => {
    if (bottomTab === "assistant") chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking, bottomTab]);

  function handleSend() {
    const text = chatInput.trim();
    if (!text) return;
    setMessages((m) => [...m, { type: "user", text }]);
    setChatInput("");
    setThinking(true);
    setTimeout(() => {
      setThinking(false);
      setMessages((m) => [...m, { type: "assistant", text: "Got it — I'll take a look and let you know what I find." }]);
    }, 900);
  }

  function handleCopyCode() {
    try {
      navigator.clipboard.writeText(editPlanCode(segments));
    } catch (e) {}
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  }

  function openSource(id) {
    if (!openTabs.includes(id)) setOpenTabs([...openTabs, id]);
    setActiveTab(id);
    setSourceMenuOpenId(null);
  }

  function closeTab(id, e) {
    e.stopPropagation();
    setOpenTabs(openTabs.filter((t) => t !== id));
    if (activeTab === id) setActiveTab("composition");
  }

  function selectSegmentFromProblem(seg) {
    setActiveTab("composition");
    setView("waveform");
    setSelectedSegmentId(seg.id);
    setCurrentTime(seg.compStart);
  }

  function seekComposition(e) {
    const x = e.nativeEvent.offsetX;
    const t = clamp(x / pxPerSec, 0, compositionDuration);
    setCurrentTime(t);
    const seg = segments.find((s) => t >= s.compStart && t <= s.compEnd);
    if (seg) setSelectedSegmentId(seg.id);
  }

  function seekSource(e) {
    const x = e.nativeEvent.offsetX;
    setCurrentTime(clamp(x / pxPerSec, 0, duration));
  }

  const compTotalWidth = compositionDuration * pxPerSec;
  const srcTotalWidth = activeTab !== "composition" ? durations[activeTab] * pxPerSec : 0;
  const sections = activeTab !== "composition" ? sectionsFromBoundaries(activeTab, boundaries) : [];

  const fieldClass =
    "w-full h-7 text-xs border border-border rounded-md px-2 bg-background tabular-nums focus:outline-none focus:ring-1 focus:ring-foreground/30";

  return (
    <div
      className="flex flex-col w-full border border-border rounded-lg overflow-hidden bg-background text-sm select-none"
      style={{ height: 844 }}
    >
      {/* ---------------- TOP BAR ---------------- */}
      <div className="flex items-center justify-between px-3 h-9 border-b border-border bg-muted/40 shrink-0">
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Recut</span>
          {["File", "Edit", "View", "Validator"].map((m) => (
            <span key={m} className="hover:text-foreground cursor-default">
              {m}
            </span>
          ))}
        </div>
        <Button size="sm" className="h-6 text-xs px-3">
          Render
        </Button>
      </div>

      {/* ---------------- CONTROL BAR ---------------- */}
      <div className="flex items-center justify-between px-3 h-11 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <Button
            size="icon"
            variant="secondary"
            className="h-7 w-7"
            onClick={() => setPlaying((p) => (currentTime >= duration ? (setCurrentTime(0), true) : !p))}
          >
            {playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
          </Button>
          <span className="text-xs tabular-nums text-muted-foreground w-20">
            {formatTime(currentTime)} / {formatTime(duration)}
          </span>
          <Separator orientation="vertical" className="h-5 mx-1" />
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            disabled={zoomIndex === 0}
            onClick={() => setZoomIndex((i) => Math.max(0, i - 1))}
          >
            <ZoomOut className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            disabled={zoomIndex === ZOOM_LEVELS.length - 1}
            onClick={() => setZoomIndex((i) => Math.min(ZOOM_LEVELS.length - 1, i + 1))}
          >
            <ZoomIn className="h-3.5 w-3.5" />
          </Button>
          <span className="text-xs text-muted-foreground w-8">{zoom}x</span>
        </div>

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">billie_jean_recut</span>
          <Badge variant="outline" className="text-xs font-normal">
            116 BPM · F#m
          </Badge>
        </div>

        <div className="flex items-center gap-1.5">
          {worstSeverity === "ok" ? (
            <CircleCheck className="h-3.5 w-3.5 text-emerald-600" />
          ) : (
            <AlertTriangle className={`h-3.5 w-3.5 ${worstSeverity === "error" ? "text-red-600" : "text-amber-600"}`} />
          )}
          <span className="text-xs text-muted-foreground">
            {problems.length} validator {problems.length === 1 ? "hit" : "hits"}
          </span>
        </div>
      </div>

      {/* ---------------- BODY ---------------- */}
      <div className="flex flex-1 min-h-0">
        {/* LEFT PANEL */}
        <div className="w-52 border-r border-border flex flex-col shrink-0">
          <div className="px-3 py-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">Sources</div>
          <div className="px-2 space-y-0.5">
            {SOURCES.map((src) => (
              <div
                key={src.id}
                className="group flex items-center justify-between px-2 py-1.5 rounded-md hover:bg-muted cursor-pointer"
                onClick={() => openSource(src.id)}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`h-2 w-2 rounded-full ${SOURCE_COLOR[src.id].dot} shrink-0`} />
                  <FileAudio className="h-3 w-3 text-muted-foreground shrink-0" />
                  <span className="truncate text-xs">{src.name}</span>
                </div>
                <div className="relative">
                  <button
                    className="opacity-0 group-hover:opacity-100 p-0.5"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSourceMenuOpenId(sourceMenuOpenId === src.id ? null : src.id);
                    }}
                  >
                    <MoreVertical className="h-3 w-3 text-muted-foreground" />
                  </button>
                  {sourceMenuOpenId === src.id && (
                    <div className="absolute right-0 top-5 z-10 w-40 bg-popover border border-border rounded-md shadow-md py-1">
                      <button
                        className="w-full text-left px-2 py-1 text-xs hover:bg-muted"
                        onClick={(e) => {
                          e.stopPropagation();
                          openSource(src.id);
                        }}
                      >
                        Open in new window
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          <Separator className="my-2" />

          <div className="px-3 py-1 text-xs font-medium text-muted-foreground uppercase tracking-wide">Structure</div>
          <div className="flex-1 overflow-y-auto px-2">
            {activeTab === "composition" ? (
              <div className="space-y-0.5 pb-2">
                {segments.map((seg) => (
                  <div
                    key={seg.id}
                    onClick={() => {
                      setView("waveform");
                      setSelectedSegmentId(seg.id);
                      setCurrentTime(seg.compStart);
                    }}
                    className={`flex items-center gap-1.5 px-2 py-1 rounded-md cursor-pointer text-xs ${
                      selectedSegmentId === seg.id ? "bg-muted" : "hover:bg-muted/60"
                    }`}
                  >
                    <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
                    <span className="truncate">{seg.label}</span>
                    <span className="ml-auto text-xs text-muted-foreground tabular-nums">{formatTime(seg.compStart)}</span>
                    <span className={`h-1.5 w-1.5 rounded-full ${SOURCE_COLOR[seg.source].dot} shrink-0`} />
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-0.5 pb-2">
                {sections.map((sec) => {
                  const active = currentTime >= sec.start && currentTime < sec.end;
                  return (
                    <div
                      key={sec.label}
                      onClick={() => setCurrentTime(sec.start)}
                      className={`flex items-center gap-1.5 px-2 py-1 rounded-md cursor-pointer text-xs ${
                        active ? "bg-muted" : "hover:bg-muted/60"
                      }`}
                    >
                      <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
                      <span className="truncate">{sec.label}</span>
                      <span className="ml-auto text-xs text-muted-foreground tabular-nums">{formatTime(sec.start)}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* MAIN AREA */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex items-center gap-1 px-2 h-9 border-b border-border shrink-0">
            <button
              onClick={() => setActiveTab("composition")}
              className={`px-2.5 h-6 rounded-md text-xs flex items-center gap-1.5 ${
                activeTab === "composition" ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60"
              }`}
            >
              Composition
            </button>
            {openTabs.map((id) => (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={`pl-2.5 pr-1.5 h-6 rounded-md text-xs flex items-center gap-1.5 ${
                  activeTab === id ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${SOURCE_COLOR[id].dot}`} />
                {SOURCES.find((s) => s.id === id)?.name}
                <span onClick={(e) => closeTab(id, e)} className="ml-1 p-0.5 rounded hover:bg-background/80">
                  <X className="h-3 w-3" />
                </span>
              </button>
            ))}

            {activeTab === "composition" && (
              <div className="ml-auto flex items-center bg-muted rounded-md p-0.5">
                <button
                  onClick={() => setView("waveform")}
                  className={`px-2 h-6 rounded text-xs flex items-center gap-1 ${
                    view === "waveform" ? "bg-background shadow-sm" : "text-muted-foreground"
                  }`}
                >
                  <AudioLines className="h-3 w-3" /> Waveform
                </button>
                <button
                  onClick={() => setView("code")}
                  className={`px-2 h-6 rounded text-xs flex items-center gap-1 ${
                    view === "code" ? "bg-background shadow-sm" : "text-muted-foreground"
                  }`}
                >
                  <Code2 className="h-3 w-3" /> Code
                </button>
              </div>
            )}
          </div>

          <div className="flex-1 overflow-auto p-4">
            {activeTab === "composition" && view === "waveform" && (
              <div className="overflow-x-auto pb-2">
                <div
                  className="relative border border-border rounded-md overflow-hidden flex"
                  style={{ width: compTotalWidth }}
                  onClick={seekComposition}
                >
                  {segments.map((seg) => (
                    <div
                      key={seg.id}
                      onMouseEnter={() => setHoveredSegmentId(seg.id)}
                      onMouseLeave={() => setHoveredSegmentId(null)}
                      className={`relative px-2 py-2 cursor-pointer border-r last:border-r-0 border-border ${
                        selectedSegmentId === seg.id
                          ? "bg-muted/60 ring-1 ring-inset ring-border"
                          : hoveredSegmentId === seg.id
                          ? "bg-muted/30"
                          : ""
                      }`}
                      style={{ width: (seg.compEnd - seg.compStart) * pxPerSec }}
                    >
                      <div className="flex items-center gap-1 mb-1 h-4">
                        {seg.warning && <SeverityIcon severity={seg.warning.severity} />}
                        <span className="text-xs text-muted-foreground truncate">
                          {seg.label} · {formatTime(seg.compStart)}–{formatTime(seg.compEnd)}
                        </span>
                      </div>
                      <WaveformCanvas
                        data={seg.bars}
                        color={SOURCE_HEX[seg.source]}
                        widthPx={(seg.compEnd - seg.compStart) * pxPerSec - 16}
                      />
                    </div>
                  ))}

                  {/* fade-in shadow — short, anchored to the very start */}
                  {segments.length > 0 &&
                    (() => {
                      const first = segments[0];
                      const w = clamp(
                        (FADE_EDGE_MS / 1000) * pxPerSec,
                        0,
                        (first.compEnd - first.compStart) * pxPerSec * 0.4
                      );
                      return <FadeOverlay side="in" leftPx={first.compStart * pxPerSec} widthPx={w} topPx={28} heightPx={64} />;
                    })()}

                  {/* crossfade hourglass at every splice — short, centered on the seam */}
                  {segments.map((seg, i) => {
                    if (i === 0) return null;
                    const prev = segments[i - 1];
                    const maxW =
                      Math.min((prev.compEnd - prev.compStart) * pxPerSec, (seg.compEnd - seg.compStart) * pxPerSec) * 0.4;
                    const w = clamp(((seg.crossfadeMs || 0) / 1000) * pxPerSec, MIN_XFADE_PX, maxW);
                    const boundaryX = seg.compStart * pxPerSec;
                    return (
                      <CrossfadeBowtie
                        key={seg.id}
                        leftPx={boundaryX - w / 2}
                        widthPx={w}
                        topPx={28}
                        heightPx={64}
                        prevColor={SOURCE_HEX[prev.source]}
                        currColor={SOURCE_HEX[seg.source]}
                      />
                    );
                  })}

                  {/* fade-out shadow — short, anchored to the very end */}
                  {segments.length > 0 &&
                    (() => {
                      const last = segments[segments.length - 1];
                      const w = clamp(
                        (FADE_EDGE_MS / 1000) * pxPerSec,
                        0,
                        (last.compEnd - last.compStart) * pxPerSec * 0.4
                      );
                      return (
                        <FadeOverlay side="out" leftPx={last.compEnd * pxPerSec - w} widthPx={w} topPx={28} heightPx={64} />
                      );
                    })()}

                  <div
                    className="absolute top-0 bottom-0 w-px bg-foreground/70 pointer-events-none"
                    style={{ left: currentTime * pxPerSec }}
                  />
                </div>
              </div>
            )}

            {activeTab === "composition" && view === "code" && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <Lock className="h-3 w-3" /> read-only — edit via Inspector, this reflects the plan
                  </span>
                  <button
                    onClick={handleCopyCode}
                    className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                  >
                    {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                    {copied ? "Copied" : "Copy"}
                  </button>
                </div>
                <pre className="text-xs bg-muted/40 border border-border rounded-md p-4 overflow-auto font-mono leading-relaxed">
                  {editPlanCode(segments)}
                </pre>
              </div>
            )}

            {activeTab !== "composition" && (
              <div className="overflow-x-auto pb-2">
                <div className="text-xs text-muted-foreground mb-2">
                  {SOURCES.find((s) => s.id === activeTab)?.name} — full source, drag boundaries to adjust
                </div>
                <div ref={sourceInnerRef} className="relative border border-border rounded-md" style={{ width: srcTotalWidth }}>
                  <div className="relative h-5 border-b border-border">
                    {sections.map((sec) => (
                      <div
                        key={sec.label}
                        className="absolute top-0 h-full flex items-center justify-center text-xs text-muted-foreground border-r border-border/60 last:border-r-0"
                        style={{ left: sec.start * pxPerSec, width: (sec.end - sec.start) * pxPerSec }}
                      >
                        {sec.label}
                      </div>
                    ))}
                  </div>

                  <div className="relative cursor-pointer" onClick={seekSource}>
                    <WaveformCanvas data={SOURCE_DATA[activeTab]} color={SOURCE_HEX[activeTab]} widthPx={srcTotalWidth} />
                    <div
                      className="absolute top-0 bottom-0 w-px bg-foreground/70 pointer-events-none"
                      style={{ left: currentTime * pxPerSec }}
                    />
                  </div>

                  {boundaries[activeTab].map((t, i) => (
                    <div
                      key={i}
                      onMouseDown={(e) => {
                        e.stopPropagation();
                        setDragging({ source: activeTab, index: i });
                      }}
                      className="absolute top-0 bottom-0 w-2 -ml-1 cursor-col-resize group"
                      style={{ left: t * pxPerSec }}
                    >
                      <div className="w-px h-full bg-border mx-auto group-hover:bg-foreground/60 group-active:bg-foreground" />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* RIGHT PANEL — Inspector (now a props panel, not just diagnostics) */}
        <div className="w-72 border-l border-border p-3 shrink-0 overflow-y-auto">
          <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Inspector</div>

          {selectedSegment ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <span className={`h-2.5 w-2.5 rounded-full ${SOURCE_COLOR[selectedSegment.source].dot}`} />
                <span className="font-medium text-sm">{selectedSegment.label}</span>
                <span className="ml-auto text-xs text-muted-foreground tabular-nums">
                  {formatTime(selectedSegment.compStart)}–{formatTime(selectedSegment.compEnd)}
                </span>
              </div>

              {/* --- editable props --- */}
              <div className="space-y-1">
                <div className="text-xs font-medium text-muted-foreground">Source</div>
                <select
                  value={selectedSegment.source}
                  onChange={(e) => handleSourceChange(selectedSegment, e.target.value)}
                  className={fieldClass}
                >
                  {SOURCES.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <div className="text-xs font-medium text-muted-foreground">In</div>
                  <TimeField
                    value={selectedSegment.srcStart}
                    onCommit={(v) => handleInCommit(selectedSegment, v)}
                    className={fieldClass}
                  />
                </div>
                <div className="space-y-1">
                  <div className="text-xs font-medium text-muted-foreground">Out</div>
                  <TimeField
                    value={selectedSegment.srcEnd}
                    onCommit={(v) => handleOutCommit(selectedSegment, v)}
                    className={fieldClass}
                  />
                </div>
              </div>

              {selectedIndex > 0 && (
                <div className="space-y-2 rounded-md border border-border p-2">
                  <div className="text-xs font-medium text-muted-foreground">Crossfade in</div>
                  <select
                    value={selectedSegment.crossfadeCurve}
                    onChange={(e) => updateSegment(selectedSegment.id, { crossfadeCurve: e.target.value })}
                    className={fieldClass}
                  >
                    {Object.entries(CURVE_LABEL).map(([v, label]) => (
                      <option key={v} value={v}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground w-16 shrink-0">crossfade_ms</span>
                    <input
                      type="range"
                      min={0}
                      max={500}
                      value={selectedSegment.crossfadeMs}
                      onChange={(e) => updateSegment(selectedSegment.id, { crossfadeMs: Number(e.target.value) })}
                      className="w-full h-1 accent-foreground"
                    />
                    <span className="text-xs tabular-nums text-muted-foreground w-9 text-right">
                      {selectedSegment.crossfadeMs}ms
                    </span>
                  </div>

                  {selectedSegment.warning?.suggestedFix &&
                    (selectedSegment.crossfadeCurve !== selectedSegment.warning.suggestedFix.curve ||
                      selectedSegment.crossfadeMs !== selectedSegment.warning.suggestedFix.ms) && (
                      <button
                        onClick={() => applySuggestedFix(selectedSegment)}
                        className="w-full flex items-center justify-center gap-1.5 text-xs h-7 rounded-md border border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100"
                      >
                        <Sparkles className="h-3 w-3" />
                        Apply validator suggestion (
                        {CURVE_LABEL[selectedSegment.warning.suggestedFix.curve]}, {selectedSegment.warning.suggestedFix.ms}ms)
                      </button>
                    )}
                </div>
              )}

              <Separator />

              {/* --- read-only diagnostics --- */}
              <div className="space-y-2">
                <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Diagnostics</div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground w-28 shrink-0">Boundary alignment</span>
                  <Badge variant="outline" className="text-xs font-normal">
                    aligned to bar grid
                  </Badge>
                </div>
                <div className="flex items-start gap-2">
                  <span className="text-xs text-muted-foreground w-28 shrink-0 pt-0.5">Adjacency</span>
                  {selectedSegment.warning ? (
                    <div
                      className={`flex items-start gap-1.5 rounded-md border px-2 py-1.5 text-xs flex-1 ${
                        selectedSegment.warning.severity === "warn"
                          ? "border-amber-200 bg-amber-50 text-amber-800"
                          : "border-slate-200 bg-slate-50 text-slate-600"
                      }`}
                    >
                      <SeverityIcon severity={selectedSegment.warning.severity} />
                      <span>{selectedSegment.warning.message}</span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5 text-xs text-emerald-700">
                      <CircleCheck className="h-3.5 w-3.5" />
                      same-source, natural adjacency
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-xs text-muted-foreground">Select a segment to edit and inspect it.</div>
          )}
        </div>
      </div>

      {/* ---------------- BOTTOM PANEL — Problems / Assistant ---------------- */}
      <div className="h-56 border-t border-border shrink-0 flex flex-col">
        <div className="flex items-center px-2 h-7 border-b border-border shrink-0">
          <div className="flex items-center bg-muted rounded-md p-0.5">
            <button
              onClick={() => setBottomTab("problems")}
              className={`px-2 h-6 rounded text-xs flex items-center gap-1.5 ${
                bottomTab === "problems" ? "bg-background shadow-sm" : "text-muted-foreground"
              }`}
            >
              Problems
              <span className="opacity-70">{problems.length}</span>
            </button>
            <button
              onClick={() => setBottomTab("assistant")}
              className={`px-2 h-6 rounded text-xs flex items-center gap-1.5 ${
                bottomTab === "assistant" ? "bg-background shadow-sm" : "text-muted-foreground"
              }`}
            >
              <Bot className="h-3 w-3" /> Assistant
            </button>
          </div>
        </div>

        {bottomTab === "problems" ? (
          <div className="flex-1 overflow-y-auto">
            <div className="w-full text-xs">
              <div
                className="grid gap-0 px-3 h-7 items-center border-b border-border text-xs text-muted-foreground sticky top-0 bg-background"
                style={{ gridTemplateColumns: "28px 64px 90px 90px 1fr" }}
              >
                <span></span>
                <span>Location</span>
                <span>Splice</span>
                <span>Rule</span>
                <span>Message</span>
              </div>
              {problems.map((seg) => (
                <div
                  key={seg.id}
                  onClick={() => selectSegmentFromProblem(seg)}
                  onMouseEnter={() => setHoveredSegmentId(seg.id)}
                  onMouseLeave={() => setHoveredSegmentId(null)}
                  className={`grid gap-0 px-3 h-8 items-center border-b border-border last:border-b-0 cursor-pointer ${
                    hoveredSegmentId === seg.id ? "bg-muted/50" : ""
                  }`}
                  style={{ gridTemplateColumns: "28px 64px 90px 90px 1fr" }}
                >
                  <SeverityIcon severity={seg.warning.severity} />
                  <span className="tabular-nums">{formatTime(seg.compStart)}</span>
                  <span>
                    <span className={`px-1.5 py-0.5 rounded border text-xs ${SOURCE_COLOR[seg.source].chip}`}>
                      {seg.source}
                    </span>
                  </span>
                  <span className="text-muted-foreground">{seg.warning.rule}</span>
                  <span className="truncate">{seg.warning.message}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col min-h-0">
            <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
              {messages.map((t, i) => (
                <ChatTurn key={i} turn={t} />
              ))}
              {thinking && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Bot className="h-3.5 w-3.5 shrink-0" />
                  <span className="animate-pulse">Recut is thinking…</span>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
            <div className="border-t border-border p-2 flex items-center gap-2 shrink-0">
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSend();
                }}
                placeholder="Ask Recut to edit, validate, or explain…"
                className="flex-1 h-7 text-xs border border-border rounded-md px-2 bg-background focus:outline-none focus:ring-1 focus:ring-foreground/30"
              />
              <Button size="icon" className="h-7 w-7" onClick={handleSend}>
                <Send className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
