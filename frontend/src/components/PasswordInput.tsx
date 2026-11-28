import { type KeyboardEvent, useState } from "react";

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
  const [isCapsLockOn, setIsCapsLockOn] = useState(false);

  // A wrong password only shows up later as "no message found", so warn while the user is still typing.
  function trackCapsLock(event: KeyboardEvent<HTMLInputElement>) {
    setIsCapsLockOn(event.getModifierState("CapsLock"));
  }

  return (
    <>
      <div className="input-group">
        <input
          id={id}
          className="input"
          type={isVisible ? "text" : "password"}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={trackCapsLock}
          onKeyUp={trackCapsLock}
          onBlur={() => setIsCapsLockOn(false)}
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
          <Icon name={isVisible ? "eyeOff" : "eye"} />
        </button>
      </div>
      <p className="caps-lock-note" role="status">
        {isCapsLockOn && (
          <>
            <Icon name="alert" size={14} />
            Caps Lock is on
          </>
        )}
      </p>
    </>
  );
}
