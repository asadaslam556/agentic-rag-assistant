// Thin client for the FastAPI backend. All paths are relative: the Vite
// dev server proxies /api to localhost:8000, and in production the same
// process serves both the console and the API.

// When the server sets API_AUTH_TOKEN, every call but /api/health needs a
// bearer token. The console asks for it on the first 401 and keeps it in
// this browser only.
const TOKEN_KEY = "rag-api-token";

function readToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

function askForToken() {
  const token = (window.prompt("This server needs an API token (API_AUTH_TOKEN):") || "").trim();
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // storage blocked: the token still works for this request
  }
  return token;
}

function withToken(options = {}, token = readToken()) {
  if (!token) return options;
  return { ...options, headers: { ...(options.headers || {}), Authorization: `Bearer ${token}` } };
}

// fetch with the stored token; on 401 ask once and retry
async function authFetch(path, options) {
  let response = await fetch(path, withToken(options));
  if (response.status === 401) {
    const token = askForToken();
    if (token) response = await fetch(path, withToken(options, token));
  }
  return response;
}

// Page images are protected too, and an <img> cannot send a header, so with
// a token the image is fetched here and handed over as an object URL.
export async function pageImageSrc(url) {
  if (!readToken()) return url;
  const response = await authFetch(url);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return URL.createObjectURL(await response.blob());
}

async function request(path, options) {
  let response;
  try {
    response = await authFetch(path, options);
  } catch {
    throw new Error("Backend not reachable at /api. Start it with: rag serve");
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // keep the status text
    }
    throw new Error(detail);
  }
  return response.json();
}

export const fetchHealth = () => request("/api/health");

export const chat = (question, history) =>
  request("/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ question, history }),
  });

export const ingestSamples = () =>
  request("/api/ingest", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ path: "data/sample_docs" }),
  });

export function uploadFiles(fileList) {
  const form = new FormData();
  for (const file of fileList) form.append("files", file);
  return request("/api/upload", { method: "POST", body: form });
}

// Consume the SSE stream from /api/chat/stream. Calls onEvent(name, payload)
// for every event; resolves when the server sends `done`. Throws before any
// event on network failure so callers can fall back to the non-stream API.
export async function streamChat(question, history, onEvent) {
  const response = await authFetch("/api/chat/stream", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ question, history }),
  });
  if (!response.ok || !response.body) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
      let name = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) name = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      let payload = {};
      try {
        payload = JSON.parse(data);
      } catch {
        continue;
      }
      onEvent(name, payload);
      if (name === "done") return;
    }
  }
}
