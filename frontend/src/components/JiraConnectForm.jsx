import { useState } from "react";

export default function JiraConnectForm({ connectJira, busy, onSuccess }) {
  const [baseUrl, setBaseUrl] = useState("");
  const [email, setEmail] = useState("");
  const [apiToken, setApiToken] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();

    const connected = await connectJira({
      base_url: baseUrl.trim(),
      email: email.trim(),
      api_token: apiToken,
    });

    if (connected) {
      setApiToken("");
      onSuccess();
    }
  }

  return (
    <form className="jira-form" onSubmit={handleSubmit}>
      <label>
        URL Jira
        <input
          type="url"
          placeholder="https://company.atlassian.net"
          value={baseUrl}
          onChange={(event) => setBaseUrl(event.target.value)}
          required
        />
      </label>

      <label>
        Email
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
      </label>

      <label>
        API token
        <input
          type="password"
          autoComplete="off"
          value={apiToken}
          onChange={(event) => setApiToken(event.target.value)}
          required
        />
      </label>

      <button type="submit" className="jira-submit" disabled={Boolean(busy)}>
        {busy === "jira" ? "Проверка..." : "Сохранить и подключить"}
      </button>
    </form>
  );
}
