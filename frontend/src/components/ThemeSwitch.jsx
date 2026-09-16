import { MonitorIcon, MoonIcon, SunIcon } from "./Icons.jsx";

const OPTIONS = [
  { value: "light", label: "Light", Icon: SunIcon },
  { value: "dark", label: "Dark", Icon: MoonIcon },
  { value: "system", label: "Auto", Icon: MonitorIcon },
];

// Three-way segmented control. "Auto" follows the operating system and is
// stored as "system" so theme.js keeps working unchanged.
export default function ThemeSwitch({ value, onChange }) {
  const move = (event) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const index = OPTIONS.findIndex((option) => option.value === value);
    const step = event.key === "ArrowRight" ? 1 : -1;
    const next = OPTIONS[(index + step + OPTIONS.length) % OPTIONS.length];
    onChange(next.value);
    const buttons = event.currentTarget.querySelectorAll("button");
    buttons[OPTIONS.indexOf(next)]?.focus();
  };

  return (
    <div className="theme-switch" role="radiogroup" aria-label="Theme" onKeyDown={move}>
      {OPTIONS.map(({ value: option, label, Icon }) => {
        const active = option === value;
        return (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={active}
            tabIndex={active ? 0 : -1}
            className={active ? "is-active" : ""}
            onClick={() => onChange(option)}
            title={option === "system" ? "Match the system setting" : `${label} theme`}
          >
            <Icon size={15} />
            <span className="theme-label">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
