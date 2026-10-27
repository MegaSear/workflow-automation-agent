import { useEffect, useRef, useState } from "react";
import { INTEGRATIONS } from "../config/integrations";
import JiraConnectForm from "./JiraConnectForm";

export default function IntegrationsMenu({
  status,
  loading,
  busy,
  error,
  setError,
  connectJira,
  connectGoogleCalendar,
  disconnect,
}) {
  const [open, setOpen] = useState(false);
  const [jiraFormOpen, setJiraFormOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  function handleConnect(integration) {
    setError("");

    if (integration.id === "google_calendar") {
      connectGoogleCalendar();
      return;
    }

    if (integration.id === "jira") {
      setJiraFormOpen((value) => !value);
    }
  }

  return (
    <div className="integrations-wrapper" ref={menuRef}>
      <div className="integrations">
        <button
          type="button"
          className="integrations-trigger"
          aria-expanded={open}
          onClick={() => {
            setOpen((value) => !value);
            setError("");
          }}
        >
          <span className="integrations-trigger-icon" aria-hidden="true">
            📎
          </span>
          <span>Интеграции</span>
          <span className="integrations-chevron" aria-hidden="true">
            {open ? "▴" : "▾"}
          </span>
        </button>

        {open && (
          <div className="integrations-dropdown">
            <div className="integrations-heading">Подключённые сервисы</div>

            {loading ? (
              <p className="integration-muted">Загрузка статусов…</p>
            ) : (
              <>
                {INTEGRATIONS.map((integration) => {
                  const connected = Boolean(status[integration.id]);
                  const isBusy = busy === integration.id;

                  return (
                    <div className="integration-row" key={integration.id}>
                      <div className="integration-info">
                        <strong>{integration.name}</strong>
                        <span>
                          {connected
                            ? integration.connectedLabel
                            : integration.disconnectedLabel}
                        </span>
                      </div>

                      <button
                        type="button"
                        className="integration-action"
                        disabled={Boolean(busy)}
                        onClick={() => {
                          if (connected) {
                            disconnect(integration.id);
                          } else {
                            handleConnect(integration);
                          }
                        }}
                      >
                        {isBusy
                          ? "..."
                          : connected
                            ? "Отключить"
                            : integration.id === "jira" && jiraFormOpen
                              ? "Скрыть"
                              : "Подключить"}
                      </button>
                    </div>
                  );
                })}

                {jiraFormOpen && !status.jira && (
                  <JiraConnectForm
                    connectJira={connectJira}
                    busy={busy}
                    onSuccess={() => setJiraFormOpen(false)}
                  />
                )}
              </>
            )}

            {error && (
              <p className="integration-error" role="alert">
                {error}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
