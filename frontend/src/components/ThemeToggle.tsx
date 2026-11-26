import { useEffect, useState } from "react";

import { Icon, type IconName } from "./Icon";

type ThemePreference = "system" | "light" | "dark";

const STORAGE_KEY = "stegoshield-theme";
const ORDER: ThemePreference[] = ["system", "light", "dark"];
const ICONS: Record<ThemePreference, IconName> = { system: "monitor", light: "sun", dark: "moon" };
const LABELS: Record<ThemePreference, string> = { system: "System", light: "Light", dark: "Dark" };

function readStoredPreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

function storePreference(preference: ThemePreference): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, preference);
  } catch {
    // Storage blocked (private mode, policy): the choice simply won't persist.
  }
}

export function ThemeToggle() {
  const [preference, setPreference] = useState<ThemePreference>(readStoredPreference);

  useEffect(() => {
    const root = document.documentElement;
    if (preference === "system") delete root.dataset.theme;
    else root.dataset.theme = preference;
    storePreference(preference);
  }, [preference]);

  const next = ORDER[(ORDER.indexOf(preference) + 1) % ORDER.length] ?? "system";
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => setPreference(next)}
      aria-label={`Colour theme: ${LABELS[preference]}. Switch to ${LABELS[next]}.`}
    >
      <Icon name={ICONS[preference]} size={18} />
      <span>{LABELS[preference]} theme</span>
    </button>
  );
}
