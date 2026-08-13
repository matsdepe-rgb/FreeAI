import openai

# Configure the client to point to your local server
client = openai.OpenAI(
    base_url="http://127.0.0.1:5000/v1",
    api_key="sk-freeai-vrlRAHS5Z9dTPdQXw6xcaZllFAPosaHc"  # Replace with your actual key from the app
)

response = client.chat.completions.create(
    model="freeai-browser-engine",
    messages=[{"role": "user", "content": "Hello! Can you hear me?"}]
)

print(response.choices[0].message.content)