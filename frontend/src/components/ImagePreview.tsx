import type { ReactNode } from "react";

import { BlobImage } from "./BlobImage";
import { Button } from "./Button";
import { describeFile } from "./FileDrop";

interface ImagePreviewProps {
  file: File;
  alt: string;
  details?: ReactNode;
  onRemove: () => void;
  removeLabel?: string;
}

/** The chosen image with its name, size and a way to start over. */
export function ImagePreview({ file, alt, details, onRemove, removeLabel = "Choose another image" }: ImagePreviewProps) {
  return (
    <div className="image-preview">
      <div className="image-preview__frame">
        <BlobImage blob={file} alt={alt} />
      </div>
      <div className="image-preview__meta">
        <p className="image-preview__name">{describeFile(file)}</p>
        {details}
        <Button variant="ghost" icon="close" onClick={onRemove}>
          {removeLabel}
        </Button>
      </div>
    </div>
  );
}
