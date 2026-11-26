import { useInView } from "../../lib/motion";

// Diagrams for the "How it works" steps; they draw themselves when scrolled into view.

export type StepArtName = "encrypt" | "scatter" | "verify";

const CIPHER_BLOCKS = Array.from({ length: 12 }, (_, index) => ({ x: 112 + (index % 4) * 16, y: 22 + Math.floor(index / 4) * 16 }));
const SCATTER_CELLS = Array.from({ length: 14 * 5 }, (_, index) => ({ x: 14 + (index % 14) * 13, y: 12 + Math.floor(index / 14) * 13 }));
const SCATTER_FILLED = new Set([3, 9, 16, 22, 27, 33, 38, 44, 51, 57, 62, 68]);

export function StepArt({ name }: { name: StepArtName }) {
  const [ref, isInView] = useInView<SVGSVGElement>();
  return (
    <svg
      ref={ref}
      className={isInView ? `step-art step-art--${name} is-visible` : `step-art step-art--${name}`}
      viewBox="0 0 200 84"
      aria-hidden="true"
      focusable="false"
    >
      {name === "encrypt" && (
        <>
          <g className="draw">
            <path d="M16 28 H68" />
            <path d="M16 42 H60" />
            <path d="M16 56 H52" />
          </g>
          <path className="draw" d="M78 42 H98 M92 36 L98 42 L92 48" />
          {CIPHER_BLOCKS.map((block, index) => (
            <rect
              key={`${block.x}-${block.y}`}
              className="pop"
              x={block.x}
              y={block.y}
              width="11"
              height="11"
              rx="2"
              style={{ transitionDelay: `${300 + index * 45}ms` }}
            />
          ))}
        </>
      )}
      {name === "scatter" &&
        SCATTER_CELLS.map((cell, index) => (
          <rect
            key={`${cell.x}-${cell.y}`}
            className={SCATTER_FILLED.has(index) ? "pop" : "cell"}
            x={cell.x}
            y={cell.y}
            width="9"
            height="9"
            rx="1.5"
            style={SCATTER_FILLED.has(index) ? { transitionDelay: `${index * 18}ms` } : undefined}
          />
        ))}
      {name === "verify" && (
        <>
          <path className="draw" d="M100 10 L128 20 V42 C128 58 116 70 100 75 C84 70 72 58 72 42 V20 Z" />
          <path className="draw draw--late" d="M88 42 L97 51 L113 34" />
        </>
      )}
    </svg>
  );
}
