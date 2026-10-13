import AuthForm from "./components/AuthForm";
import ChatApp from "./components/ChatApp";

import { useTheme } from "./hooks/useTheme";
import { useAuth } from "./hooks/useAuth";

import "./index.css";

function App() {
    const auth = useAuth();
    const { darkMode, toggleTheme } = useTheme();

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
        <ChatApp
            token={auth.token}
            logout={auth.logout}
            darkMode={darkMode}
            toggleTheme={toggleTheme}
        />
    );
}

export default App;