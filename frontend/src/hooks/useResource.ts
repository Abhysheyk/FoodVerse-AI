import { useCallback, useEffect, useState } from "react";

interface Settled<T> {
  source: () => Promise<T>;
  nonce: number;
  data: T | null;
  error: unknown;
}

export interface Resource<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  reload: () => void;
}

/**
 * Load data from the API. Pass a fetcher memoised with useCallback; it reruns whenever the
 * fetcher identity changes (e.g. a new page number) or reload() is called.
 * `loading` is derived, so a stale result is never shown for a newer request.
 */
export function useResource<T>(fetcher: () => Promise<T>): Resource<T> {
  const [nonce, setNonce] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetcher().then(
      (data) => !cancelled && setSettled({ source: fetcher, nonce, data, error: null }),
      (error: unknown) => !cancelled && setSettled({ source: fetcher, nonce, data: null, error }),
    );
    return () => {
      cancelled = true;
    };
  }, [fetcher, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const current = settled !== null && settled.source === fetcher && settled.nonce === nonce;
  return {
    data: current ? settled.data : (settled?.data ?? null), // keep old data visible while reloading
    error: current ? settled.error : null,
    loading: !current,
    reload,
  };
}
