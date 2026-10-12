import { API_BASE_URL } from "./config";

export async function login(email, password) {
    return authenticate("/api/auth/login", email, password);
}

export async function register(email, password) {
    return authenticate("/api/auth/register", email, password);
}

async function authenticate(endpoint, email, password) {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, 
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ email, password }),
        }
    );

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.detail || "Ошибка авторизации");
    }

    return data;
}
