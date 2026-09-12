import os
from dotenv import load_dotenv
import httpx

load_dotenv()

response = httpx.post(
    "https://api.deepseek.com/chat/completions",
    headers={
        "Authorization": f"Bearer {os.getenv('LLM_API_KEY')}",
        "Content-Type": "application/json"
    },
    json={
        "model": "deepseek-v4-pro",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "用一句话介绍python"}
        ]
    },
    timeout=30.0
)

data = response.json()
print(data)

# 只需要内容
print(data["choices"][0]["message"]["content"])

# 只需要打印花费的token
print(data["usage"]["total_tokens"])

import asyncio


async def chat(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('LLM_API_KEY')}",
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]


# 在 FastAPI 中可直接 `await chat("...")` 不阻塞其他请求
result = asyncio.run(chat("用一句话介绍 Python"))
print(result)
