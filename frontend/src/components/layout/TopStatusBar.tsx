import { apiBaseUrl } from "../../api/client";
import { useApiStatus } from "../../features/capabilities/useApiStatus";
import { useLocale } from "../../i18n/LocaleProvider";
import { Toast, useToast } from "../feedback/Toast";
import { StatusChip } from "../status/StatusChip";

export function TopStatusBar() {
  const { locale, setLocale, t } = useLocale();
  const { toast, showToast } = useToast();
  const { health, capabilities, loading, hasLoaded, stale, error, refresh } = useApiStatus({
    onRefreshSuccess: () => showToast({ messageKey: "common.dataRefreshed", tone: "success" }),
    onRefreshError: () => showToast({ messageKey: "common.refreshFailed", tone: "error" })
  });
  const initialLoading = loading && !hasLoaded;

  return (
    <>
      <header className="top-status-bar">
        <div className="top-status-bar__brand">
          <span className="brand-mark">EA</span>
          <span>Enterprise AI Tool Gateway</span>
        </div>
        <div className="top-status-bar__badges">
          <StatusChip label={t("chrome.localDemo")} tone="blue" />
          <StatusChip
            label={t("chrome.provider", { value: capabilities?.provider_mode ?? t("common.unknown") })}
            tone={capabilities?.provider_mode === "mock" ? "purple" : "gray"}
          />
          <StatusChip
            label={
              initialLoading
                ? t("chrome.apiChecking")
                : stale
                  ? t("chrome.apiStatusStale", { value: health?.status ?? t("common.unknown") })
                  : error
                    ? t("chrome.apiUnavailable")
                    : t("chrome.apiStatus", { value: health?.status ?? t("common.unknown") })
            }
            tone={stale ? "orange" : error ? "red" : health?.status === "ok" ? "green" : "gray"}
            title={stale ? error?.message : undefined}
          />
          <StatusChip label={t("chrome.database")} tone="gray" />
          <StatusChip
            label={t("chrome.modelSelector", {
              value: capabilities?.model_selection.enabled ? t("common.enabled") : t("common.disabled")
            })}
            tone={capabilities?.model_selection.enabled ? "orange" : "gray"}
          />
        </div>
        <div className="top-status-bar__right">
          <code>{apiBaseUrl}</code>
          <div className="locale-switch" role="group" aria-label={t("locale.selectorLabel")}>
            <button
              className="locale-switch__button"
              type="button"
              aria-pressed={locale === "ru"}
              onClick={() => setLocale("ru")}
            >
              {t("locale.ru")}
            </button>
            <button
              className="locale-switch__button"
              type="button"
              aria-pressed={locale === "en"}
              onClick={() => setLocale("en")}
            >
              {t("locale.en")}
            </button>
          </div>
          <button className="ghost-button" type="button" onClick={refresh}>
            {t("common.refresh")}
          </button>
        </div>
      </header>
      <Toast toast={toast} />
    </>
  );
}
