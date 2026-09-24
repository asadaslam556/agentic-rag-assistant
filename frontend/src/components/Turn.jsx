import { useEffect, useRef, useState } from "react";
import AnswerPanel from "./AnswerPanel.jsx";
import ReasoningPanel from "./ReasoningPanel.jsx";
import { clockTime } from "../sessions.js";
import {
  AlertIcon,
  BulbIcon,
  CheckIcon,
  ChevronIcon,
  CopyIcon,
  DocIcon,
  RobotAvatar,
  UserAvatar,
} from "./Icons.jsx";

const STAGE_LABELS = {
  planning: "Planning the search",
  assembling: "Gathering the evidence",
  synthesizing: "Writing the answer",
  verifying: "Checking every claim",
  refining: "Tightening the answer",
  retrying: "Looking for a missing piece",
};

const ACTION_LABELS = {
  vector_search: "document search",
  web_search: "web search",
  knowledge_base: "catalog lookup",
  sql_query: "database query",
  graph_search: "graph search",
  visual_search: "page image search",
  calculator: "calculator",
  finish: "done",
};

function StageLine({ stage, steps, multiBranch }) {
  return (
    <div className="stage-line">
      <span className="typing" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span className="stage-name">{STAGE_LABELS[stage] || stage}</span>
      {steps.length > 0 && (
        <span className="step-trail">
          {steps.map((step, index) => (
            <span key={`${step.branch ?? 0}-${step.step}-${index}`} className={`step-mini a-${step.action}`}>
              {multiBranch && <b>{(step.branch ?? 0) + 1}</b>}
              {ACTION_LABELS[step.action] || step.action}
            </span>
          ))}
        </span>
      )}
    </div>
  );
}

// "Verified 80%" next to a claim the verifier rejected reads as a
// contradiction. Say how many claims held up instead, and keep the green
// only for answers the backend actually passed.
function VerdictChip({ verification, onClick }) {
  const passed = verification.passed;
  const verdicts = verification.verdicts || [];
  const supported = verdicts.filter((verdict) => verdict.supported).length;
  const allSupported = verdicts.length > 0 && supported === verdicts.length;
  let label;
  if (!verdicts.length) label = passed ? "Verified" : "Needs review";
  else if (allSupported) label = "Verified";
  else label = `${supported} of ${verdicts.length} claims verified`;

  return (
    <button
      type="button"
      className={`verdict ${passed ? "ok" : "warn"}`}
      onClick={onClick}
      title="Open the verification report"
    >
      {passed ? <CheckIcon size={14} /> : <AlertIcon size={14} />}
      {label}
    </button>
  );
}

function formatDuration(ms) {
  if (ms == null) return "";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export default function Turn({ turn, onOpenDetail }) {
  const [copied, setCopied] = useState(false);
  const [showReasoning, setShowReasoning] = useState(false);
  const timer = useRef(null);
  const answer = turn.answer;
  const multiBranch = (turn.subQuestions || []).length > 1;
  const openDetail = () => onOpenDetail(turn.id);
  const reasoningId = `reasoning-${turn.id}`;

  useEffect(() => () => clearTimeout(timer.current), []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(answer.text);
      setCopied(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  const sourceCount = answer ? answer.citations.length : 0;
  const stepCount = answer ? (answer.steps || []).filter((step) => step.action !== "finish").length : 0;

  return (
    <article className="turn">
      <div className="row user">
        <div className="user-column">
          <div className="bubble user-bubble">
            <p>{turn.question}</p>
          </div>
          <span className="stamp">{clockTime(turn.id)}</span>
        </div>
        <UserAvatar />
      </div>

      <div className="row assistant">
        <div className="avatar" aria-hidden="true">
          <RobotAvatar size={32} />
        </div>

        <div className="assistant-body">
          {turn.rewritten && (
            <div className="interp">
              Searched for: <span>{turn.rewritten}</span>
            </div>
          )}

          {multiBranch && (
            <div className="split">
              <span className="split-label">Split into {turn.subQuestions.length} parts</span>
              {turn.subQuestions.map((question, index) => (
                <span key={question} className="split-part">
                  <b>{index + 1}</b> {question}
                </span>
              ))}
            </div>
          )}

          {turn.status === "streaming" && (
            <div className="bubble bot-bubble live" aria-live="polite">
              <StageLine stage={turn.stage} steps={turn.liveSteps} multiBranch={multiBranch} />
              {turn.liveText && <div className="answer-text live">{turn.liveText}</div>}
            </div>
          )}

          {turn.status === "error" && (
            <div className="bubble bot-bubble error" role="alert">
              <AlertIcon size={16} />
              <p>{turn.errorMessage}</p>
            </div>
          )}

          {turn.status === "done" && answer && (
            <div className="bubble bot-bubble">
              <AnswerPanel answer={answer} anchorPrefix={`turn-${turn.id}`} onOpenSource={openDetail} />
              {showReasoning && <ReasoningPanel answer={answer} id={reasoningId} />}
              <div className="bubble-tools">
                <VerdictChip verification={answer.verification} onClick={openDetail} />
                {stepCount > 0 && (
                  <button
                    type="button"
                    className={`tool-btn ${showReasoning ? "is-on" : ""}`}
                    onClick={() => setShowReasoning((value) => !value)}
                    aria-expanded={showReasoning}
                    aria-controls={reasoningId}
                    title={showReasoning ? "Hide the steps behind this answer" : "Show the steps behind this answer"}
                  >
                    <BulbIcon size={15} />
                    Reasoning
                    <ChevronIcon size={14} className={`chevron ${showReasoning ? "is-open" : ""}`} />
                  </button>
                )}
                <button type="button" className="tool-btn" onClick={openDetail}>
                  <DocIcon size={15} />
                  {sourceCount === 0 ? "Details" : `${sourceCount} ${sourceCount === 1 ? "source" : "sources"}`}
                </button>
                <button type="button" className="tool-btn" onClick={copy} aria-live="polite">
                  {copied ? <CheckIcon size={15} /> : <CopyIcon size={15} />}
                  {copied ? "Copied" : "Copy"}
                </button>
                <span className="stamp" title="Total time for this answer">
                  {formatDuration(answer.timings_ms.total_ms)}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </article>
  );
}
