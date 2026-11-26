export interface GridCell {
  column: number;
  row: number;
}

/**
 * Deterministic pseudo-random cells in a grid (a tiny LCG), so decorative "scattered bits"
 * look the same on every render. Not for anything security-related.
 */
export function scatteredCells(count: number, columns: number, rows: number, seed: number): GridCell[] {
  let state = seed;
  const next = () => {
    state = (state * 1103515245 + 12345) % 2147483648;
    return state / 2147483648;
  };
  const target = Math.min(count, columns * rows);
  const taken = new Set<string>();
  const cells: GridCell[] = [];
  while (cells.length < target) {
    const cell = { column: Math.floor(next() * columns), row: Math.floor(next() * rows) };
    const key = `${cell.column}:${cell.row}`;
    if (taken.has(key)) continue;
    taken.add(key);
    cells.push(cell);
  }
  return cells;
}
