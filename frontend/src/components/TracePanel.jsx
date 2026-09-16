const TIMING_LABELS = [
  ["retrieve_ms", "retrieve"],
  ["assemble_ms", "assemble"],
  ["synthesize_ms", "write"],
  ["verify_ms", "verify"],
  ["total_ms", "total"],
];

export default function TracePanel({ steps, timings, subQuestions = [], branches = [] }) {
  const multiBranch = branches.length > 1;
  return (
    <section className="card trace">
      <h2 className="card-label">Agent steps</h2>

      {multiBranch && (
        <ol className="branch-list">
          {branches.map((branch, index) => (
            <li key={branch.index ?? index}>
              <span className="branch-tag">part {(branch.index ?? index) + 1}</span>
              <span className="branch-q">{branch.question || subQuestions[index]}</span>
              <span className="muted small">
                {branch.error ? branch.error : `${branch.evidence_count} passages`}
              </span>
            </li>
          ))}
        </ol>
      )}

      <ol className="steps">
        {steps.map((step, index) => (
          <li key={`${step.branch ?? 0}-${step.step}-${index}`}>
            <div className="step-head">
              {multiBranch && <span className="branch-tag">part {(step.branch ?? 0) + 1}</span>}
              <span className="step-no">{step.step}</span>
              <span className={`action a-${step.action}`}>{step.action}</span>
              {step.action_input && Object.keys(step.action_input).length > 0 && (
                <code className="step-input">{JSON.stringify(step.action_input)}</code>
              )}
            </div>
            {step.thought && <p className="thought">{step.thought}</p>}
            {step.observation && <p className="observation">{step.observation}</p>}
          </li>
        ))}
      </ol>

      <div className="timings">
        {TIMING_LABELS.map(([key, label]) => (
          <span key={key} className={`timing ${key === "total_ms" ? "is-total" : ""}`}>
            {label} <b>{timings[key] ?? 0} ms</b>
          </span>
        ))}
      </div>
    </section>
  );
}
