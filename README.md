# Workflow automation agent

## Installation

### 1. Clone the repository

```bash

git clone <repository-url>
cd <repository-name>
```

### 2. Installation

```bash
uv sync
```

### 5. Configure environment variables
Create a `.env` file in the project root by copying `.env.example`:

```bash
copy .env.example .env
```

Open `.env` and fill in the required values, such as your LLM API key, base URL, and model name.

If `.env.example` is not provided, create `.env` manually and add the environment variables required by the application.


### 6. Run the application

```bash
uv run python run.py
```

### 7. Shutdown
Press Ctrl+C in the terminal running the application.

## Описание репозитория  
Репозиторий в разработке 🛠️
