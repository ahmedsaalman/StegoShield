import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";

import { type ApiError, api, isAbortError, type Meta, toApiError } from "../lib/api";

export interface SavedPublicKey {
  publicKeyBase64: string;
  fingerprint: string;
}

interface AppState {
  meta: Meta | null;
  metaError: ApiError | null;
  recipientKey: SavedPublicKey | null;
  setRecipientKey: (key: SavedPublicKey | null) => void;
  /** A cover chosen on one page and handed to another (pre-flight → hide). Held in memory only. */
  handoffCover: File | null;
  setHandoffCover: (file: File | null) => void;
}

const AppStateContext = createContext<AppState | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState<ApiError | null>(null);
  const [recipientKey, setRecipientKey] = useState<SavedPublicKey | null>(null);
  const [handoffCover, setHandoffCover] = useState<File | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .meta(controller.signal)
      .then(setMeta)
      .catch((error: unknown) => {
        if (!isAbortError(error)) setMetaError(toApiError(error));
      });
    return () => controller.abort();
  }, []);

  const value = useMemo(
    () => ({ meta, metaError, recipientKey, setRecipientKey, handoffCover, setHandoffCover }),
    [meta, metaError, recipientKey, handoffCover],
  );
  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState(): AppState {
  const state = useContext(AppStateContext);
  if (!state) throw new Error("useAppState must be used inside <AppStateProvider>.");
  return state;
}
