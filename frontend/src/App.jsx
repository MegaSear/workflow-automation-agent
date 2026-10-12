import AuthForm from "./components/AuthForm";
import ChatWindow from "./components/ChatWindow";
import SideBar from "./components/SideBar";

import { useTheme } from "./hooks/useTheme";
import { useAuth } from "./hooks/useAuth";
import { useChat } from "./hooks/useChat";

import { useEffect, useState } from "react";

import "./index.css";

function App() {
    const auth = useAuth();
    const chat = useChat(auth.token, auth.logout);
    const { darkMode, toggleTheme } = useTheme();

    const [sidebarOpen, setSidebarOpen] = useState(
        () => !window.matchMedia("(max-width: 768px)").matches
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

    if (!auth.token) {
        return (
            <AuthForm
                darkMode={darkMode}
                toggleTheme={toggleTheme}
                isRegister={auth.isRegister}
                setIsRegister={auth.setIsRegister}
                email={auth.email}
                setEmail={auth.setEmail}
                password={auth.password}
                setPassword={auth.setPassword}
                authError={auth.authError}
                setAuthError={auth.setAuthError}
                handleAuth={auth.handleAuth}
            />
        );
    }

    return (
        <div
            className={`app-layout ${
                sidebarOpen
                    ? "app-layout--sidebar-open"
                    : "app-layout--sidebar-closed"
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
                logout={auth.logout}
                messages={chat.messages}
                loading={chat.loading}
                input={chat.input}
                setInput={chat.setInput}
                handleKeyDown={chat.handleKeyDown}
                sendMessage={chat.sendMessage}
            />
        </div>
    );
}

export default App;