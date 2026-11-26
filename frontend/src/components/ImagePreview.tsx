import type { CSSProperties, ReactNode } from "react";

import { scatteredCells } from "../lib/scatter";
import { BlobImage } from "./BlobImage";
import { Button } from "./Button";
import { describeFile } from "./FileDrop";

/** What the server is currently doing with this image, shown as an overlay animation. */
export type ImageActivity = "embedding" | "scanning";

const OVERLAY_COLUMNS = 12;
const OVERLAY_ROWS = 8;
const EMBED_CELLS = scatteredCells(26, OVERLAY_COLUMNS, OVERLAY_ROWS, 7);
const EMBED_DELAY_STEP_MS = 70;

interface ImagePreviewProps {
  file: File;
  alt: string;
  details?: ReactNode;
  onRemove: () => void;
  removeLabel?: string;
  activity?: ImageActivity | null;
}

/** The chosen image with its name, size and a way to start over. */
export function ImagePreview({
  file,
  alt,
  details,
  onRemove,
  removeLabel = "Choose another image",
  activity = null,
}: ImagePreviewProps) {
  return (
    <div className="image-preview">
      <div className="image-frame image-frame--overlay">
        <BlobImage blob={file} alt={alt} />
        {activity && <ActivityOverlay activity={activity} />}
      </div>
      <div className="image-preview__meta">
        <p className="image-preview__name">{describeFile(file)}</p>
        {details}
        <Button variant="ghost" icon="close" onClick={onRemove} disabled={activity !== null}>
          {removeLabel}
        </Button>
      </div>
    </div>
  );
}

function ActivityOverlay({ activity }: { activity: ImageActivity }) {
  if (activity === "scanning") {
    return <span className="activity activity--scanning" aria-hidden="true" />;
  }
  return (
    <span
      className="activity activity--embedding"
      aria-hidden="true"
      style={{ "--columns": OVERLAY_COLUMNS, "--rows": OVERLAY_ROWS } as CSSProperties}
    >
      {EMBED_CELLS.map((cell, index) => (
        <span
          key={`${cell.column}:${cell.row}`}
          className="activity__bit"
          style={{ gridColumn: cell.column + 1, gridRow: cell.row + 1, animationDelay: `${index * EMBED_DELAY_STEP_MS}ms` }}
        />
      ))}
    </span>
  );
}
