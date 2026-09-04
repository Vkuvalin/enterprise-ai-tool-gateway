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

let cachedSnapshot: KnownRunsSnapshot = SERVER_SNAPSHOT;
let hasHydratedFromStorage = false;
let storageUsable = true;

export function useKnownRuns(): KnownRunsSnapshot {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export function addKnownRunId(runId: string): void {
  const normalizedRunId = runId.trim();
  if (!normalizedRunId) {
    return;
  }
  const current = getClientSnapshot();
  replaceSnapshot({
    knownRunIds: [normalizedRunId, ...current.knownRunIds.filter((id) => id !== normalizedRunId)].slice(0, 25),
    selectedRunId: normalizedRunId
  });
}

export function removeKnownRunId(runId: string): void {
  const current = getClientSnapshot();
  const nextKnownRunIds = current.knownRunIds.filter((id) => id !== runId);
  replaceSnapshot({
    knownRunIds: nextKnownRunIds,
    selectedRunId: current.selectedRunId === runId ? nextKnownRunIds[0] ?? null : current.selectedRunId
  });
}

export function setSelectedRunId(runId: string | null): void {
  const normalized = runId?.trim() || null;
  const current = getClientSnapshot();
  if (current.selectedRunId === normalized) {
    return;
  }
  replaceSnapshot({
    knownRunIds: current.knownRunIds,
    selectedRunId: normalized
  });
}

export function clearKnownRuns(): void {
  replaceSnapshot(SERVER_SNAPSHOT);
}

function subscribe(callback: () => void): () => void {
  if (typeof window === "undefined") {
    return () => undefined;
  }

  const onStorage = (event: StorageEvent) => {
    if (event.key === KNOWN_RUN_IDS_KEY || event.key === SELECTED_RUN_ID_KEY) {
      hydrateSnapshotFromStorage(true);
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
  return getClientSnapshot();
}

function getServerSnapshot(): KnownRunsSnapshot {
  return SERVER_SNAPSHOT;
}

function parseKnownRunIds(value: string | null): string[] {
  const parsed = readJson(value);
  if (!Array.isArray(parsed)) {
    return [];
  }
  return Array.from(
    new Set(
      parsed
        .filter((item): item is string => typeof item === "string")
        .map((item) => item.trim())
        .filter(Boolean)
    )
  ).slice(0, 25);
}

function normalizeRunId(value: string | null): string | null {
  const normalized = value?.trim() ?? "";
  return normalized || null;
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

function getClientSnapshot(): KnownRunsSnapshot {
  hydrateSnapshotFromStorage(false);
  return cachedSnapshot;
}

function hydrateSnapshotFromStorage(force: boolean): void {
  if (typeof window === "undefined" || (hasHydratedFromStorage && !force)) {
    return;
  }
  hasHydratedFromStorage = true;

  const knownRunIdsRaw = safeReadStorage(KNOWN_RUN_IDS_KEY);
  const selectedRunIdRaw = safeReadStorage(SELECTED_RUN_ID_KEY);
  const nextKnownRunIds = knownRunIdsRaw.ok ? parseKnownRunIds(knownRunIdsRaw.value) : cachedSnapshot.knownRunIds;
  const nextSelectedRunId = selectedRunIdRaw.ok
    ? normalizeRunId(selectedRunIdRaw.value)
    : cachedSnapshot.selectedRunId;
  if (
    arraysEqual(cachedSnapshot.knownRunIds, nextKnownRunIds) &&
    cachedSnapshot.selectedRunId === nextSelectedRunId
  ) {
    return;
  }
  cachedSnapshot = {
    knownRunIds: nextKnownRunIds,
    selectedRunId: nextSelectedRunId
  };
}

function replaceSnapshot(nextSnapshot: KnownRunsSnapshot): void {
  cachedSnapshot = nextSnapshot;
  hasHydratedFromStorage = true;
  if (typeof window !== "undefined") {
    safeWriteStorage(KNOWN_RUN_IDS_KEY, JSON.stringify(nextSnapshot.knownRunIds));
    if (nextSnapshot.selectedRunId === null) {
      safeRemoveStorage(SELECTED_RUN_ID_KEY);
    } else {
      safeWriteStorage(SELECTED_RUN_ID_KEY, nextSnapshot.selectedRunId);
    }
  }
  notify();
}

function safeReadStorage(key: string): { ok: true; value: string | null } | { ok: false } {
  if (!storageUsable) {
    return { ok: false };
  }
  try {
    return { ok: true, value: window.localStorage.getItem(key) };
  } catch {
    storageUsable = false;
    return { ok: false };
  }
}

function safeWriteStorage(key: string, value: string): boolean {
  if (!storageUsable) {
    return false;
  }
  try {
    window.localStorage.setItem(key, value);
    return true;
  } catch {
    storageUsable = false;
    return false;
  }
}

function safeRemoveStorage(key: string): boolean {
  if (!storageUsable) {
    return false;
  }
  try {
    window.localStorage.removeItem(key);
    return true;
  } catch {
    storageUsable = false;
    return false;
  }
}

function arraysEqual(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function notify(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }
}
