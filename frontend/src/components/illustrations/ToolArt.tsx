// Small line drawings for the tool pages. On Overview cards they animate on hover/focus of
// the card; in page title bands (`isAmbient`) they loop gently. Decorative only.

export type ToolArtName = "hide" | "reveal" | "preflight" | "detect" | "keys";

const DETECT_DOTS = Array.from({ length: 6 * 4 }, (_, index) => ({
  x: 58 + (index % 6) * 17,
  y: 38 + Math.floor(index / 6) * 15,
}));

function Frame() {
  return (
    <>
      <rect x="40" y="22" width="120" height="76" rx="6" />
      <path className="art-faint" d="M40 82 L72 58 L96 74 L120 52 L160 84" />
    </>
  );
}

interface ToolArtProps {
  name: ToolArtName;
  isAmbient?: boolean;
}

export function ToolArt({ name, isAmbient = false }: ToolArtProps) {
  const className = `tool-art tool-art--${name}${isAmbient ? " tool-art--ambient" : ""}`;
  return (
    <svg className={className} viewBox="0 0 200 120" aria-hidden="true" focusable="false">
      {name === "hide" && (
        <>
          <Frame />
          <g className="art-lock">
            <rect x="86" y="54" width="28" height="22" rx="4" className="art-solid" />
            <path d="M92 54 V47 a8 8 0 0 1 16 0 V54" />
          </g>
        </>
      )}
      {name === "reveal" && (
        <>
          <rect x="22" y="26" width="76" height="68" rx="6" />
          <path className="art-faint" d="M22 80 L44 62 L60 74 L76 58 L98 78" />
          <path className="art-arrow" d="M106 60 H124 M118 54 L124 60 L118 66" />
          <g className="art-lines">
            <path d="M134 44 H180" />
            <path d="M134 60 H172" />
            <path d="M134 76 H160" />
          </g>
        </>
      )}
      {name === "preflight" && (
        <>
          <path d="M52 92 A48 48 0 0 1 148 92" />
          <g className="art-faint">
            <path d="M60 70 L66 74" />
            <path d="M100 46 V53" />
            <path d="M140 70 L134 74" />
          </g>
          <path className="art-needle" d="M100 92 L100 56" />
          <circle cx="100" cy="92" r="4" className="art-solid" />
        </>
      )}
      {name === "detect" && (
        <>
          <rect x="40" y="22" width="120" height="76" rx="6" />
          {DETECT_DOTS.map((dot) => (
            <circle key={`${dot.x}-${dot.y}`} className="art-dot" cx={dot.x} cy={dot.y} r="1.6" />
          ))}
          <g className="art-lens">
            <circle cx="78" cy="56" r="16" />
            <path d="M90 68 L102 80" />
          </g>
        </>
      )}
      {name === "keys" && (
        <>
          <g className="art-key art-key--private">
            <circle cx="62" cy="46" r="15" />
            <circle cx="62" cy="46" r="5" className="art-faint" />
            <path d="M77 46 H146 M128 46 V57 M139 46 V54" />
          </g>
          <g className="art-key art-key--public">
            <circle cx="138" cy="80" r="11" />
            <path d="M127 80 H70 M84 80 V89 M76 80 V86" />
          </g>
        </>
      )}
    </svg>
  );
}
