import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { setAccessToken, setSessionLostHandler } from "../api/client";
import { unmocked } from "./unmocked";

// jsdom has no object-URL support; protected images are shown through blob URLs.
URL.createObjectURL = vi.fn(() => "blob:test-image");
URL.revokeObjectURL = vi.fn();

afterEach(() => {
  cleanup();
  // A request nobody mocked would silently render as an error state; make it a failure.
  const missed = unmocked.splice(0);
  expect(missed, "API requests made without a mock").toEqual([]);
  setAccessToken(null);
  setSessionLostHandler(null);
  vi.unstubAllGlobals();
});
