import { useEffect, useState } from "react";

/** Fetch a protected binary and expose it as an object URL (revoked on cleanup). */
export function useBlobUrl(load: () => Promise<Blob>): { url: string | null; failed: boolean } {
  const [state, setState] = useState<{ url: string | null; failed: boolean }>({
    url: null,
    failed: false,
  });

  useEffect(() => {
    let cancelled = false;
    let created: string | null = null;
    load().then(
      (blob) => {
        if (cancelled) return;
        created = URL.createObjectURL(blob);
        setState({ url: created, failed: false });
      },
      () => !cancelled && setState({ url: null, failed: true }),
    );
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [load]);

  return state;
}
