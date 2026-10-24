import { ApiError } from "../api/client";

/** Turn any thrown error into a user-facing message without leaking internals. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === "validation_error" && err.details?.length) {
      return err.details.map((d) => `${d.field ? d.field + ": " : ""}${d.message}`).join(" ");
    }
    return err.message;
  }
  return "Could not reach the server. Check your connection and try again.";
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p className="alert error" role="alert">
      {message}
    </p>
  );
}
