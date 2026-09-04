export type NormalizedApiError = {
  status: number | null;
  code: string;
  message: string;
  details?: unknown;
  frontendMessage?: "client_error" | "unexpected_client_error" | "api_request_failed";
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
    if (error.message) {
      return {
        status: null,
        code: "client_error",
        message: error.message
      };
    }
    return {
      status: null,
      code: "client_error",
      message: "Client error.",
      frontendMessage: "client_error"
    };
  }

  return {
    status: null,
    code: "unknown_client_error",
    message: "Unexpected client error.",
    frontendMessage: "unexpected_client_error"
  };
}
