import { useEffect, useState, useCallback } from "react";
import type { SimulatorState } from "../types";

const API = "/api/state";

export function useSimState() {
  const [state, setState] = useState<SimulatorState | null>(null);

  const fetchState = useCallback(async () => {
    const res = await fetch(API);
    setState(await res.json());
  }, []);

  const update = useCallback(
    async (patch: Partial<SimulatorState>) => {
      const res = await fetch(API, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      setState(await res.json());
    },
    []
  );

  const reset = useCallback(async () => {
    const res = await fetch("/api/state/reset", { method: "POST" });
    setState(await res.json());
  }, []);

  useEffect(() => {
    fetchState();
    const id = setInterval(fetchState, 1000);
    return () => clearInterval(id);
  }, [fetchState]);

  return { state, update, reset };
}
