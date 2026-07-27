import { useEffect, useRef, useState } from "react";

/**
 * Tracks whole seconds elapsed while `active` is true, resetting to 0 each time
 * a new busy period starts. Used to drive "elapsed Ns" busy-state copy.
 */
export function useElapsedSeconds(active: boolean): number {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    if (!active) {
      startRef.current = null;
      setElapsed(0);
      return;
    }
    startRef.current = Date.now();
    setElapsed(0);
    const interval = window.setInterval(() => {
      const start = startRef.current;
      if (start === null) return;
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 250);
    return () => window.clearInterval(interval);
  }, [active]);

  return elapsed;
}
