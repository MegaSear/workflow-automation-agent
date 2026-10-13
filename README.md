## Требования

- Windows (скрипт запуска `run.py` использует `taskkill` и `npm.cmd`)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (PostgreSQL и песочница агента)
- [Node.js](https://nodejs.org/) (фронтенд)
- [uv](https://docs.astral.sh/uv/) (менеджер зависимостей Python)

## Установка

### 1. Клонировать репозиторий

```powershell
git clone https://github.com/MegaSear/workflow-automation-agent.git
cd workflow-automation-agent
```

### 2. Установить зависимости Python

```powershell
uv sync
```

uv сам создаст `.venv` и поставит версии из `uv.lock`.

### 3. Установить зависимости фронтенда

```powershell
cd frontend
npm install
cd ..
```

### 4. Настроить переменные окружения

```powershell
copy .env.example .env
```

Открой `.env` и заполни `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` и `JWT_SECRET_KEY`.

### 5. Запустить

```powershell
uv run python run.py
```

Остановить: `Ctrl+C` в терминале.

## Тесты

```powershell
uv run pytest
```

### 6. Описание репозитория  

Репозиторий в разработке 🛠️