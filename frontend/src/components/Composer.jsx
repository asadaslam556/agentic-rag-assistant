import { forwardRef, useLayoutEffect, useRef } from "react";
import { PaperclipIcon, SendIcon } from "./Icons.jsx";

const ACCEPT = ".pdf,.md,.markdown,.txt,.html,.htm";
const MAX_HEIGHT = 200;

const Composer = forwardRef(function Composer(
  { value, onChange, onSubmit, onUpload, busy, uploading },
  textareaRef
) {
  const fileInput = useRef(null);

  // Grow with the text up to a cap, then scroll inside the box. An empty box
  // drops the inline height entirely: measuring before the stylesheet and
  // fonts settle can report a wildly tall scrollHeight on first paint.
  useLayoutEffect(() => {
    const box = textareaRef.current;
    if (!box) return undefined;
    const fit = () => {
      box.style.height = "";
      if (!box.value) return;
      box.style.height = `${Math.min(box.scrollHeight, MAX_HEIGHT)}px`;
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [value, textareaRef]);

  const canSend = !busy && value.trim().length > 0;

  return (
    <div className="composer">
      <form
        className="composer-inner"
        onSubmit={(event) => {
          event.preventDefault();
          if (canSend) onSubmit();
        }}
      >
        <button
          type="button"
          className="icon-btn attach"
          title="Add documents (pdf, md, txt, html)"
          aria-label="Add documents to the index"
          onClick={() => fileInput.current && fileInput.current.click()}
          disabled={busy || uploading}
        >
          {uploading ? <span className="spinner" aria-hidden="true" /> : <PaperclipIcon />}
        </button>
        <input
          ref={fileInput}
          type="file"
          multiple
          accept={ACCEPT}
          hidden
          onChange={(event) => {
            const files = Array.from(event.target.files || []);
            event.target.value = "";
            if (files.length) onUpload(files);
          }}
        />
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          placeholder="Ask about your documents"
          aria-label="Question"
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            // Enter sends, Shift+Enter adds a line. Skip while an IME is composing.
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              if (canSend) onSubmit();
            }
          }}
          autoFocus
        />
        <button
          type="submit"
          className="send-btn"
          disabled={!canSend}
          aria-label={busy ? "Working on the answer" : "Send"}
          title={busy ? "Working on the answer" : "Send (Enter)"}
        >
          {busy ? <span className="spinner light" aria-hidden="true" /> : <SendIcon size={18} />}
        </button>
      </form>
      <p className="composer-hint">
        {uploading
          ? "Indexing your files..."
          : "Every answer is checked against its sources. Shift+Enter for a new line."}
      </p>
    </div>
  );
});

export default Composer;
