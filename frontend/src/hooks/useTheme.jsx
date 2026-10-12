import { useEffect, useState } from "react";

export function useTheme() {
    const [darkMode, setDarkMode] = useState(
        () => localStorage.getItem("theme") === "dark"
    );

    useEffect(() => {
        document.body.className = darkMode ? "dark" : "light";
        localStorage.setItem("theme", darkMode ? "dark" : "light");
    }, [darkMode]);

    function toggleTheme() {
        setDarkMode((prev) => !prev);
    }

    return { darkMode, toggleTheme };
}
