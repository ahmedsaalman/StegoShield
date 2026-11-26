import { useCallback, useEffect, useState } from "react";

import { useAppState } from "../state/AppState";
import { api, type Capacity } from "./api";
import { formatBytes } from "./format";
import { type RequestState, useRequest } from "./useRequest";

const COVER_TYPES = new Set(["image/png", "image/jpeg", "image/bmp", "image/webp"]);
export const COVER_ACCEPT = "image/png,image/jpeg,image/bmp,image/webp";

export interface CoverImage {
  file: File | null;
  fileError: string | null;
  capacity: RequestState<Capacity>;
  choose: (file: File) => void;
  clear: () => void;
}

/** A chosen cover image, checked in the browser first and then measured by the server. */
export function useCoverImage(initialFile: File | null = null): CoverImage {
  const { meta } = useAppState();
  const [file, setFile] = useState<File | null>(initialFile);
  const [fileError, setFileError] = useState<string | null>(null);
  const capacityRequest = useRequest<Capacity>();
  const { run, reset } = capacityRequest;

  useEffect(() => {
    if (file) void run((signal) => api.capacity(file, signal));
    else reset();
  }, [file, run, reset]);

  const choose = useCallback(
    (candidate: File) => {
      const problem = describeCoverProblem(candidate, meta?.limits.max_upload_bytes);
      setFileError(problem);
      setFile(problem ? null : candidate);
    },
    [meta],
  );

  const clear = useCallback(() => {
    setFile(null);
    setFileError(null);
  }, []);

  return { file, fileError, capacity: capacityRequest.state, choose, clear };
}

function describeCoverProblem(file: File, maxBytes: number | undefined): string | null {
  if (!COVER_TYPES.has(file.type)) return "Choose a PNG, JPEG, BMP or WebP image.";
  if (maxBytes !== undefined && file.size > maxBytes) {
    return `This file is ${formatBytes(file.size)}; the limit is ${formatBytes(maxBytes)}.`;
  }
  return null;
}
