import { useCallback } from "react";
import { getMediaBlob } from "../api/endpoints";
import { useBlobUrl } from "../hooks/useBlobUrl";

/** <img> for a protected media file: fetched with the bearer token, shown via an object URL. */
export function AuthImage({ mediaId, alt, className }: { mediaId: string; alt: string; className?: string }) {
  const load = useCallback(() => getMediaBlob(mediaId), [mediaId]);
  const { url, failed } = useBlobUrl(load);
  if (failed) return <div className={`img-fallback ${className ?? ""}`} role="img" aria-label={`${alt} (could not be loaded)`}>Unavailable</div>;
  if (!url) return <div className={`img-skeleton ${className ?? ""}`} aria-hidden="true" />;
  return <img src={url} alt={alt} className={className} loading="lazy" />;
}
