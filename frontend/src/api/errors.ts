export type NormalizedApiError = {
  status: number | null;
  code: string;
  message: string;
  details?: unknown;
};

export class ApiError extends Error {
  readonly normalized: NormalizedApiError;

  constructor(error: NormalizedApiError) {
    super(error.message);
    this.name = "ApiError";
    this.normalized = error;
  }
}

export function toDisplayError(error: unknown): NormalizedApiError {
  if (error instanceof ApiError) {
    return error.normalized;
  }

  if (error instanceof Error) {
    return {
      status: null,
      code: "client_error",
      message: error.message || "Client error."
    };
  }

  return {
    status: null,
    code: "unknown_client_error",
    message: "Unexpected client error."
  };
}
