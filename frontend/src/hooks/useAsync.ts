import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * One request, and the three things a screen needs to know about it.
 *
 * Every panel here asks the backend once and draws what comes back, so they
 * all want the same three answers: is it still coming, what arrived, and what
 * went wrong. Writing that once means no panel invents its own way to be
 * loading.
 */
export interface Async<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  reload: () => void;
}

export function useAsync<T>(
  load: () => Promise<T>,
  deps: readonly unknown[],
  options: { enabled?: boolean } = {},
): Async<T> {
  const enabled = options.enabled ?? true;

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(false);
  const [attempt, setAttempt] = useState(0);

  // A reply that arrives after the question changed is not an answer. Each
  // run takes a number, and only the newest is allowed to set state.
  const current = useRef(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    if (!enabled) return;

    const run = ++current.current;
    setLoading(true);

    loadRef
      .current()
      .then((result) => {
        if (current.current !== run) return;
        setData(result);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (current.current !== run) return;
        setError(cause instanceof Error ? cause : new Error(String(cause)));
      })
      .finally(() => {
        if (current.current === run) setLoading(false);
      });
    // The caller states what this request depends on; `load` is read through
    // a ref so an inline function does not count as a change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, attempt, ...deps]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  return { data, loading, error, reload };
}
