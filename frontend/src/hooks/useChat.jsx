import { useEffect, useState } from "react";
import { sendMessageRequest } from "../api/chat";
import {
  getConversations,
  getConversationMessages,
  deleteConversation as deleteConversationRequest,
  renameConversation as renameConversationRequest,
} from "../api/conversations";

export function useChat(token, logout) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [conversations, setConversations] = useState([]);

  async function refreshConversations() {
    const data = await getConversations(token);
    setConversations(data);
    return data;
  }

  useEffect(() => {
    let cancelled = false;

    getConversations(token)
      .then(async (data) => {
        if (cancelled) return;

        setConversations(data);

        if (data.length === 0) {
          setConversationId(null);
          setMessages([]);
          setInput("");
          return;
        }

        const conversation = data[0];

        const history = await getConversationMessages(conversation.id, token);

        if (cancelled) return;

        setConversationId(conversation.id);
        setMessages(history);
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
    if (id === conversationId || loading) {
      return;
    }

    try {
      const history = await getConversationMessages(id, token);

      setConversationId(id);
      setMessages(history);
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
    if (loading) {
      return;
    }

    setConversationId(null);
    setMessages([]);
    setInput("");
  }

  async function handleDeleteConversation(id) {
    if (loading || !token) {
      return;
    }

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

    setConversations(remainingConversations);

    // Если удалили неактивный диалог, больше ничего делать не нужно.
    if (id !== conversationId) {
      return;
    }

    setInput("");
    setMessages([]);

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

      setMessages(history);
    } catch (error) {
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

    try {
      const data = await sendMessageRequest(userMessage, conversationId, token);

      setConversationId(data.conversation_id);

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.response,
        },
      ]);

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

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Ошибка соединения с сервером.",
        },
      ]);
    } finally {
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
    conversations,
    openConversation,
    startNewConversation,
    sendMessage,
    handleKeyDown,
    handleDeleteConversation,
    handleRenameConversation,
  };
}
