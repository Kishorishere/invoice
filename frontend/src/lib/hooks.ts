import { useEffect, useState } from "react";

/**
 * Returns `value` only after it has been stable for `delay` ms.
 * Trailing-edge debounce: good for search inputs.
 */
export function useDebouncedValue<T>(value: T, delay = 180): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(t);
  }, [value, delay]);

  return debounced;
}
