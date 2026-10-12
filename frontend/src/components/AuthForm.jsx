export default function AuthForm({
    darkMode,
    toggleTheme,
    isRegister,
    setIsRegister,
    email,
    setEmail,
    password,
    setPassword,
    authError,
    handleAuth,
}) {
    return (
        <div className="app">
            <header className="header">
                <h1>Dionysius</h1>

                <button
                    className="theme-button"
                    onClick={toggleTheme}
                    title={
                        darkMode
                            ? "Светлая тема"
                            : "Тёмная тема"
                    }
                >
                    {darkMode ? "☀" : "☾"}
                </button>
            </header>

            <main className="auth-page">
                <div className="auth-card">
                    <h2>
                        {isRegister
                            ? "Регистрация"
                            : "Вход"}
                    </h2>

                    <form onSubmit={handleAuth}>
                        <input
                            type="email"
                            placeholder="Email"
                            value={email}
                            onChange={(event) =>
                                setEmail(event.target.value)
                            }
                            required
                        />

                        <input
                            type="password"
                            placeholder="Пароль"
                            value={password}
                            onChange={(event) =>
                                setPassword(event.target.value)
                            }
                            required
                        />

                        {authError && (
                            <div className="auth-error">
                                {authError}
                            </div>
                        )}

                        <button type="submit">
                            {isRegister
                                ? "Зарегистрироваться"
                                : "Войти"}
                        </button>
                    </form>

                    <button
                        className="auth-switch"
                        onClick={() => {
                            setIsRegister((prev) => !prev);
                            setAuthError("");
                        }}
                    >
                        {isRegister
                            ? "Уже есть аккаунт? Войти"
                            : "Нет аккаунта? Зарегистрироваться"}
                    </button>
                </div>
            </main>
        </div>
    );
}