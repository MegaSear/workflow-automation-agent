import { useState } from "react";

export default function GitHubConnectForm({ connectGitHub, busy, onSuccess }) {
  const [accessToken, setAccessToken] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();

    if (await connectGitHub(accessToken)) {
      setAccessToken("");
      onSuccess();
    }
  }

  return (
    <form className="jira-form" onSubmit={handleSubmit}>
      <label>
        GitHub personal access token
        <input
          type="password"
          autoComplete="off"
          value={accessToken}
          onChange={(event) => setAccessToken(event.target.value)}
          required
        />
      </label>

      <button type="submit" className="jira-submit" disabled={Boolean(busy)}>
        {busy === "github" ? "Проверка..." : "Сохранить и подключить"}
      </button>
    </form>
  );
}
