import { useCallback, useState } from "react";
import { login, register } from "../api/auth";

export function useAuth() {
  const [token, setToken] = useState(() =>
    localStorage.getItem("access_token"),
  );

  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");

  async function handleAuth(event) {
    event.preventDefault();
    setAuthError("");

    try {
      const data = isRegister
        ? await register(email, password)
        : await login(email, password);

      localStorage.setItem("access_token", data.access_token);
      setToken(data.access_token);

      setEmail("");
      setPassword("");
    } catch (error) {
      setAuthError(error.message);
    }
  }

  const logout = useCallback(() => {
    localStorage.removeItem("access_token");
    setToken(null);
  }, []);

  return {
    token,
    isRegister,
    setIsRegister,
    email,
    setEmail,
    password,
    setPassword,
    authError,
    setAuthError,
    handleAuth,
    logout,
  };
}
