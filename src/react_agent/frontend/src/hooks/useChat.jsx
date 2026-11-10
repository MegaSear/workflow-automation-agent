import { useEffect, useRef, useState } from "react";
import { getChatProgress, sendMessageRequest } from "../api/chat";
import {
  getConversations,
  getConversationMessages,
  deleteConversation as deleteConversationRequest,
  renameConversation as renameConversationRequest,
} from "../api/conversations";

function normalizeMessages(messages) {
  return messages.map((message) => ({
    ...message,
    toolTrace: message.tool_trace || [],
  }));
}

export function useChat(token, logout) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeToolTrace, setActiveToolTrace] = useState([]);
  const [conversations, setConversations] = useState([]);

  const viewVersionRef = useRef(0);

  async function refreshConversations() {
    const data = await getConversations(token);
    setConversations(data);
    return data;
  }

  useEffect(() => {
    const requestVersion = ++viewVersionRef.current;
    let cancelled = false;

    getConversations(token)
      .then(async (data) => {
        if (cancelled) return;

        setConversations(data);
        if (viewVersionRef.current !== requestVersion) return;

        if (data.length === 0) {
          setConversationId(null);
          setMessages([]);
          setInput("");
          return;
        }

        const conversation = data[0];

        const history = await getConversationMessages(conversation.id, token);

        if (cancelled || viewVersionRef.current !== requestVersion) return;

        setConversationId(conversation.id);
        setMessages(normalizeMessages(history));
      })
      .catch((error) => {
        if (cancelled) return;

        if (error.status === 401) {
          logout();
          return;
        }

        console.error("Не удалось загрузить диалоги:", error);
      });

    return () => {
      cancelled = true;
    };
  }, [token, logout]);

  async function openConversation(id) {
    if (id === conversationId) {
      return;
    }

    const requestVersion = ++viewVersionRef.current;
    setActiveToolTrace([]);

    try {
      const history = await getConversationMessages(id, token);

      if (viewVersionRef.current !== requestVersion) {
        return;
      }

      setConversationId(id);
      setMessages(normalizeMessages(history));
      setInput("");
    } catch (error) {
      if (error.status === 401) {
        logout();
        return;
      }

      console.error("Не удалось загрузить диалог:", error);
    }
  }

  function startNewConversation() {
    viewVersionRef.current += 1;

    setConversationId(null);
    setMessages([]);
    setInput("");
    setActiveToolTrace([]);
  }

  async function handleDeleteConversation(id) {
    if (!token) {
      return;
    }

    const requestVersion = viewVersionRef.current;
    const wasActive = id === conversationId;

    // Сначала удаляем диалог на сервере.
    try {
      await deleteConversationRequest(id, token);
    } catch (error) {
      if (error.status === 401) {
        logout();
        return;
      }

      console.error("Не удалось удалить диалог:", error);
      return;
    }

    // Обновляем список после успешного удаления.
    const remainingConversations = conversations.filter(
      (conversation) => conversation.id !== id,
    );

    setConversations((prev) =>
      prev.filter((conversation) => conversation.id !== id),
    );

    if (!wasActive || viewVersionRef.current !== requestVersion) {
      return;
    }

    const nextVersion = ++viewVersionRef.current;

    setInput("");
    setMessages([]);
    setActiveToolTrace([]);

    // Если диалогов больше нет, показываем пустой чат.
    if (remainingConversations.length === 0) {
      setConversationId(null);
      return;
    }

    // Иначе переключаемся на первый оставшийся диалог.
    const nextConversation = remainingConversations[0];

    setConversationId(nextConversation.id);

    try {
      const history = await getConversationMessages(nextConversation.id, token);
      if (viewVersionRef.current !== nextVersion) {
        return;
      }
      setMessages(normalizeMessages(history));
    } catch (error) {
        if (viewVersionRef.current !== nextVersion) {
          return;
        }

        if (error.status === 401) {
          logout();
          return;
        }

        console.error("Не удалось загрузить следующий диалог:", error);
      }
  }

  async function handleRenameConversation(id, title) {
    if (!token) {
      return false;
    }

    const normalizedTitle = title.trim();

    if (!normalizedTitle || normalizedTitle.length > 100) {
      return false;
    }

    try {
      const updated = await renameConversationRequest(
        id,
        normalizedTitle,
        token,
      );

      setConversations((prev) =>
        prev.map((conversation) =>
          conversation.id === id
            ? { ...conversation, title: updated.title }
            : conversation,
        ),
      );

      return true;
    } catch (error) {
      if (error.status === 401) {
        logout();
        return false;
      }

      console.error("Не удалось переименовать диалог:", error);
      return false;
    }
  }

  async function sendMessage() {
    if (!input.trim() || loading || !token) {
      return;
    }

    const requestViewVersion = viewVersionRef.current;
    const userMessage = input.trim();
    setInput("");

    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content: userMessage,
      },
    ]);

    setLoading(true);
    if (viewVersionRef.current === requestViewVersion) {
      setActiveToolTrace([]);
    }
    const traceId = globalThis.crypto.randomUUID();
    let keepPolling = true;

    const pollProgress = async () => {
      while (keepPolling) {
        try {
          const progress = await getChatProgress(traceId, token);
          if (viewVersionRef.current === requestViewVersion) {
            setActiveToolTrace(progress.tool_trace);
          }
        } catch (error) {
          if (error.status === 401) {
            logout();
            return;
          } else if (error.status !== 404) {
            console.error("Не удалось получить ход выполнения:", error);
            return;
          }
        }

        await new Promise((resolve) => setTimeout(resolve, 400));
      }
    };

    const progressPolling = pollProgress();

    try {
      const data = await sendMessageRequest(
        userMessage,
        conversationId,
        token,
        traceId,
      );

      if (viewVersionRef.current === requestViewVersion) {
        setConversationId(data.conversation_id);

        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.response,
            toolTrace: data.tool_trace || [],
          },
        ]);
      }

      try {
        await refreshConversations();
      } catch (error) {
        if (error.status === 401) {
          logout();
          return;
        }

        console.error("Не удалось обновить список диалогов:", error);
      }
    } catch (error) {
      if (error.status === 401) {
        logout();
        return;
      }
      if (viewVersionRef.current === requestViewVersion) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: error.message || "Ошибка соединения с сервером.",
          },
        ]);
      }
    } finally {
      keepPolling = false;
      await progressPolling;
      if (viewVersionRef.current === requestViewVersion) {
        setActiveToolTrace([]);
      }
      setLoading(false);
    }
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  }

  return {
    input,
    setInput,
    messages,
    conversationId,
    loading,
    activeToolTrace,
    conversations,
    openConversation,
    startNewConversation,
    sendMessage,
    handleKeyDown,
    handleDeleteConversation,
    handleRenameConversation,
  };
}
