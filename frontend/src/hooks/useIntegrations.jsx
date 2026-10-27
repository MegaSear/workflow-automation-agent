import { useCallback, useEffect, useState } from "react";

import {
  connectJira as connectJiraRequest,
  disconnectIntegration,
  getGoogleCalendarAuthUrl,
  getIntegrations,
} from "../api/integrations";

const INITIAL_STATUS = {
  jira: false,
  google_calendar: false,
};

export function useIntegrations(token, logout) {
  const [status, setStatus] = useState(INITIAL_STATUS);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const data = await getIntegrations(token);
      setStatus(data);
      setError("");
    } catch (err) {
      if (err.status === 401) {
        logout();
        return;
      }

      setError(err.message || "Не удалось загрузить интеграции");
    } finally {
      setLoading(false);
    }
  }, [token, logout]);

  useEffect(() => {
    let cancelled = false;

    async function loadIntegrations() {
      try {
        const data = await getIntegrations(token);

        if (cancelled) return;

        setStatus(data);
        setError("");
      } catch (err) {
        if (cancelled) return;

        if (err.status === 401) {
          logout();
          return;
        }

        setError(err.message || "Не удалось загрузить интеграции");
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadIntegrations();

    return () => {
      cancelled = true;
    };
  }, [token, logout]);

  async function connectJira(credentials) {
    setBusy("jira");
    setError("");

    try {
      await connectJiraRequest(credentials, token);
      await refresh();
      return true;
    } catch (err) {
      if (err.status === 401) {
        logout();
      } else {
        setError(err.message || "Не удалось подключить Jira");
      }
      return false;
    } finally {
      setBusy("");
    }
  }

  async function disconnect(provider) {
    setBusy(provider);
    setError("");

    try {
      await disconnectIntegration(provider, token);
      setStatus((current) => ({
        ...current,
        [provider]: false,
      }));
    } catch (err) {
      if (err.status === 401) {
        logout();
      } else {
        setError(err.message || "Не удалось отключить интеграцию");
      }
    } finally {
      setBusy("");
    }
  }

  async function connectGoogleCalendar() {
    setBusy("google_calendar");
    setError("");

    try {
      const url = await getGoogleCalendarAuthUrl(token);
      window.location.assign(url);
    } catch (err) {
      if (err.status === 401) {
        logout();
      } else {
        setError(
          err.message || "Не удалось начать подключение Google Calendar",
        );
      }
      setBusy("");
    }
  }

  return {
    status,
    loading,
    busy,
    error,
    setError,
    connectJira,
    connectGoogleCalendar,
    disconnect,
  };
}
