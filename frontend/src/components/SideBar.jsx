import { useEffect, useState } from "react";
import "./SideBar.css";

export default function SideBar({
    conversations = [],
    activeConversationId = null,
    onSelectConversation,
    onNewConversation,
    onDeleteConversation,
    onClose,
    onRenameConversation,
    darkMode = false,
}) {

    const [openMenuId, setOpenMenuId] = useState(null);
    const [editingConversationId, setEditingConversationId] = useState(null);
    const [editingTitle, setEditingTitle] = useState("");

    useEffect(() => {
        const closeMenu = (event) => {
            if (!event.target.closest?.(".sidebar__actions")) {
                setOpenMenuId(null);
            }
        };

        document.addEventListener("pointerdown", closeMenu);

        return () => {
            document.removeEventListener("pointerdown", closeMenu);
        };
    }, []);

    return (
        <aside
            className={`sidebar ${
                darkMode ? "sidebar--dark" : "sidebar--light"
            }`}
            aria-label="История диалогов"
        >
            <div className="sidebar__header">
                <div className="sidebar__topbar">
                    <div className="sidebar__brand">Dionysius</div>

                    <button
                        type="button"
                        className="sidebar__collapse"
                        onClick={onClose}
                        aria-label="Свернуть боковую панель"
                        title="Свернуть боковую панель"
                    >
                        ‹
                    </button>
                </div>

                <button
                    type="button"
                    className="sidebar__new-chat"
                    onClick={onNewConversation}
                    disabled={!onNewConversation}
                >
                    <span aria-hidden="true">+</span>
                    Новый диалог
                </button>
            </div>

            <div className="sidebar__content">
                <h2 className="sidebar__heading">
                    История
                </h2>

                {conversations.length === 0 ? (
                    <p className="sidebar__empty">
                        Пока нет диалогов
                    </p>
                ) : (
                    <ul className="sidebar__list">
                        {conversations.map((conversation) => {
                            const isActive =
                                conversation.id === activeConversationId;

                            const title =
                                typeof conversation.title === "string" &&
                                conversation.title.trim()
                                    ? conversation.title.trim()
                                    : "Новый диалог";

                            return (
                                <li
                                    key={conversation.id}
                                    className="sidebar__item"
                                >
                                    {editingConversationId === conversation.id ? (
                                        <form
                                            className="sidebar__rename-form"
                                            onSubmit={async (event) => {
                                                event.preventDefault();

                                                const nextTitle = editingTitle.trim();
                                                if (!nextTitle) return;

                                                const saved = await onRenameConversation?.(
                                                    conversation.id,
                                                    nextTitle
                                                );

                                                if (saved) {
                                                    setEditingConversationId(null);
                                                    setEditingTitle("");
                                                }
                                            }}
                                        >
                                            <input
                                                className="sidebar__rename-input"
                                                value={editingTitle}
                                                onChange={(event) => setEditingTitle(event.target.value)}
                                                maxLength={100}
                                                autoFocus
                                                aria-label="Название диалога"
                                                onKeyDown={(event) => {
                                                    if (event.key === "Escape") {
                                                        setEditingConversationId(null);
                                                        setEditingTitle("");
                                                    }
                                                }}
                                            />

                                            <button type="submit" aria-label="Сохранить название">
                                                ✓
                                            </button>

                                            <button
                                                type="button"
                                                aria-label="Отменить переименование"
                                                onClick={() => {
                                                    setEditingConversationId(null);
                                                    setEditingTitle("");
                                                }}
                                            >
                                                ×
                                            </button>
                                        </form>
                                    ) : (
                                        <button
                                            type="button"
                                            className={`sidebar__conversation ${
                                                isActive ? "sidebar__conversation--active" : ""
                                            }`}
                                            onClick={() => onSelectConversation?.(conversation.id)}
                                            aria-current={isActive ? "page" : undefined}
                                            title={title}
                                        >
                                            {title}
                                        </button>
                                    )}

                                    <div className="sidebar__actions">
                                        <button
                                            type="button"
                                            className="sidebar__more"
                                            aria-label={`Действия с диалогом: ${title}`}
                                            aria-expanded={openMenuId === conversation.id}
                                            title="Действия"
                                            onClick={() =>
                                                setOpenMenuId((current) =>
                                                    current === conversation.id ? null : conversation.id
                                                )
                                            }
                                        >
                                            ⋯
                                        </button>

                                        {openMenuId === conversation.id && (
                                            <div className="sidebar__menu" role="menu">
                                                <button
                                                    type="button"
                                                    role="menuitem"
                                                    onClick={() => {
                                                        setEditingConversationId(conversation.id);
                                                        setEditingTitle(title);
                                                        setOpenMenuId(null);
                                                    }}
                                                >
                                                    Переименовать
                                                </button>

                                                <button
                                                    type="button"
                                                    role="menuitem"
                                                    className="sidebar__menu-delete"
                                                    onClick={() => {
                                                        setOpenMenuId(null);
                                                        onDeleteConversation?.(conversation.id);
                                                    }}
                                                >
                                                    Удалить
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </div>
        </aside>
    );
}