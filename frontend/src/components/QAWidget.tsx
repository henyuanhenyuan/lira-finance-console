import { useState } from "react";
import { createPortal } from "react-dom";
import { api, money, type Insight } from "../lib/api";

type Turn = { q: string; a: Insight | null; error?: string };

export default function QAWidget() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);

  async function ask() {
    const question = q.trim();
    if (question.length < 2 || busy) return;
    setQ("");
    setBusy(true);
    const idx = turns.length;
    setTurns((t) => [...t, { q: question, a: null }]);
    try {
      const run = await api.createRun(question, "qa");
      const insight = run.result?.insight ?? null;
      setTurns((t) => t.map((x, i) => (i === idx ? { ...x, a: insight } : x)));
    } catch (e: any) {
      setTurns((t) => t.map((x, i) => (i === idx ? { ...x, error: e?.message ?? "失败" } : x)));
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return createPortal(
      <button className="btn primary qa-dock" style={{ width: "auto" }} onClick={() => setOpen(true)}>
        辅助问答
      </button>,
      document.body,
    );
  }

  return createPortal(
    <div className="glass qa-dock pad">
      <div className="qa-head" onClick={() => setOpen(false)}>
        <div className="row gap-8">
          <span className="badge cyan"><i className="dot" /> 辅助问答</span>
          <span className="muted" style={{ fontSize: 10.5 }}>核心分析已在视图内自动完成</span>
        </div>
        <span className="muted" style={{ fontSize: 16 }}>×</span>
      </div>

      <div className="qa-body stack gap-8 mt-12">
        {turns.length === 0 && (
          <div className="muted" style={{ fontSize: 12 }}>
            补充追问某个指标或口径即可，例如「退款率超过多少要预警？」。
          </div>
        )}
        {turns.map((t, i) => (
          <div className="stack gap-6" key={i}>
            <div className="qa-bubble me" style={{ alignSelf: "flex-end" }}>{t.q}</div>
            {t.error ? (
              <div className="qa-bubble" style={{ borderColor: "rgba(255,122,156,.4)" }}>出错：{t.error}</div>
            ) : t.a ? (
              <div className="stack gap-6">
                <div className="qa-bubble">{t.a.headline}</div>
                {t.a.actions?.slice(0, 2).map((a, j) => (
                  <div className="muted" key={j} style={{ fontSize: 11.5 }}>· {a.title}</div>
                ))}
                {t.a.drivers?.slice(0, 1).map((d, j) => (
                  <div className="muted mono" key={j} style={{ fontSize: 11 }}>
                    {d.factor} {d.impact ? money(d.impact) : ""}
                  </div>
                ))}
              </div>
            ) : (
              <div className="qa-bubble muted">分析中…</div>
            )}
          </div>
        ))}
      </div>

      <div className="row gap-8 mt-12">
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="追问一句…"
               onKeyDown={(e) => e.key === "Enter" && ask()} />
        <button className="btn primary sm" onClick={ask} disabled={busy}>{busy ? "…" : "发送"}</button>
      </div>
    </div>,
    document.body,
  );
}
