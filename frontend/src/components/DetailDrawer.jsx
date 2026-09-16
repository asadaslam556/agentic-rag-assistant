import { useEffect, useRef } from "react";
import VerificationStrip from "./VerificationStrip.jsx";
import SourcesPanel from "./SourcesPanel.jsx";
import TracePanel from "./TracePanel.jsx";
import { CloseIcon, DownloadIcon } from "./Icons.jsx";

export default function DetailDrawer({ turn, onClose }) {
  const closeRef = useRef(null);

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // move focus into the drawer so Escape and Tab work straight away, and hand
  // it back to whatever opened the drawer when it closes
  useEffect(() => {
    const previous = document.activeElement;
    closeRef.current?.focus({ preventScroll: true });
    return () => {
      if (previous instanceof HTMLElement) previous.focus({ preventScroll: true });
    };
  }, []);

  if (!turn || !turn.answer) return null;
  const answer = turn.answer;
  const prefix = `turn-${turn.id}`;

  const download = () => {
    const blob = new Blob([JSON.stringify(answer, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `answer-${turn.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <div className="scrim drawer-scrim is-open" onClick={onClose} />
      <section className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
        <header className="drawer-head">
          <div className="drawer-heading">
            <div className="eyebrow" id="drawer-title">
              Sources and reasoning
            </div>
            <p className="drawer-question">{answer.question}</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="icon-btn"
            onClick={onClose}
            aria-label="Close"
            title="Close (Esc)"
          >
            <CloseIcon />
          </button>
        </header>

        <div className="drawer-body">
          <VerificationStrip verification={answer.verification} attempts={answer.attempts} />
          <SourcesPanel citations={answer.citations} evidence={answer.evidence} anchorPrefix={prefix} />
          <TracePanel
            steps={answer.steps}
            timings={answer.timings_ms}
            subQuestions={answer.sub_questions || []}
            branches={answer.branches || []}
          />
        </div>

        <footer className="drawer-foot">
          <button type="button" className="btn" onClick={download}>
            <DownloadIcon size={16} />
            Export as JSON
          </button>
        </footer>
      </section>
    </>
  );
}
