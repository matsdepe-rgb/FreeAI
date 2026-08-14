# ✦ FreeAI - Gemini-Style ChatGPT Desktop Client

FreeAI is a modern, Gemini-inspired desktop application that wraps around a hidden, automated Google Chrome browser session running ChatGPT. It allows you to use ChatGPT locally through a slick UI, maintain chat history, and even host your own **Local OpenAI-Compatible API Server** (`/v1/chat/completions`) to route prompts from other apps—all completely free.

---

## ✨ Features

- **Gemini-Inspired UI:** Built with CustomTkinter for a sleek, dark-mode desktop experience.
- **Persistent Chat History:** Automatically saves your conversations locally (`chats.json`) with sidebar navigation and context restoration.
- **Real-Time Streaming:** Streams ChatGPT responses into the UI in real-time as they are generated.
- **Background Automation:** Automatically parks the automation browser off-screen so it stays active without throttling, with a manual **Show/Hide Chrome** toggle.
- **Local API Provider:** Turn your app into a local server (`http://127.0.0.1:5000/v1`) to use your free browser session as an API backend in other tools.
- **First-Time Calibration & Security Check:** Simple interactive checks to securely lock onto your active session.

---

## 🛠️ Prerequisites & Installation

1. Make sure you have **Python 3.10+** installed.
2. Install the required Python dependencies:
   ```bash
   pip install customtkinter selenium pygame pillow
   
This app was vibecoded completely with Gemini so expect bugs.
Also I would reccomend staying loggged out of ChatGPT so you dont get banned
