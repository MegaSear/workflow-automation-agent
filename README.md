## Требования

- OS: Windows
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) - запуск всего приложения
- [uv](https://docs.astral.sh/uv/) и [Node.js](https://nodejs.org/) нужны только для локальной разработки вне Docker
## Установка

### 1. Клонировать репозиторий

```powershell
git clone https://github.com/MegaSear/workflow-automation-agent.git
cd workflow-automation-agent
```

### 2. Настроить переменные окружения

```powershell
copy .env.example .env
```
Заполнить в `.env` параметры `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` и `JWT_SECRET_KEY`. JWT_SECRET_KEY должен быть не короче 32 байт.

Для интеграций также задайте `INTEGRATION_ENCRYPTION_KEY`. Сгенерировать ключ можно командой:

```powershell
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Добавьте этот ключ в `.env` и храните его отдельно от резервных копий базы данных. Google OAuth client должен находиться в `secrets/google_web_credentials.json`, а в Google Cloud Console должен быть разрешён redirect URI `http://localhost:8000/api/integrations/google_calendar/callback`.

MCP server registry загружается из `src/react_agent/backend/mcp/mcp_config.yaml`. MCP manager вызывает `list_tools()` у каждого сервера по Streamable HTTP и передаёт модели полученные от серверов схемы; вызовы инструментов также идут через MCP URL. `my_default` — отдельный сервис Docker Compose, доступный backend только по внутреннему URL `http://my-default:8001/mcp`; он содержит ваши инструменты и работает с изолированной песочницей. Сервис требует общий секрет `MY_DEFAULT_MCP_TOKEN`; backend передаёт его и ID workspace в служебных HTTP-заголовках, а не в параметрах инструментов. Jira, Google Calendar и GitHub подключаются к указанным удалённым MCP серверам.

Во время ответа раскройте `Thinking...`, чтобы видеть вызовы инструментов и их текущий статус. Это список действий инструментов, а не скрытые рассуждения модели. Трассировка сохраняется с сообщением и доступна при повторном открытии диалога.

Для снижения расхода TPM GitHub MCP ограничен четырьмя инструментами из allowlist в конфигурации сервера. История чата ограничена 2000 символами, а `LLM_MAX_COMPLETION_TOKENS` по умолчанию равен 1024; увеличивайте лимиты только если провайдер и модель это позволяют.

OpenAI-совместимые параметры генерации можно задать в `.env`: `LLM_TEMPERATURE` (0–2), `LLM_TOP_P` (больше 0 и до 1), `LLM_FREQUENCY_PENALTY` и `LLM_PRESENCE_PENALTY` (−2…2), `LLM_SEED`, `LLM_REASONING_EFFORT` (`low`, `medium`, `high`). Пустые значения не отправляются провайдеру. `top_k` намеренно не добавлен: он не является параметром OpenAI-compatible Chat Completions, используемого проектом; передача его Groq может привести к отказу API. Доступность каждого параметра зависит от выбранной модели.

Подключите GitHub PAT и Jira credentials в разделе интеграций приложения; Google Calendar подключается через OAuth 2.0. Секреты хранятся зашифрованными в базе и передаются соответствующим удалённым MCP-серверам в заголовке авторизации. Для внешних серверов используйте HTTPS. Сервис `my-default` и backend имеют доступ к Docker socket для изолированных sandbox-контейнеров; Compose не публикует порт MCP сервера на хост.

### 3. Запустить все сервисы

```powershell
docker compose up --build -d --wait
```

Frontend: http://localhost:5173. Backend API: http://localhost:8000. Prometheus: http://localhost:9090. Grafana: http://localhost:3000.

Если host-порт PostgreSQL `5432` занят, поменяйте `POSTGRES_PORT` в `.env`, например на `5433`; между Compose-сервисами база по-прежнему доступна на порту `5432`.

Backend использует Docker socket для запуска изолированных sandbox-контейнеров. Это даёт ему доступ к Docker daemon, поэтому используйте этот Compose setup только на доверенной машине.

Остановить сервисы: `docker compose down`. Данные PostgreSQL сохраняются в Docker volume.

Для разработки без Docker установите Python-зависимости командой `uv sync`, а frontend-зависимости из `src/react_agent/frontend` командой `npm install`.

## Тесты

```powershell
uv run pytest
```

### 4. Описание репозитория

Репозиторий в разработке 🛠️