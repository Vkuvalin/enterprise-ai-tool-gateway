import type { NormalizedApiError } from "../../api/types";
import { useLocale } from "../../i18n/LocaleProvider";
import type { Translator } from "../../i18n/messages";

type ErrorStateProps = {
  error: NormalizedApiError;
};

export function ErrorState({ error }: ErrorStateProps) {
  const { t } = useLocale();
  return (
    <div className="state-box state-box--error">
      <strong>{getErrorMessage(error, t)}</strong>
      <span>
        {error.status ? `HTTP ${error.status}` : t("common.clientError")} / {error.code}
      </span>
    </div>
  );
}

function getErrorMessage(error: NormalizedApiError, t: Translator): string {
  if (error.frontendMessage === "client_error") {
    return t("common.clientErrorMessage");
  }
  if (error.frontendMessage === "unexpected_client_error") {
    return t("common.unexpectedClientError");
  }
  if (error.frontendMessage === "api_request_failed" && error.status !== null) {
    return t("common.apiRequestFailed", { status: error.status });
  }
  return error.message;
}
