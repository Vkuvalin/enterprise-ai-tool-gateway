import { useEffect, useRef, useState } from "react";
import { getCapabilities, getHealth } from "../../api/capabilities";
import { toDisplayError } from "../../api/errors";
import type { CapabilitiesResponse, HealthResponse, NormalizedApiError } from "../../api/types";

export type ApiStatusSnapshot = {
  health: HealthResponse | null;
  capabilities: CapabilitiesResponse | null;
  loading: boolean;
  refreshing: boolean;
  hasLoaded: boolean;
  stale: boolean;
  error: NormalizedApiError | null;
  refresh: () => void;
};

type ApiStatusOptions = {
  onRefreshSuccess?: () => void;
  onRefreshError?: (error: NormalizedApiError) => void;
};

export function useApiStatus(options: ApiStatusOptions = {}): ApiStatusSnapshot {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilitiesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const callbacksRef = useRef(options);

  useEffect(() => {
    callbacksRef.current = options;
  }, [options]);

  useEffect(() => {
    let cancelled = false;
    const hadLoaded = hasLoaded;
    const manualRefresh = refreshToken > 0;
    setLoading(true);
    if (!hadLoaded) {
      setError(null);
      setStale(false);
    }

    Promise.all([getHealth(), getCapabilities()])
      .then(([nextHealth, nextCapabilities]) => {
        if (cancelled) {
          return;
        }
        setHealth(nextHealth);
        setCapabilities(nextCapabilities);
        setHasLoaded(true);
        setError(null);
        setStale(false);
        if (manualRefresh) {
          callbacksRef.current.onRefreshSuccess?.();
        }
      })
      .catch((nextError: unknown) => {
        if (cancelled) {
          return;
        }
        const displayError = toDisplayError(nextError);
        setError(displayError);
        setStale(hadLoaded);
        if (hadLoaded) {
          callbacksRef.current.onRefreshError?.(displayError);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [refreshToken]);

  return {
    health,
    capabilities,
    loading,
    refreshing: loading && hasLoaded,
    hasLoaded,
    stale,
    error,
    refresh: () => setRefreshToken((value) => value + 1)
  };
}
