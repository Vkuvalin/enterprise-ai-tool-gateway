import { apiRequest } from "./client";
import { toDisplayError } from "./errors";
import type {
  ApprovalResponse,
  AuditEventResponse,
  NormalizedApiError,
  RunDetailResponse,
  ToolCallResponse
} from "./types";

export type RunReadFailure = {
  runId: string;
  error: NormalizedApiError;
};

export type RunReadSummary = {
  attempted: number;
  succeeded: number;
  failures: RunReadFailure[];
};

export type SettledRunReads<T> = RunReadSummary & {
  successes: Array<{ runId: string; value: T }>;
};

export function getRunDetail(runId: string): Promise<RunDetailResponse> {
  return apiRequest<RunDetailResponse>(`/runs/${encodePathSegment(runId)}`);
}

export function getRunToolCalls(runId: string): Promise<ToolCallResponse[]> {
  return apiRequest<ToolCallResponse[]>(`/runs/${encodePathSegment(runId)}/tool-calls`);
}

export function getRunApprovals(runId: string): Promise<ApprovalResponse[]> {
  return apiRequest<ApprovalResponse[]>(`/runs/${encodePathSegment(runId)}/approvals`);
}

export function getRunAuditEvents(runId: string): Promise<AuditEventResponse[]> {
  return apiRequest<AuditEventResponse[]>(`/runs/${encodePathSegment(runId)}/audit-events`);
}

export async function settleRunReads<T>(
  runIds: readonly string[],
  read: (runId: string) => Promise<T>
): Promise<SettledRunReads<T>> {
  const outcomes = await Promise.all(
    runIds.map(async (runId) => {
      try {
        return { ok: true as const, runId, value: await read(runId) };
      } catch (error) {
        return { ok: false as const, runId, error: toDisplayError(error) };
      }
    })
  );
  const successes = outcomes
    .filter((outcome): outcome is Extract<(typeof outcomes)[number], { ok: true }> => outcome.ok)
    .map(({ runId, value }) => ({ runId, value }));
  const failures = outcomes
    .filter((outcome): outcome is Extract<(typeof outcomes)[number], { ok: false }> => !outcome.ok)
    .map(({ runId, error }) => ({ runId, error }));

  return {
    attempted: runIds.length,
    succeeded: successes.length,
    successes,
    failures
  };
}

function encodePathSegment(value: string): string {
  return encodeURIComponent(value);
}
