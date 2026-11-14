@'
import os
import requests
from dotenv import load_dotenv

load_dotenv(".env")

base_url = os.environ["LLM_BASE_URL"].rstrip("/")
if base_url.endswith("/v1"):
    base_url = base_url[:-3]

api_key = os.environ["LLM_API_KEY"]
model = os.environ["LLM_MODEL"]

headers = {"Authorization": f"Bearer {api_key}"}

response = requests.get(
    f"{base_url}/v1/models",
    headers=headers,
    timeout=30,
)
print("HTTP:", response.status_code)
print(response.json())

response = requests.post(
    f"{base_url}/v1/chat/completions",
    headers=headers,
    json={
        "model": model,
        "messages": [
            {"role": "user", "content": "What is the difference between an LLM and an LLM agent?"}
        ],
        "max_tokens": 150,
        "temperature": 0.2,
    },
    timeout=180,
)
response.raise_for_status()
print(response.json()["choices"][0]["message"]["content"])
'@ | python