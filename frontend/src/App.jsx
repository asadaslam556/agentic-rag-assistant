import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { chat, fetchHealth, ingestSamples, streamChat, uploadFiles } from "./api.js";
import { applyTheme, readStoredTheme, watchSystemTheme } from "./theme.js";
import { loadSessions, newSession, saveSessions, titleFromQuestion } from "./sessions.js";
import Header from "./components/Header.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Composer from "./components/Composer.jsx";
import Turn from "./components/Turn.jsx";
import DetailDrawer from "./components/DetailDrawer.jsx";
import { CloseIcon, LogoMark } from "./components/Icons.jsx";

const SAMPLES = [
  { label: "Specs", question: "What is the payload capacity of the Atlas P2?" },
  { label: "Pricing", question: "What does the Scale plan cost per robot per month?" },
  { label: "Math", question: "What is 23 * 649?" },
  { label: "Rollout", question: "How long does a typical Atlas deployment take?" },
];

// Keep in sync with the breakpoint in styles.css
const MOBILE_QUERY = "(max-width: 860px)";
const SIDEBAR_KEY = "arag.sidebar";

function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const list = window.matchMedia(query);
    const onChange = () => setMatches(list.matches);
    onChange();
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

function readCollapsed() {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === "collapsed";
  } catch {
    return false;
  }
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState("");
  const [sessions, setSessions] = useState(() => {
    const saved = loadSessions();
    return saved.length ? saved : [newSession()];
  });
  const [currentId, setCurrentId] = useState(() => sessions[0].id);
  const [draft, setDraft] = useState("");
  const [detailTurnId, setDetailTurnId] = useState(null);
  const [ingesting, setIngesting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState(null);
  const [theme, setTheme] = useState(readStoredTheme);
  const threadRef = useRef(null);
  const composerRef = useRef(null);

  // The menu button used to flip a flag that only the mobile CSS listened to,
  // so on a desktop-width window it did nothing at all. Desktop and mobile
  // now each get their own state: a remembered collapse on desktop, and an
  // overlay on small screens that always starts closed.
  const isMobile = useMediaQuery(MOBILE_QUERY);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);
  const sidebarVisible = isMobile ? mobileOpen : !collapsed;

  useEffect(() => {
    if (!isMobile) setMobileOpen(false);
  }, [isMobile]);

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, collapsed ? "collapsed" : "open");
    } catch {
      // storage blocked: the layout still works, it just isn't remembered
    }
  }, [collapsed]);

  useEffect(() => {
    if (!mobileOpen) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  const toggleSidebar = useCallback(() => {
    if (isMobile) setMobileOpen((open) => !open);
    else setCollapsed((value) => !value);
  }, [isMobile]);

  const current = useMemo(
    () => sessions.find((session) => session.id === currentId) || sessions[0],
    [sessions, currentId]
  );
  const turns = current ? current.turns : [];
  const busy = turns.some((turn) => turn.status === "streaming");
  const lastTurn = turns[turns.length - 1];

  // ---------------------------------------------------------------- theme

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => watchSystemTheme(() => theme === "system" && applyTheme("system")), [theme]);

  // --------------------------------------------------------------- health

  const loadHealth = useCallback(async () => {
    try {
      setHealth(await fetchHealth());
      setHealthError("");
    } catch (err) {
      setHealth(null);
      setHealthError(err.message || "Backend not reachable.");
    }
  }, []);

  // re-check now and then so the status dot notices a backend that went away
  // or came back, but skip it while the tab is in the background
  useEffect(() => {
    loadHealth();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") loadHealth();
    }, 30000);
    return () => clearInterval(timer);
  }, [loadHealth]);

  // ------------------------------------------------------------ scrolling

  // Jump to the bottom when a new question goes in or a session opens. While
  // tokens stream, only follow along if the reader is already near the
  // bottom, so scrolling up to reread something isn't yanked back down.
  useEffect(() => {
    const area = threadRef.current;
    if (area) area.scrollTop = area.scrollHeight;
  }, [turns.length, current && current.id]);

  useEffect(() => {
    const area = threadRef.current;
    if (!area) return;
    const distance = area.scrollHeight - area.scrollTop - area.clientHeight;
    if (distance < 160) area.scrollTop = area.scrollHeight;
  }, [lastTurn && lastTurn.liveText, lastTurn && lastTurn.status, lastTurn && lastTurn.liveSteps]);

  // ------------------------------------------------------------- sessions

  // persist once a turn settles, not on every streamed token
  const streamingAnywhere = sessions.some((session) =>
    session.turns.some((turn) => turn.status === "streaming")
  );
  useEffect(() => {
    if (!streamingAnywhere) saveSessions(sessions);
  }, [sessions, streamingAnywhere]);

  const updateSession = useCallback((id, updater) => {
    setSessions((previous) =>
      previous.map((session) =>
        session.id === id ? { ...updater(session), updatedAt: Date.now() } : session
      )
    );
  }, []);

  const updateTurn = useCallback(
    (sessionId, turnId, updater) => {
      updateSession(sessionId, (session) => ({
        ...session,
        turns: session.turns.map((turn) => (turn.id === turnId ? updater(turn) : turn)),
      }));
    },
    [updateSession]
  );

  const startNewSession = useCallback(() => {
    // reuse an untouched chat instead of stacking empty ones
    const empty = sessions.find((session) => session.turns.length === 0);
    if (empty) {
      setCurrentId(empty.id);
    } else {
      const session = newSession();
      setSessions((previous) => [session, ...previous]);
      setCurrentId(session.id);
    }
    setMobileOpen(false);
    setNotice(null);
    setDetailTurnId(null);
    // on phones focusing would pop the keyboard over the welcome screen
    if (!isMobile) requestAnimationFrame(() => composerRef.current && composerRef.current.focus());
  }, [sessions, isMobile]);

  const selectSession = useCallback((id) => {
    setCurrentId(id);
    setMobileOpen(false);
    setDetailTurnId(null);
    setNotice(null);
  }, []);

  const deleteSession = useCallback(
    (id) => {
      const remaining = sessions.filter((session) => session.id !== id);
      const next = remaining.length ? remaining : [newSession()];
      setSessions(next);
      if (id === currentId) setCurrentId(next[0].id);
    },
    [sessions, currentId]
  );

  const renameSession = useCallback(
    (id, title) => updateSession(id, (session) => ({ ...session, title })),
    [updateSession]
  );

  // ------------------------------------------------------------------ ask

  const submit = useCallback(
    async (text) => {
      const question = (text ?? draft).trim();
      if (!question || busy || !current) return;
      if (question.length < 3) {
        setNotice({ tone: "bad", text: "Questions need at least 3 characters." });
        return;
      }
      const sessionId = current.id;
      setDraft("");
      setNotice(null);

      const id = Date.now();
      const history = current.turns
        .filter((turn) => turn.status === "done" && turn.answer)
        .slice(-6)
        .map((turn) => ({ question: turn.question, answer: turn.answer.text }));

      updateSession(sessionId, (session) => ({
        ...session,
        title:
          session.turns.length === 0 && session.title === "New chat"
            ? titleFromQuestion(question)
            : session.title,
        turns: [
          ...session.turns,
          {
            id,
            question,
            status: "streaming",
            stage: "planning",
            rewritten: "",
            subQuestions: [],
            liveText: "",
            liveSteps: [],
            answer: null,
            errorMessage: "",
          },
        ],
      }));

      let settled = false;
      const handleEvent = (name, payload) => {
        if (name === "rewrite") {
          updateTurn(sessionId, id, (turn) => ({ ...turn, rewritten: payload.question }));
        } else if (name === "decompose") {
          updateTurn(sessionId, id, (turn) => ({
            ...turn,
            subQuestions: payload.sub_questions || [],
          }));
        } else if (name === "stage") {
          updateTurn(sessionId, id, (turn) => ({ ...turn, stage: payload.name }));
        } else if (name === "step") {
          updateTurn(sessionId, id, (turn) => ({ ...turn, liveSteps: [...turn.liveSteps, payload] }));
        } else if (name === "branch_error") {
          updateTurn(sessionId, id, (turn) => ({
            ...turn,
            liveSteps: [
              ...turn.liveSteps,
              { step: `err-${payload.branch}`, action: "branch failed", branch: payload.branch },
            ],
          }));
        } else if (name === "synthesis_start") {
          updateTurn(sessionId, id, (turn) => ({ ...turn, liveText: "" }));
        } else if (name === "token") {
          updateTurn(sessionId, id, (turn) => ({ ...turn, liveText: turn.liveText + payload.text }));
        } else if (name === "answer") {
          settled = true;
          updateTurn(sessionId, id, (turn) => ({
            ...turn,
            status: "done",
            answer: payload,
            subQuestions: payload.sub_questions || turn.subQuestions,
          }));
        } else if (name === "error") {
          settled = true;
          updateTurn(sessionId, id, (turn) => ({
            ...turn,
            status: "error",
            errorMessage: payload.message || "The pipeline failed.",
          }));
        }
      };

      try {
        await streamChat(question, history, handleEvent);
        if (!settled) throw new Error("The stream ended before an answer arrived.");
      } catch {
        if (settled) return;
        // streaming blocked by a proxy or dropped: fall back to one plain request
        try {
          const answer = await chat(question, history);
          updateTurn(sessionId, id, (turn) => ({
            ...turn,
            status: "done",
            answer,
            subQuestions: answer.sub_questions || [],
          }));
        } catch (err) {
          updateTurn(sessionId, id, (turn) => ({
            ...turn,
            status: "error",
            errorMessage: err.message || "The request failed.",
          }));
          loadHealth();
        }
      }
    },
    [draft, busy, current, updateSession, updateTurn, loadHealth]
  );

  // -------------------------------------------------------------- corpus

  const ingest = useCallback(async () => {
    setIngesting(true);
    setNotice(null);
    try {
      await ingestSamples();
      await loadHealth();
      setNotice({ tone: "ok", text: "Sample documents are indexed. Try one of the questions below." });
    } catch (err) {
      setNotice({ tone: "bad", text: err.message || "Ingestion failed." });
    } finally {
      setIngesting(false);
    }
  }, [loadHealth]);

  const upload = useCallback(
    async (files) => {
      setUploading(true);
      setNotice(null);
      try {
        const result = await uploadFiles(files);
        const saved = result.results.filter((entry) => entry.status === "saved").length;
        const rejected = result.results.filter((entry) => entry.status === "rejected");
        let text = saved
          ? `Added ${saved} file${saved === 1 ? "" : "s"} (${result.chunks_added} passages) to the index.`
          : "No files were added.";
        if (rejected.length) {
          text += ` Skipped: ${rejected.map((entry) => `${entry.file} (${entry.detail})`).join(", ")}.`;
        }
        setNotice({ tone: rejected.length ? "warn" : "ok", text });
        await loadHealth();
      } catch (err) {
        setNotice({ tone: "bad", text: err.message || "Upload failed." });
      } finally {
        setUploading(false);
      }
    },
    [loadHealth]
  );

  const detailTurn = turns.find((turn) => turn.id === detailTurnId);
  const indexEmpty = health && health.chunks_indexed === 0;
  const closeDetail = useCallback(() => setDetailTurnId(null), []);

  return (
    <div className={`shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      <Sidebar
        mobileOpen={mobileOpen}
        sessions={sessions}
        currentId={current ? current.id : ""}
        onSelect={selectSession}
        onNew={startNewSession}
        onRename={renameSession}
        onDelete={deleteSession}
        onClose={() => setMobileOpen(false)}
      />

      <div className="main">
        <Header
          health={health}
          healthError={healthError}
          title={current ? current.title : "New chat"}
          turnCount={turns.length}
          sidebarVisible={sidebarVisible}
          onToggleSidebar={toggleSidebar}
          onRetryHealth={loadHealth}
          theme={theme}
          onThemeChange={setTheme}
        />

        <main className="thread-area" ref={threadRef}>
          {notice && (
            <div className={`notice ${notice.tone}`} role="status">
              <span>{notice.text}</span>
              <button
                type="button"
                className="icon-btn small"
                onClick={() => setNotice(null)}
                aria-label="Dismiss"
              >
                <CloseIcon size={15} />
              </button>
            </div>
          )}

          {indexEmpty && (
            <div className="notice warn">
              <span>No documents are indexed yet. Load the bundled sample set, or attach your own files.</span>
              <button type="button" className="btn small" onClick={ingest} disabled={ingesting}>
                {ingesting ? "Indexing..." : "Load sample documents"}
              </button>
            </div>
          )}

          {turns.length === 0 ? (
            <section className="intro">
              <LogoMark size={44} />
              <h2>What would you like to know?</h2>
              <p className="lede">
                Ask anything about your documents. The assistant searches them, writes an answer
                with citations, and checks each claim against its sources before showing it to you.
              </p>
              <div className="samples">
                {SAMPLES.map((sample) => (
                  <button
                    key={sample.question}
                    type="button"
                    className="sample"
                    onClick={() => submit(sample.question)}
                    disabled={busy || !health}
                  >
                    <span className="sample-label">{sample.label}</span>
                    <span className="sample-q">{sample.question}</span>
                  </button>
                ))}
              </div>
            </section>
          ) : (
            <div className="thread">
              {turns.map((turn) => (
                <Turn key={turn.id} turn={turn} onOpenDetail={setDetailTurnId} />
              ))}
            </div>
          )}
        </main>

        <Composer
          ref={composerRef}
          value={draft}
          onChange={setDraft}
          onSubmit={submit}
          onUpload={upload}
          busy={busy}
          uploading={uploading}
        />
      </div>

      {detailTurn && <DetailDrawer turn={detailTurn} onClose={closeDetail} />}
    </div>
  );
}
