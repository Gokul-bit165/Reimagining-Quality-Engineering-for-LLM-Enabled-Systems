import { useCallback, useEffect, useRef, useState } from 'react';

export interface PollState<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  reload: () => void;
}

/**
 * Fetch once, then re-fetch every `intervalMs` while `shouldPoll(data)` is true.
 * Errors stop polling but keep the last good data.
 */
export function usePoll<T>(
  fetcher: () => Promise<T>,
  shouldPoll: (data: T) => boolean,
  deps: unknown[],
  intervalMs = 1500,
): PollState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const fetchRef = useRef(fetcher);
  const pollRef = useRef(shouldPoll);
  fetchRef.current = fetcher;
  pollRef.current = shouldPoll;

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setLoading(true);
    const run = async () => {
      try {
        const next = await fetchRef.current();
        if (cancelled) return;
        setData(next);
        setError(null);
        setLoading(false);
        if (pollRef.current(next)) timer = setTimeout(run, intervalMs);
      } catch (err) {
        if (cancelled) return;
        setError(err);
        setLoading(false);
      }
    };
    void run();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, intervalMs]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}
