import { CalculatorIcon, CheckIcon, GlobeIcon, GraphIcon, SearchIcon, TableIcon } from "./Icons.jsx";

// A short, readable version of the agent trace that opens right under the
// answer. It shows what the agent decided to do and why, one line per step.
// The evidence drawer keeps the full detail (raw inputs, observations,
// timings) for anyone who wants to dig in.

const ACTIONS = {
  vector_search: { label: "Searched the documents", Icon: SearchIcon },
  graph_search: { label: "Walked the knowledge graph", Icon: GraphIcon },
  visual_search: { label: "Searched page images", Icon: SearchIcon },
  web_search: { label: "Searched the web", Icon: GlobeIcon },
  knowledge_base: { label: "Looked up the catalog", Icon: TableIcon },
  sql_query: { label: "Queried the database", Icon: TableIcon },
  calculator: { label: "Calculated", Icon: CalculatorIcon },
  finish: { label: "Ready to answer", Icon: CheckIcon },
};

function inputSummary(input) {
  if (!input) return "";
  const value = input.query ?? input.expression ?? input.question ?? Object.values(input)[0];
  return typeof value === "string" ? value : "";
}

export default function ReasoningPanel({ answer, id }) {
  const steps = answer.steps || [];
  const multiBranch = (answer.branches || []).length > 1;

  return (
    <div className="reasoning" id={id}>
      <ol className="reasoning-steps">
        {steps.map((step, index) => {
          const meta = ACTIONS[step.action] || { label: step.action, Icon: SearchIcon };
          const detail = step.action === "finish" ? "" : inputSummary(step.action_input);
          return (
            <li key={`${step.branch ?? 0}-${step.step}-${index}`}>
              <span className="reasoning-icon">
                <meta.Icon size={14} />
              </span>
              <div className="reasoning-body">
                <div className="reasoning-action">
                  {multiBranch && <span className="branch-tag">part {(step.branch ?? 0) + 1}</span>}
                  {meta.label}
                  {detail && <span className="reasoning-detail">{detail}</span>}
                </div>
                {step.thought && <p className="reasoning-thought">{step.thought}</p>}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
