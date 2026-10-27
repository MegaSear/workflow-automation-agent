import { useEffect, useRef } from "react";
import IntegrationsMenu from "./IntegrationsMenu";

export default function ChatWindow({
  darkMode,
  toggleTheme,
  logout,
  messages,
  loading,
  input,
  setInput,
  handleKeyDown,
  sendMessage,
  integrations,
}) {
  const textareaRef = useRef(null);
  const messagesEndRef = useRef(null);
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: "auto",
      block: "end",
    });
  }, [messages, loading]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = "auto";

    const fullHeight = textarea.scrollHeight;
    textarea.style.height = `${Math.min(fullHeight, 200)}px`;
    textarea.style.overflowY = fullHeight > 200 ? "auto" : "hidden";
  }, [input]);

  return (
    <div className="app">
      <header className="header">
        <div className="header-actions">
          <button
            className="theme-button"
            onClick={toggleTheme}
            title={darkMode ? "Светлая тема" : "Тёмная тема"}
          >
            {darkMode ? "☀" : "☾"}
          </button>

          <button className="logout-button" onClick={logout}>
            Выйти
          </button>
        </div>
      </header>

      <main className="chat">
        {messages.length === 0 && <div className="empty">Чем могу помочь?</div>}

        {messages.map((message, index) => (
          <div key={index} className={`message ${message.role}`}>
            {message.content}
          </div>
        ))}

        {loading && <div className="thinking">Thinking...</div>}
        <div ref={messagesEndRef} />
      </main>

      <footer className="input-area">
        <IntegrationsMenu {...integrations} />
        <textarea
          ref={textareaRef}
          rows={1}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Введите сообщение..."
          aria-label="Введите сообщение"
          className="message-input"
        />

        <button
          type="button"
          className="send-button"
          onClick={sendMessage}
          disabled={loading || !input.trim()}
          aria-label="Отправить сообщение"
          title="Отправить сообщение"
        >
          <span aria-hidden="true">↑</span>
        </button>
      </footer>
    </div>
  );
}
