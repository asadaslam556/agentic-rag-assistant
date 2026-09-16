// Theme handling. Follows the operating system by default and remembers a
// manual choice. The document carries data-theme, everything else is CSS.

const KEY = "arag.theme";

export function readStoredTheme() {
  try {
    const saved = localStorage.getItem(KEY);
    return saved === "light" || saved === "dark" ? saved : "system";
  } catch {
    return "system";
  }
}

export function systemTheme() {
  if (typeof window === "undefined" || !window.matchMedia) return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function resolveTheme(choice) {
  return choice === "system" ? systemTheme() : choice;
}

export function applyTheme(choice) {
  const resolved = resolveTheme(choice);
  document.documentElement.setAttribute("data-theme", resolved);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", resolved === "dark" ? "#111615" : "#0B6E5E");
  try {
    if (choice === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, choice);
  } catch {
    // private browsing, or storage is full: the theme still applies for this session
  }
  return resolved;
}

export function watchSystemTheme(onChange) {
  if (typeof window === "undefined" || !window.matchMedia) return () => {};
  const query = window.matchMedia("(prefers-color-scheme: dark)");
  const handler = () => onChange();
  query.addEventListener("change", handler);
  return () => query.removeEventListener("change", handler);
}
