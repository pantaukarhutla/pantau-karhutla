import { useCallback, useState } from "react";

/**
 * State remembered in this browser (localStorage). `parse` turns the stored
 * text back into a value, or null when it is not one; `format` is the inverse.
 * Blocked storage (private mode) or a bad value falls back to `fallback`, and
 * changes then last for this visit only.
 */
export function usePersistentState<T>(
  key: string,
  fallback: T,
  parse: (stored: string) => T | null,
  format: (value: T) => string = JSON.stringify,
): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = localStorage.getItem(key);
      return (stored === null ? null : parse(stored)) ?? fallback;
    } catch {
      return fallback;
    }
  });
  const set = useCallback(
    (v: T) => {
      setValue(v);
      try {
        localStorage.setItem(key, format(v));
      } catch {
        // storage blocked: the choice lasts for this visit
      }
    },
    [key, format],
  );
  return [value, set];
}
