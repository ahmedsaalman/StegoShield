import { useEffect, useRef } from "react";

interface BlobImageProps {
  blob: Blob;
  alt: string;
}

/**
 * Shows an in-memory image through a temporary blob: URL that is revoked when the blob
 * changes or the component unmounts, so previews never leak memory.
 */
export function BlobImage({ blob, alt }: BlobImageProps) {
  const imageRef = useRef<HTMLImageElement>(null);

  useEffect(() => {
    const url = URL.createObjectURL(blob);
    if (imageRef.current) imageRef.current.src = url;
    return () => URL.revokeObjectURL(url);
  }, [blob]);

  return <img ref={imageRef} alt={alt} />;
}
