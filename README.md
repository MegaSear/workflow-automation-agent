## Требования

- OS: Windows
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) - запуск PostgreSQL и песочницы агента
- [Node.js](https://nodejs.org/) - запуск фронтенда
- [uv](https://docs.astral.sh/uv/) - управление зависимостями и виртуальным окружением Python  
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

uv создаст виртуальное окружение `.venv` и установит зависимости из `uv.lock`.

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
Заполнить в `.env` параметры `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` и `JWT_SECRET_KEY`. JWT_SECRET_KEY должен быть не короче 32 байт.

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