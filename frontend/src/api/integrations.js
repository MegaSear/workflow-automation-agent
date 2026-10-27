
import { API_BASE_URL } from "./config";

async function request(path, token, options = {}) {
    const response = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        headers: {
            Authorization: `Bearer ${token}`,
            ...(options.body
                ? { "Content-Type": "application/json" }
                : {}),
            ...options.headers,
        },
        // Нужно для OAuth-cookie Google Calendar.
        credentials: "include",
    });

    if (!response.ok) {
        let message = `HTTP ${response.status}`;

        try {
            const data = await response.json();
            message = data.detail || message;
        } catch {
            // Ответ сервера может быть не JSON.
        }

        const error = new Error(message);
        error.status = response.status;
        throw error;
    }

    if (response.status === 204) {
        return null;
    }

    return response.json();
}

export function getIntegrations(token) {
    return request("/api/integrations", token);
}

export function connectJira(credentials, token) {
    return request("/api/integrations/jira", token, {
        method: "PUT",
        body: JSON.stringify(credentials),
    });
}

export function disconnectIntegration(provider, token) {
    return request(`/api/integrations/${provider}`, token, {
        method: "DELETE",
    });
}

export async function getGoogleCalendarAuthUrl(token) {
    const data = await request(
        "/api/integrations/google_calendar/auth-url",
        token
    );

    return data.authorization_url;
}
