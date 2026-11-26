import { type DragEvent, useId, useRef, useState } from "react";

import { formatBytes } from "../lib/format";
import { Icon, type IconName } from "./Icon";

interface FileDropProps {
  label: string;
  hint: string;
  accept: string;
  icon?: IconName;
  onFile: (file: File) => void;
  error?: string | null;
}

/**
 * A real <input type="file"> (so keyboard and screen readers work normally) with a larger,
 * drag-and-drop-friendly label around it.
 */
export function FileDrop({ label, hint, accept, icon = "upload", onFile, error }: FileDropProps) {
  const inputId = useId();
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  function handleDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setIsDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) onFile(file);
  }

  function handleDragOver(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setIsDragging(true);
  }

  const classes = ["file-drop", isDragging && "file-drop--active", error && "file-drop--invalid"]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="field">
      {/* Drag-and-drop is a pointer-only shortcut; the file input inside is the accessible control. */}
      {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions */}
      <div className={classes} onDrop={handleDrop} onDragOver={handleDragOver} onDragLeave={() => setIsDragging(false)}>
        <input
          ref={inputRef}
          id={inputId}
          className="visually-hidden file-drop__input"
          type="file"
          accept={accept}
          aria-describedby={error ? `${hintId} ${errorId}` : hintId}
          aria-invalid={error ? true : undefined}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onFile(file);
            event.target.value = "";
          }}
        />
        <label htmlFor={inputId} className="file-drop__label">
          <span className="file-drop__icon" aria-hidden="true">
            <Icon name={icon} size={18} />
          </span>
          <span className="file-drop__title">{label}</span>
          <span className="file-drop__hint" id={hintId}>
            {hint}
          </span>
        </label>
      </div>
      {error && (
        <p className="field__error" id={errorId} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function describeFile(file: File): string {
  return `${file.name} · ${formatBytes(file.size)}`;
}
