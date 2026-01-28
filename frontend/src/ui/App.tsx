import React, { useEffect, useMemo, useState } from "react";

type ExecutionSummary = {
  execution_id: string;
  user_id: string;
  url: string;
  status: string;
  updated_at: string;
  interrupt?: any;
};

type ExecutionStateResponse = {
  execution_id: string;
  status: string;
  state: any;
};

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`);
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as T;
}

async function apiPost<T>(path: string, body: any): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as T;
}

export function App() {
  const [inbox, setInbox] = useState<ExecutionSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<ExecutionStateResponse | null>(null);
  const [err, setErr] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const [userId, setUserId] = useState("demo-user");
  const [url, setUrl] = useState("");

  const selectedState = selected?.state || {};
  const twitterDraft = selectedState.twitter_draft || "";
  const linkedinDraft = selectedState.linkedin_draft || "";
  const img = selectedState.image_metadata || {};

  const [editedTwitter, setEditedTwitter] = useState("");
  const [editedLinkedin, setEditedLinkedin] = useState("");

  const [approveContent, setApproveContent] = useState(false);
  const [rejectContent, setRejectContent] = useState(false);
  const [approveImage, setApproveImage] = useState(false);
  const [rejectImage, setRejectImage] = useState(false);
  const [regenTwitter, setRegenTwitter] = useState(false);
  const [regenLinkedin, setRegenLinkedin] = useState(false);

  const interrupt = useMemo(() => {
    const intr = (selectedState && selectedState.__interrupt__ && selectedState.__interrupt__[0]) || null;
    return intr?.value || null;
  }, [selectedState]);

  async function refreshInbox() {
    setErr("");
    const data = await apiGet<ExecutionSummary[]>("/v1/inbox");
    setInbox(data);
    if (!selectedId && data[0]?.execution_id) setSelectedId(data[0].execution_id);
  }

  async function loadExecution(executionId: string) {
    setErr("");
    const data = await apiGet<ExecutionStateResponse>(`/v1/executions/${executionId}`);
    setSelected(data);
    setSelectedId(executionId);

    // Reset action UI but keep edits empty by default
    setEditedTwitter("");
    setEditedLinkedin("");
    setApproveContent(false);
    setRejectContent(false);
    setApproveImage(false);
    setRejectImage(false);
    setRegenTwitter(false);
    setRegenLinkedin(false);
  }

  useEffect(() => {
    refreshInbox().catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    if (selectedId) loadExecution(selectedId).catch((e) => setErr(String(e)));
  }, [selectedId]);

  async function createExecution() {
    setLoading(true);
    setErr("");
    try {
      const res = await apiPost<ExecutionStateResponse>("/v1/executions", { user_id: userId, url });
      await refreshInbox();
      await loadExecution(res.execution_id);
      setUrl("");
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function submitActions() {
    if (!selectedId) return;
    setLoading(true);
    setErr("");
    try {
      const res = await apiPost<ExecutionStateResponse>(`/v1/executions/${selectedId}/actions`, {
        approve_content: approveContent,
        reject_content: rejectContent,
        approve_image: approveImage,
        reject_image: rejectImage,
        regenerate_twitter: regenTwitter,
        regenerate_linkedin: regenLinkedin,
        edited_twitter: editedTwitter,
        edited_linkedin: editedLinkedin,
      });
      setSelected(res);
      await refreshInbox();
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="layout">
      <div className="sidebar">
        <div className="card" style={{ marginBottom: 14 }}>
          <div style={{ fontWeight: 700, marginBottom: 10 }}>New URL</div>
          <div className="muted" style={{ marginBottom: 8 }}>
            Creates a LangGraph execution. It will pause for review before any publish.
          </div>
          <div style={{ display: "grid", gap: 10 }}>
            <input value={userId} onChange={(e) => setUserId(e.target.value)} type="text" placeholder="user_id" />
            <input value={url} onChange={(e) => setUrl(e.target.value)} type="text" placeholder="https://example.com/blog" />
            <button disabled={loading || !url} onClick={createExecution}>
              Create execution
            </button>
          </div>
        </div>

        <div className="card" style={{ marginBottom: 14 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>Connections</div>
          <div className="muted" style={{ marginBottom: 8 }}>
            Connect your accounts once. Tokens are stored securely and reused for all executions for this <code>user_id</code>.
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <button
              className="secondary"
              type="button"
              onClick={() => window.open(`${API_BASE}/v1/oauth/twitter/start?user_id=${encodeURIComponent(userId)}`, "_blank")}
            >
              Connect Twitter
            </button>
            <button
              className="secondary"
              type="button"
              onClick={() => window.open(`${API_BASE}/v1/oauth/linkedin/start?user_id=${encodeURIComponent(userId)}`, "_blank")}
            >
              Connect LinkedIn
            </button>
          </div>
        </div>

        <div className="topBar">
          <div style={{ fontWeight: 700 }}>Agent Inbox</div>
          <button className="secondary" onClick={() => refreshInbox().catch((e) => setErr(String(e)))}>
            Refresh
          </button>
        </div>

        {inbox.map((x) => (
          <div
            key={x.execution_id}
            className={`listItem ${x.execution_id === selectedId ? "listItemActive" : ""}`}
            onClick={() => setSelectedId(x.execution_id)}
          >
            <div style={{ fontWeight: 700 }}>{x.status}</div>
            <div className="muted">{x.updated_at}</div>
            <div className="muted" style={{ marginTop: 6, wordBreak: "break-word" }}>
              {x.url}
            </div>
          </div>
        ))}
      </div>

      <div className="main">
        <div className="card">
          <div className="topBar">
            <div>
              <div style={{ fontWeight: 800 }}>Execution</div>
              <div className="muted">{selectedId || "None selected"}</div>
            </div>
            <div className="muted">{selected?.status || ""}</div>
          </div>

          {err ? (
            <div className="card" style={{ borderColor: "#fecaca", background: "#fff1f2", marginBottom: 14 }}>
              <div style={{ fontWeight: 800, marginBottom: 6 }}>Error</div>
              <div className="muted" style={{ color: "#7f1d1d", whiteSpace: "pre-wrap" }}>
                {err}
              </div>
            </div>
          ) : null}

          {selected ? (
            <>
              <div className="muted" style={{ marginBottom: 10 }}>
                Source URL: <span style={{ wordBreak: "break-word" }}>{selectedState.url}</span>
              </div>

              {interrupt?.type === "reauth_required" ? (
                <div className="card" style={{ marginBottom: 14, borderColor: "#fde68a", background: "#fffbeb" }}>
                  <div style={{ fontWeight: 800, marginBottom: 6 }}>Re-auth required</div>
                  <div className="muted" style={{ marginBottom: 6 }}>
                    Needs: {(interrupt.needs || []).join(", ")}
                  </div>
                  <div className="muted" style={{ marginBottom: 10 }}>
                    Complete OAuth, then click “Submit actions” to resume.
                  </div>
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    <a href={`${API_BASE}/v1/oauth/twitter/start?user_id=${encodeURIComponent(selectedState.user_id)}`} target="_blank">
                      <button className="secondary" type="button">Connect Twitter</button>
                    </a>
                    <a href={`${API_BASE}/v1/oauth/linkedin/start?user_id=${encodeURIComponent(selectedState.user_id)}`} target="_blank">
                      <button className="secondary" type="button">Connect LinkedIn</button>
                    </a>
                  </div>
                </div>
              ) : null}

              <div className="row" style={{ marginBottom: 14 }}>
                <div className="card">
                  <div style={{ fontWeight: 800, marginBottom: 8 }}>Twitter draft</div>
                  <div className="muted" style={{ marginBottom: 8 }}>
                    Draft (generated):
                  </div>
                  <textarea readOnly value={twitterDraft} />
                  <div className="muted" style={{ marginTop: 10, marginBottom: 6 }}>
                    Optional edit (only affects Twitter):
                  </div>
                  <textarea value={editedTwitter} onChange={(e) => setEditedTwitter(e.target.value)} />
                </div>

                <div className="card">
                  <div style={{ fontWeight: 800, marginBottom: 8 }}>LinkedIn draft</div>
                  <div className="muted" style={{ marginBottom: 8 }}>
                    Draft (generated):
                  </div>
                  <textarea readOnly value={linkedinDraft} />
                  <div className="muted" style={{ marginTop: 10, marginBottom: 6 }}>
                    Optional edit (only affects LinkedIn):
                  </div>
                  <textarea value={editedLinkedin} onChange={(e) => setEditedLinkedin(e.target.value)} />
                </div>
              </div>

              <div className="row" style={{ marginBottom: 14 }}>
                <div className="card">
                  <div style={{ fontWeight: 800, marginBottom: 10 }}>Selected image (article-only)</div>
                  {img?.image_url ? (
                    <>
                      <img className="imgPreview" src={img.image_url} alt={img.caption || "Selected"} />
                      <div className="muted" style={{ marginTop: 8, wordBreak: "break-word" }}>
                        {img.image_url}
                      </div>
                    </>
                  ) : (
                    <div className="muted">No image extracted/selected.</div>
                  )}
                </div>

                <div className="card">
                  <div style={{ fontWeight: 800, marginBottom: 10 }}>Actions (granular HITL)</div>
                  <div className="checks" style={{ marginBottom: 12 }}>
                    <label className="check">
                      <input type="checkbox" checked={approveContent} onChange={(e) => setApproveContent(e.target.checked)} />
                      Approve content (both)
                    </label>
                    <label className="check">
                      <input type="checkbox" checked={rejectContent} onChange={(e) => setRejectContent(e.target.checked)} />
                      Reject content (terminates)
                    </label>
                    <label className="check">
                      <input type="checkbox" checked={approveImage} onChange={(e) => setApproveImage(e.target.checked)} />
                      Approve image
                    </label>
                    <label className="check">
                      <input type="checkbox" checked={rejectImage} onChange={(e) => setRejectImage(e.target.checked)} />
                      Reject image (text-only)
                    </label>
                    <label className="check">
                      <input type="checkbox" checked={regenTwitter} onChange={(e) => setRegenTwitter(e.target.checked)} />
                      Regenerate Twitter
                    </label>
                    <label className="check">
                      <input type="checkbox" checked={regenLinkedin} onChange={(e) => setRegenLinkedin(e.target.checked)} />
                      Regenerate LinkedIn
                    </label>
                  </div>

                  <div style={{ display: "flex", gap: 10 }}>
                    <button disabled={loading} onClick={submitActions}>
                      Submit actions
                    </button>
                    <button className="secondary" disabled={loading} onClick={() => loadExecution(selectedId!).catch((e) => setErr(String(e)))}>
                      Reload
                    </button>
                  </div>

                  <div className="muted" style={{ marginTop: 10 }}>
                    Publishing only happens after approval; image upload only happens if image is approved.
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="muted">Select an execution from the Inbox.</div>
          )}
        </div>
      </div>
    </div>
  );
}

