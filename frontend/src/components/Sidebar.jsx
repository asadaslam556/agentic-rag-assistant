import { useEffect, useRef, useState } from "react";
import { relativeTime } from "../sessions.js";
import { CloseIcon, LogoMark, PencilIcon, PlusIcon, TrashIcon } from "./Icons.jsx";

export default function Sidebar({
  mobileOpen,
  sessions,
  currentId,
  onSelect,
  onNew,
  onRename,
  onDelete,
  onClose,
}) {
  const [editingId, setEditingId] = useState("");
  const [draft, setDraft] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    if (editingId && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingId]);

  const startEdit = (session, event) => {
    event.stopPropagation();
    setEditingId(session.id);
    setDraft(session.title);
  };

  const commit = (id) => {
    const title = draft.trim();
    if (title) onRename(id, title);
    setEditingId("");
  };

  const remove = (session, event) => {
    event.stopPropagation();
    if (session.turns.length && !window.confirm(`Delete "${session.title}"?`)) return;
    onDelete(session.id);
  };

  return (
    <>
      <div className={`scrim sidebar-scrim ${mobileOpen ? "is-open" : ""}`} onClick={onClose} />
      <aside id="sidebar" className={`sidebar ${mobileOpen ? "is-open" : ""}`} aria-label="Conversations">
        <div className="sidebar-head">
          <div className="brand">
            <LogoMark size={26} />
            <span className="brand-name">Agentic RAG</span>
            <button
              type="button"
              className="icon-btn only-mobile"
              onClick={onClose}
              aria-label="Close conversations"
            >
              <CloseIcon />
            </button>
          </div>
          <button type="button" className="btn primary wide" onClick={onNew}>
            <PlusIcon size={16} />
            New chat
          </button>
        </div>

        <div className="sidebar-section">Recent</div>

        <nav className="session-list">
          {sessions.map((session) => {
            const active = session.id === currentId;
            if (editingId === session.id) {
              return (
                <div key={session.id} className="session is-editing">
                  <input
                    ref={inputRef}
                    className="session-edit"
                    value={draft}
                    aria-label="Conversation name"
                    maxLength={80}
                    onChange={(event) => setDraft(event.target.value)}
                    onBlur={() => commit(session.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") commit(session.id);
                      if (event.key === "Escape") setEditingId("");
                    }}
                  />
                </div>
              );
            }
            return (
              <div key={session.id} className={`session ${active ? "is-active" : ""}`}>
                <button
                  type="button"
                  className="session-main"
                  onClick={() => onSelect(session.id)}
                  aria-current={active ? "page" : undefined}
                  title={session.title}
                >
                  <span className="session-title">{session.title}</span>
                  <span className="session-meta">
                    {session.turns.length === 0
                      ? "Empty"
                      : `${session.turns.length} ${session.turns.length === 1 ? "question" : "questions"}`}
                    {" · "}
                    {relativeTime(session.updatedAt)}
                  </span>
                </button>
                <div className="session-tools">
                  <button
                    type="button"
                    className="icon-btn small"
                    title="Rename"
                    aria-label={`Rename ${session.title}`}
                    onClick={(event) => startEdit(session, event)}
                  >
                    <PencilIcon size={15} />
                  </button>
                  <button
                    type="button"
                    className="icon-btn small danger"
                    title="Delete"
                    aria-label={`Delete ${session.title}`}
                    onClick={(event) => remove(session, event)}
                  >
                    <TrashIcon size={15} />
                  </button>
                </div>
              </div>
            );
          })}
        </nav>

        <div className="sidebar-foot">
          <span>Chat history is saved in this browser only.</span>
          <a href="https://github.com/asadaslam556/agentic-rag-assistant" target="_blank" rel="noreferrer">
            Built by Asad Aslam
          </a>
        </div>
      </aside>
    </>
  );
}
