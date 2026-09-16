function Gauge({ label, value }) {
  const pct = Math.round(value * 100);
  const tone = pct >= 70 ? "" : pct >= 40 ? "warn" : "bad";
  return (
    <div className="gauge">
      <div className="gauge-top">
        <span>{label}</span>
        <span className="gauge-value">{pct}%</span>
      </div>
      <div
        className="gauge-track"
        role="meter"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuenow={pct}
        aria-label={label}
      >
        <div className={`gauge-fill ${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// Claims arrive with their [n] markers stripped, which leaves "instantly ."
// behind. Close that gap for display.
function tidyClaim(text) {
  return text.replace(/\s+([.,;:!?])/g, "$1").trim();
}

const METHOD_LABELS = {
  lexical: "word overlap check",
  llm: "model check",
};

export default function VerificationStrip({ verification, attempts }) {
  const passed = verification.passed;
  return (
    <section className={`card strip ${passed ? "is-ok" : "is-warn"}`}>
      <h2 className="card-label">Verification</h2>
      <div className="strip-head">
        <span className={`stamp-badge ${passed ? "ok" : "bad"}`}>{passed ? "Passed" : "Needs review"}</span>
        <span className="muted small">
          {METHOD_LABELS[verification.method] || verification.method}
          {attempts > 0 ? `, revised ${attempts} ${attempts === 1 ? "time" : "times"}` : ""}
        </span>
      </div>
      <div className="gauges">
        <Gauge label="Claims supported" value={verification.groundedness} />
        <Gauge label="Claims with a citation" value={verification.citation_coverage} />
      </div>
      {verification.verdicts.length > 0 && (
        <ul className="claims">
          {verification.verdicts.map((verdict, index) => (
            <li key={index} className={verdict.supported ? "ok" : "bad"}>
              <span className={`lamp ${verdict.supported ? "" : "bad"}`} aria-hidden="true" />
              <div className="claim-body">
                <span className="claim-text">
                  {tidyClaim(verdict.claim)}
                  {verdict.cited_markers.length > 0 && (
                    <span className="claim-cites"> [{verdict.cited_markers.join("][")}]</span>
                  )}
                </span>
                <span className="sr-only">{verdict.supported ? "Supported." : "Not supported."}</span>
                {verdict.note && <span className="claim-note">{verdict.note}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
