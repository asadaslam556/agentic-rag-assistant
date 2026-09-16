const CITE_SPLIT = /(\[\d+\])/g;
const CITE_MATCH = /^\[(\d+)\]$/;

// Citation markers point at source cards inside the evidence drawer. When the
// drawer is closed the card isn't in the page yet, so onOpenSource opens it
// first and the jump happens once the card has rendered.
function jumpToSource(anchorPrefix, marker) {
  const card = document.getElementById(`${anchorPrefix}-source-${marker}`);
  if (!card) return false;
  card.scrollIntoView({ behavior: "smooth", block: "center" });
  card.classList.remove("flash");
  // restart the highlight animation on repeated clicks
  void card.offsetWidth;
  card.classList.add("flash");
  return true;
}

export function renderWithCitations(text, anchorPrefix, onOpenSource) {
  return text.split(CITE_SPLIT).map((part, index) => {
    const match = CITE_MATCH.exec(part);
    if (match) {
      const marker = Number(match[1]);
      return (
        <button
          key={index}
          type="button"
          className="cite"
          onClick={() => {
            if (jumpToSource(anchorPrefix, marker) || !onOpenSource) return;
            onOpenSource();
            // wait two frames so the drawer has mounted and laid out
            requestAnimationFrame(() =>
              requestAnimationFrame(() => jumpToSource(anchorPrefix, marker))
            );
          }}
          title={`Show source ${marker}`}
          aria-label={`Source ${marker}`}
        >
          {marker}
        </button>
      );
    }
    return <span key={index}>{part}</span>;
  });
}

export default function AnswerPanel({ answer, anchorPrefix, onOpenSource }) {
  return (
    <div className="answer-text">{renderWithCitations(answer.text, anchorPrefix, onOpenSource)}</div>
  );
}
