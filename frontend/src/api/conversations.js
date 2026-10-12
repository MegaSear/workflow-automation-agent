import { API_BASE_URL } from "./config";

async function authorizedGet(url, token) {
    const response = await fetch(url, {
        headers: {
            Authorization: `Bearer ${token}`,
        },
    });


    if (!response.ok) {
        const error = new Error(`HTTP ${response.status}`);
        error.status = response.status;
        throw error;
    }

    return response.json();
}

export async function getConversations(token) {
    return authorizedGet(`${API_BASE_URL}/api/conversations`, token);
}

export async function getConversationMessages(conversationId, token) {
    return authorizedGet(
        `${API_BASE_URL}/api/conversations/${conversationId}/messages`,
        token
    );
}

export async function deleteConversation(conversationId, token) {
    const response = await fetch(
        `${API_BASE_URL}/api/conversations/${conversationId}`,
        {
            method: "DELETE",
            headers: {
                Authorization: `Bearer ${token}`,
            },
        }
    );

    if (!response.ok) {
        const error = new Error(`HTTP ${response.status}`);
        error.status = response.status;
        throw error;
    }
}

export async function renameConversation(conversationId, title, token) {
    const response = await fetch(
        `${API_BASE_URL}/api/conversations/${conversationId}`,
        {
            method: "PATCH",
            headers: {
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ title }),
        }
    );

    if (!response.ok) {
        const error = new Error(`HTTP ${response.status}`);
        error.status = response.status;
        throw error;
    }

    return response.json();
}