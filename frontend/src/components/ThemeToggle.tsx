import { useEffect, useState } from "react";

import { Icon, type IconName } from "./Icon";

type ThemePreference = "system" | "light" | "dark";

const STORAGE_KEY = "stegoshield-theme";
const OPTIONS: { value: ThemePreference; label: string; icon: IconName }[] = [
  { value: "system", label: "System theme", icon: "monitor" },
  { value: "light", label: "Light theme", icon: "sun" },
  { value: "dark", label: "Dark theme", icon: "moon" },
];

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

/** Three-way switch (system / light / dark) built from native radio buttons. */
export function ThemeSwitcher() {
  const [preference, setPreference] = useState<ThemePreference>(readStoredPreference);

  useEffect(() => {
    const root = document.documentElement;
    if (preference === "system") delete root.dataset.theme;
    else root.dataset.theme = preference;
    storePreference(preference);
  }, [preference]);

  return (
    <fieldset className="theme-switcher">
      <legend className="visually-hidden">Colour theme</legend>
      {OPTIONS.map((option) => (
        <label key={option.value} className="theme-switcher__option" title={option.label}>
          <input
            type="radio"
            name="theme"
            value={option.value}
            checked={preference === option.value}
            onChange={() => setPreference(option.value)}
          />
          <Icon name={option.icon} />
          <span className="visually-hidden">{option.label}</span>
        </label>
      ))}
    </fieldset>
  );
}
