import type { ButtonHTMLAttributes, ReactNode } from "react";

import { Icon, type IconName } from "./Icon";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: IconName;
  isLoading?: boolean;
  loadingLabel?: string;
  fullWidth?: boolean;
  children: ReactNode;
}

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  isLoading = false,
  loadingLabel,
  fullWidth = false,
  type = "button",
  disabled,
  className,
  children,
  ...rest
}: ButtonProps) {
  const classes = ["btn", `btn--${variant}`, size !== "md" && `btn--${size}`, fullWidth && "btn--full", className].filter(Boolean).join(" ");
  return (
    <button {...rest} type={type} className={classes} disabled={disabled || isLoading} aria-busy={isLoading}>
      {isLoading ? <span className="spinner" aria-hidden="true" /> : icon && <Icon name={icon} />}
      <span>{isLoading && loadingLabel ? loadingLabel : children}</span>
    </button>
  );
}
