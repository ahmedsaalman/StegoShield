import type { ReactNode } from "react";

interface FieldProps {
  id: string;
  label: string;
  hint?: ReactNode;
  error?: string | null;
  optional?: boolean;
  children: (describedBy: string | undefined) => ReactNode;
}

/** Label, hint and error wired to one control through aria-describedby. */
export function Field({ id, label, hint, error, optional = false, children }: FieldProps) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={error ? "field field--invalid" : "field"}>
      <label className="field__label" htmlFor={id}>
        {label}
        {optional && <span className="field__optional"> (optional)</span>}
      </label>
      {hint && (
        <p className="field__hint" id={hintId}>
          {hint}
        </p>
      )}
      {children(describedBy)}
      {error && (
        <p className="field__error" id={errorId}>
          {error}
        </p>
      )}
    </div>
  );
}
