import { useEffect, useState } from "react";

import ChatWindow from "./ChatWindow";
import SideBar from "./SideBar";
import { useChat } from "../hooks/useChat";
import { useIntegrations } from "../hooks/useIntegrations";

export default function ChatApp({ token, logout, darkMode, toggleTheme }) {
  const chat = useChat(token, logout);
  const integrations = useIntegrations(token, logout);
  const [sidebarOpen, setSidebarOpen] = useState(
    () => !window.matchMedia("(max-width: 768px)").matches,
  );

  useEffect(() => {
    if (!sidebarOpen) return;

    const handleEscape = (event) => {
      if (event.key === "Escape") {
        setSidebarOpen(false);
      }
    };

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [sidebarOpen]);

  return (
    <div
      className={`app-layout ${
        sidebarOpen ? "app-layout--sidebar-open" : "app-layout--sidebar-closed"
      }`}
    >
      {sidebarOpen && (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="Закрыть боковую панель"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <SideBar
        conversations={chat.conversations}
        activeConversationId={chat.conversationId}
        onSelectConversation={(id) => {
          chat.openConversation(id);

          if (window.matchMedia("(max-width: 768px)").matches) {
            setSidebarOpen(false);
          }
        }}
        onNewConversation={() => {
          chat.startNewConversation();

          if (window.matchMedia("(max-width: 768px)").matches) {
            setSidebarOpen(false);
          }
        }}
        onDeleteConversation={chat.handleDeleteConversation}
        onClose={() => setSidebarOpen(false)}
        onRenameConversation={chat.handleRenameConversation}
        darkMode={darkMode}
      />

      {!sidebarOpen && (
        <button
          type="button"
          className="sidebar-toggle"
          aria-label="Открыть боковую панель"
          title="Открыть боковую панель"
          onClick={() => setSidebarOpen(true)}
        >
          <span aria-hidden="true">☰</span>
        </button>
      )}

      <ChatWindow
        darkMode={darkMode}
        toggleTheme={toggleTheme}
        logout={logout}
        messages={chat.messages}
        loading={chat.loading}
        input={chat.input}
        setInput={chat.setInput}
        handleKeyDown={chat.handleKeyDown}
        sendMessage={chat.sendMessage}
        integrations={integrations}
      />
    </div>
  );
}
