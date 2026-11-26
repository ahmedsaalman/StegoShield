import { useState } from "react";

import { Icon } from "./Icon";

interface PasswordInputProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  describedBy?: string | undefined;
  isInvalid?: boolean;
  autoComplete: "new-password" | "current-password" | "off";
}

export function PasswordInput({ id, value, onChange, describedBy, isInvalid = false, autoComplete }: PasswordInputProps) {
  const [isVisible, setIsVisible] = useState(false);
  return (
    <div className="input-group">
      <input
        id={id}
        className="input"
        type={isVisible ? "text" : "password"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-describedby={describedBy}
        aria-invalid={isInvalid || undefined}
        autoComplete={autoComplete}
        spellCheck={false}
        autoCapitalize="off"
      />
      <button
        type="button"
        className="input-group__button"
        onClick={() => setIsVisible((visible) => !visible)}
        aria-pressed={isVisible}
        aria-label={isVisible ? "Hide password" : "Show password"}
      >
        <Icon name={isVisible ? "eyeOff" : "eye"} size={18} />
      </button>
    </div>
  );
}
