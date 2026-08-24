from ollama import chat

response = chat(
    model="qwen3:8b",
    messages=[
        {
            "role": "user",
            "content": "Say hello like a futuristic AI assistant."
        }
    ],
)

print(response.message.content)