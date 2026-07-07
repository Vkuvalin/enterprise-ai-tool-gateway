import { useSyncExternalStore } from "react";

const KNOWN_RUN_IDS_KEY = "gateway.knownRunIds";
const SELECTED_RUN_ID_KEY = "gateway.selectedRunId";
const CHANGE_EVENT = "gateway-known-runs-changed";

export type KnownRunsSnapshot = {
  knownRunIds: string[];
  selectedRunId: string | null;
};

const SERVER_SNAPSHOT: KnownRunsSnapshot = {
  knownRunIds: [],
  selectedRunId: null
};

let cachedKnownRunIdsRaw: string | null = null;
let cachedSelectedRunIdRaw: string | null = null;
let cachedSnapshot: KnownRunsSnapshot = SERVER_SNAPSHOT;

export function useKnownRuns(): KnownRunsSnapshot {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export function addKnownRunId(runId: string): void {
  if (!runId.trim()) {
    return;
  }
  const current = readKnownRunIds();
  const next = [runId, ...current.filter((id) => id !== runId)].slice(0, 25);
  writeJson(KNOWN_RUN_IDS_KEY, next);
  setSelectedRunId(runId);
  notify();
}

export function removeKnownRunId(runId: string): void {
  const next = readKnownRunIds().filter((id) => id !== runId);
  writeJson(KNOWN_RUN_IDS_KEY, next);
  if (readSelectedRunId() === runId) {
    writeString(SELECTED_RUN_ID_KEY, next[0] ?? null);
  }
  notify();
}

export function setSelectedRunId(runId: string | null): void {
  const normalized = runId && runId.trim() ? runId : null;
  writeString(SELECTED_RUN_ID_KEY, normalized);
  notify();
}

export function clearKnownRuns(): void {
  writeJson(KNOWN_RUN_IDS_KEY, []);
  writeString(SELECTED_RUN_ID_KEY, null);
  notify();
}

function subscribe(callback: () => void): () => void {
  if (typeof window === "undefined") {
    return () => undefined;
  }

  const onStorage = (event: StorageEvent) => {
    if (event.key === KNOWN_RUN_IDS_KEY || event.key === SELECTED_RUN_ID_KEY) {
      callback();
    }
  };
  const onCustom = () => callback();

  window.addEventListener("storage", onStorage);
  window.addEventListener(CHANGE_EVENT, onCustom);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(CHANGE_EVENT, onCustom);
  };
}

function getSnapshot(): KnownRunsSnapshot {
  if (typeof window === "undefined") {
    return SERVER_SNAPSHOT;
  }

  const knownRunIdsRaw = window.localStorage.getItem(KNOWN_RUN_IDS_KEY);
  const selectedRunIdRaw = window.localStorage.getItem(SELECTED_RUN_ID_KEY);
  if (knownRunIdsRaw === cachedKnownRunIdsRaw && selectedRunIdRaw === cachedSelectedRunIdRaw) {
    return cachedSnapshot;
  }

  cachedKnownRunIdsRaw = knownRunIdsRaw;
  cachedSelectedRunIdRaw = selectedRunIdRaw;
  cachedSnapshot = {
    knownRunIds: parseKnownRunIds(knownRunIdsRaw),
    selectedRunId: normalizeRunId(selectedRunIdRaw)
  };
  return cachedSnapshot;
}

function getServerSnapshot(): KnownRunsSnapshot {
  return SERVER_SNAPSHOT;
}

function readKnownRunIds(): string[] {
  return parseKnownRunIds(readRaw(KNOWN_RUN_IDS_KEY));
}

function parseKnownRunIds(value: string | null): string[] {
  const parsed = readJson(value);
  if (!Array.isArray(parsed)) {
    return [];
  }
  return parsed.filter((value): value is string => typeof value === "string");
}

function readSelectedRunId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return normalizeRunId(window.localStorage.getItem(SELECTED_RUN_ID_KEY));
}

function normalizeRunId(value: string | null): string | null {
  return value && value.trim() ? value : null;
}

function readRaw(key: string): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(key);
}

function readJson(value: string | null): unknown {
  if (!value) {
    return null;
  }
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function writeJson(key: string, value: unknown): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(key, JSON.stringify(value));
}

function writeString(key: string, value: string | null): void {
  if (typeof window === "undefined") {
    return;
  }
  if (value === null) {
    window.localStorage.removeItem(key);
    return;
  }
  window.localStorage.setItem(key, value);
}

function notify(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }
}
