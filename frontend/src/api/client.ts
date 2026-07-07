import { ApiError } from "./errors";

const DEFAULT_API_BASE_URL = "/api/v1";

export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL;

type RequestOptions = {
  method?: "GET" | "POST";
  body?: unknown;
};

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: HeadersInit = {};

  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body)
  });

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    throw new ApiError({
      status: response.status,
      code: extractErrorCode(payload),
      message: extractErrorMessage(payload, response.status),
      details: payload
    });
  }

  return payload as T;
}

function extractErrorCode(payload: unknown): string {
  const detail = getDetail(payload);
  if (isRecord(detail) && typeof detail.code === "string") {
    return detail.code;
  }
  return "api_error";
}

function extractErrorMessage(payload: unknown, status: number): string {
  const detail = getDetail(payload);
  if (isRecord(detail) && typeof detail.message === "string") {
    return detail.message;
  }
  if (typeof detail === "string") {
    return detail;
  }
  return `API request failed with HTTP ${status}.`;
}

function getDetail(payload: unknown): unknown {
  if (payload && typeof payload === "object" && "detail" in payload) {
    return (payload as { detail: unknown }).detail;
  }
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}
