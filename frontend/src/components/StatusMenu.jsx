import { useEffect, useRef, useState } from "react";

// The header used to print the model name and the chunk count as bare pills,
// which meant nothing to anyone who hadn't read the backend. Now it is a
// single status button with a plain-language label, and the details live in
// a small popover for when you actually want them.

function modelLabel(llm) {
  if (!llm) return "";
  if (llm === "mock") return "Demo mode";
  const [provider, ...rest] = llm.split(":");
  const model = rest.join(":");
  return model ? model.replace(/@default$/, "") : provider;
}

const COMPONENT_NAMES = {
  llm: "Language model",
  index: "Document index",
  catalog: "Product catalog",
  database: "SQL database",
  web_search: "Web search",
};

export default function StatusMenu({ health, healthError, onRetry }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onPointer = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    };
    const onKey = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  let tone = "pending";
  let label = "Connecting";
  if (health) {
    tone = health.status === "degraded" ? "warn" : "ok";
    label = modelLabel(health.llm);
  } else if (healthError) {
    tone = "bad";
    label = "Offline";
  }

  const isMock = health && health.llm === "mock";
  const components = health ? Object.entries(health.components || {}) : [];

  return (
    <div className="status" ref={rootRef}>
      <button
        type="button"
        className="status-btn"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="dialog"
        aria-expanded={open}
        title="Backend status"
      >
        <span className={`dot ${tone}`} aria-hidden="true" />
        <span className="status-label">{label}</span>
      </button>

      {open && (
        <div className="popover" role="dialog" aria-label="Backend status">
          {!health && healthError && (
            <>
              <p className="popover-title">Can't reach the backend</p>
              <p className="popover-text">{healthError}</p>
              <button type="button" className="btn small" onClick={onRetry}>
                Try again
              </button>
            </>
          )}

          {!health && !healthError && <p className="popover-text">Checking the backend...</p>}

          {health && (
            <>
              <p className="popover-title">
                {health.status === "degraded" ? "Running with problems" : "Everything is running"}
              </p>
              {isMock && (
                <p className="popover-text">
                  No language model is connected, so answers come from the built-in offline
                  mock. Start Ollama or set LLM_PROVIDER for real answers.
                </p>
              )}
              <dl className="facts">
                <dt>Model</dt>
                <dd>{health.llm}</dd>
                <dt>Documents</dt>
                <dd>{health.chunks_indexed.toLocaleString()} passages indexed</dd>
                <dt>Retrieval</dt>
                <dd>{health.retrieval_mode}</dd>
                <dt>Version</dt>
                <dd>{health.version}</dd>
              </dl>
              {components.some(([, part]) => part.status !== "ok") && (
                <ul className="problems">
                  {components
                    .filter(([, part]) => part.status !== "ok")
                    .map(([name, part]) => (
                      <li key={name}>
                        <strong>{COMPONENT_NAMES[name] || name}:</strong> {part.detail}
                      </li>
                    ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
