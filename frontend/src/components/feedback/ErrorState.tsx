import type { NormalizedApiError } from "../../api/types";

type ErrorStateProps = {
  error: NormalizedApiError;
};

export function ErrorState({ error }: ErrorStateProps) {
  return (
    <div className="state-box state-box--error">
      <strong>{error.message}</strong>
      <span>
        {error.status ? `HTTP ${error.status}` : "Client error"} / {error.code}
      </span>
    </div>
  );
}
