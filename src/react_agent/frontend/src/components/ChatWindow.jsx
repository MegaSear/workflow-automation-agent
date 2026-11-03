import { useEffect, useRef } from "react";
import IntegrationsMenu from "./IntegrationsMenu";

export default function ChatWindow({
  darkMode,
  toggleTheme,
  logout,
  messages,
  loading,
  activeToolTrace,
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
            <div>{message.content}</div>
            {message.role === "assistant" && message.toolTrace?.length > 0 && (
              <details className="tool-trace" open>
                <summary>
                  Thinking... ({message.toolTrace.length})
                </summary>
                <ToolTraceList tools={message.toolTrace} />
              </details>
            )}
          </div>
        ))}

        {loading && (
          <details className="tool-trace tool-trace--active">
            <summary>
              <span className="thinking">Thinking...</span>
            </summary>
            <ToolTraceList tools={activeToolTrace} />
          </details>
        )}
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

function formatToolName(name) {
  const [server, tool] = name.split("__", 2);
  const serverNames = {
    my_default: "Мои инструменты",
    github: "GitHub",
    jira: "Jira",
    google_calendar: "Google Calendar",
  };

  return `${serverNames[server] || server}: ${tool || name}`;
}

function ToolTraceList({ tools }) {
  if (tools.length === 0) {
    return <p className="tool-trace-empty">Инструменты пока не вызывались</p>;
  }

  return (
    <ol>
      {tools.map((tool, toolIndex) => (
        <li key={`${tool.name}-${toolIndex}`}>
          <span>{formatToolName(tool.name)}</span>
          <span
            className={`tool-trace-status tool-trace-status--${tool.status}`}
          >
            {tool.status === "running"
              ? "Выполняется"
              : tool.status === "success"
                ? "Готово"
                : "Ошибка"}
          </span>
        </li>
      ))}
    </ol>
  );
}
