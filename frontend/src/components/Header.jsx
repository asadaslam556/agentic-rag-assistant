import { PanelIcon } from "./Icons.jsx";
import StatusMenu from "./StatusMenu.jsx";
import ThemeSwitch from "./ThemeSwitch.jsx";

export default function Header({
  health,
  healthError,
  title,
  turnCount,
  sidebarVisible,
  onToggleSidebar,
  onRetryHealth,
  theme,
  onThemeChange,
}) {
  return (
    <header className="topbar">
      <button
        type="button"
        className="icon-btn"
        onClick={onToggleSidebar}
        title={sidebarVisible ? "Hide conversations" : "Show conversations"}
        aria-label={sidebarVisible ? "Hide conversations" : "Show conversations"}
        aria-expanded={sidebarVisible}
        aria-controls="sidebar"
      >
        <PanelIcon />
      </button>

      <div className="topbar-title">
        <h1 className="title-text">{title}</h1>
        {turnCount > 0 && (
          <span className="title-meta">
            {turnCount} {turnCount === 1 ? "question" : "questions"}
          </span>
        )}
      </div>

      <div className="topbar-actions">
        <StatusMenu health={health} healthError={healthError} onRetry={onRetryHealth} />
        <ThemeSwitch value={theme} onChange={onThemeChange} />
      </div>
    </header>
  );
}
