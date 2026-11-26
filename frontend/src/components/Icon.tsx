// Small inline icon set (24×24, stroke-based). Icons are decorative: the text next to them
// always carries the meaning, so they are hidden from screen readers.

const PATHS = {
  shield: "M12 3 4.5 6v6c0 4.6 3.2 8.4 7.5 9.5 4.3-1.1 7.5-4.9 7.5-9.5V6z",
  hide: "M3 3l18 18M10.6 6.1A9.7 9.7 0 0 1 12 6c5 0 8.5 4.2 9.5 6-.5.9-1.5 2.4-3 3.7M6.6 7.6C4.7 8.9 3.3 10.7 2.5 12c1 1.8 4.5 6 9.5 6 1.5 0 2.9-.4 4.1-1M9.9 10a3 3 0 0 0 4.2 4.2",
  reveal: "M2.5 12C3.5 10.2 7 6 12 6s8.5 4.2 9.5 6c-1 1.8-4.5 6-9.5 6s-8.5-4.2-9.5-6zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  gauge: "M4.5 18a8.5 8.5 0 1 1 15 0M12 13l4-4M12 14a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  scan: "M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M8 12h8",
  key: "M14.5 9.5a4 4 0 1 1-1.2-2.8M13.3 6.7 20 13.4M17 10.4l2-2M15 12.4l1.5 1.5M10.5 13.5a1 1 0 1 1 0-2",
  upload: "M12 15V4M7.5 8.5 12 4l4.5 4.5M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4",
  download: "M12 4v11M7.5 10.5 12 15l4.5-4.5M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4",
  copy: "M9 9h10v11H9zM5 15V4h10",
  check: "M5 12.5 10 17.5 19 7",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v6M12 7.5v.5",
  alert: "M12 4 2.8 19.5h18.4zM12 10v4.5M12 17v.5",
  x: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9 9l6 6M15 9l-6 6",
  close: "M6 6l12 12M18 6 6 18",
  image: "M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M15.5 9.5a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  file: "M6 3h8l4 4v14H6zM14 3v4h4",
  lock: "M6 11h12v9H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3",
  sun: "M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  moon: "M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z",
  monitor: "M3 5h18v11H3zM8 20h8M12 16v4",
  menu: "M4 7h16M4 12h16M4 17h16",
  arrowRight: "M5 12h14M13 6l6 6-6 6",
  eye: "M2.5 12C3.5 10.2 7 6 12 6s8.5 4.2 9.5 6c-1 1.8-4.5 6-9.5 6s-8.5-4.2-9.5-6zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  eyeOff: "M3 3l18 18M10.6 6.1A9.7 9.7 0 0 1 12 6c5 0 8.5 4.2 9.5 6-.5.9-1.5 2.4-3 3.7M6.6 7.6C4.7 8.9 3.3 10.7 2.5 12c1 1.8 4.5 6 9.5 6 1.5 0 2.9-.4 4.1-1",
  trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
} as const;

export type IconName = keyof typeof PATHS;

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
}

export function Icon({ name, size = 16, className }: IconProps) {
  return (
    <svg
      className={className ? `icon ${className}` : "icon"}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
