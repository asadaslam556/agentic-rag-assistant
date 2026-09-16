// Chat sessions kept in the browser. Nothing goes to a server, which suits a
// local-first tool: clearing site data clears the history.
//
// Answers carry their evidence, so a long history can outgrow the storage
// quota. Sessions are capped and trimmed oldest-first, and every write is
// guarded because localStorage throws when it is full or blocked.

const KEY = "arag.sessions.v1";
const MAX_SESSIONS = 20;
const MAX_TURNS_PER_SESSION = 40;

export function newSession(title = "New chat") {
  return {
    id: `s-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    title,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    turns: [],
  };
}

export function loadSessions() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((session) => session && session.id && Array.isArray(session.turns))
      .map((session) => ({
        ...session,
        // a tab closed mid-answer can leave a turn marked streaming, and on
        // reload that would keep the composer disabled with nothing running
        turns: session.turns.map((turn) =>
          turn.status === "streaming"
            ? { ...turn, status: "error", errorMessage: "This answer was interrupted." }
            : turn
        ),
      }));
  } catch {
    return [];
  }
}

export function saveSessions(sessions) {
  const trimmed = sessions
    .slice(0, MAX_SESSIONS)
    .map((session) => ({ ...session, turns: session.turns.slice(-MAX_TURNS_PER_SESSION) }));
  try {
    localStorage.setItem(KEY, JSON.stringify(trimmed));
    return true;
  } catch {
    // over quota: drop the oldest half and try once more before giving up
    try {
      const half = trimmed.slice(0, Math.max(1, Math.floor(trimmed.length / 2)));
      localStorage.setItem(KEY, JSON.stringify(half));
      return true;
    } catch {
      return false;
    }
  }
}

export function titleFromQuestion(question) {
  const clean = question.trim().replace(/\s+/g, " ");
  return clean.length > 48 ? `${clean.slice(0, 45)}...` : clean;
}

export function relativeTime(timestamp) {
  const seconds = Math.round((Date.now() - timestamp) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(timestamp).toLocaleDateString();
}

export function clockTime(timestamp) {
  return new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
