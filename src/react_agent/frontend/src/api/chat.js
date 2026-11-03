import { API_BASE_URL } from "./config";

export async function sendMessageRequest(
  message,
  conversationId,
  token,
  traceId,
) {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + token,
    },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      trace_id: traceId,
    }),
  });

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") {
        message = body.detail;
      }
    } catch (parseError) {
      if (!(parseError instanceof SyntaxError)) {
        throw parseError;
      }
    }

    const error = new Error(message);
    error.status = response.status;
    throw error;
  }

  return response.json();
}

export async function getChatProgress(traceId, token) {
  const response = await fetch(
    `${API_BASE_URL}/api/chat/${traceId}/progress`,
    {
      headers: {
        Authorization: "Bearer " + token,
      },
    },
  );

  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }

  return response.json();
}
