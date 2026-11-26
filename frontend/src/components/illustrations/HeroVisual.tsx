import type { CSSProperties } from "react";

import { RISK_PRESENTATION } from "../../lib/presentation";
import { scatteredCells } from "../../lib/scatter";
import { Icon } from "../Icon";
import { StatusBadge } from "../StatusBadge";

// A stylised "photo" whose pixels quietly carry encrypted bits, scattered at
// key-derived positions. Purely decorative: hidden from assistive technology.

const GRID_COLUMNS = 16;
const GRID_ROWS = 11;
const BIT_COUNT = 30;
const BIT_DELAY_STEP_MS = 140;

const BIT_CELLS = scatteredCells(BIT_COUNT, GRID_COLUMNS, GRID_ROWS, 2026);

export function HeroVisual() {
  return (
    <div className="hero-visual" aria-hidden="true">
      <div className="hero-visual__photo">
        <svg className="hero-visual__scene" viewBox="0 0 320 220" preserveAspectRatio="xMidYMid slice">
          <rect className="scene-sky" width="320" height="220" />
          <circle className="scene-sun" cx="238" cy="58" r="20" />
          <path className="scene-far" d="M0 148 L56 98 L98 128 L150 72 L206 136 L256 100 L320 142 V220 H0Z" />
          <path className="scene-near" d="M0 176 L44 142 L92 166 L146 124 L204 170 L258 144 L320 178 V220 H0Z" />
          <g className="scene-water">
            <path d="M24 196 H92" />
            <path d="M120 204 H220" />
            <path d="M236 194 H300" />
          </g>
        </svg>
        <div
          className="hero-visual__grid"
          style={{ "--columns": GRID_COLUMNS, "--rows": GRID_ROWS } as CSSProperties}
        >
          {BIT_CELLS.map((cell, index) => (
            <span
              key={`${cell.column}:${cell.row}`}
              className="hero-visual__bit"
              style={{
                gridColumn: cell.column + 1,
                gridRow: cell.row + 1,
                animationDelay: `${index * BIT_DELAY_STEP_MS}ms`,
              }}
            />
          ))}
        </div>
        <div className="hero-visual__scan" />
      </div>

      <div className="hero-visual__chip hero-visual__chip--message">
        <Icon name="lock" />
        <span>meet at the north gate</span>
      </div>
      <div className="hero-visual__chip hero-visual__chip--cipher">
        <span className="hero-visual__cipher">9f2a c41e 07bd 5e93 a1c0 …</span>
      </div>
      <div className="hero-visual__chip hero-visual__chip--risk">
        <StatusBadge status={RISK_PRESENTATION.low} value="12%" />
      </div>
    </div>
  );
}
