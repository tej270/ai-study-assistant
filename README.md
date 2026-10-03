# 🤖 My AI Study Assistant

A multimodal AI-powered study companion built from scratch — chat with memory, understand documents/images/YouTube videos, generate flashcards, track study progress, and more. Built as a personal learning project to explore LLM APIs, app architecture, and product design.

**🔗 Live demo:** [ai-study-assistant.streamlit.app](https://ai-study-assistant-gtwdtqsgosw43jdplbn5f2.streamlit.app/)
*(Note: this is a free-tier demo — data may reset periodically since it doesn't use persistent cloud storage.)*

---

## ✨ Features

- **💬 Conversational AI chat** with full memory across a session, powered by Google's Gemini API
- **📄 Document understanding** — upload a PDF and ask questions or get a summary, no OCR needed
- **🖼️ Image understanding** — snap a photo of a handwritten problem or textbook page and ask for help
- **🎥 YouTube video summarizer** — paste a link, get key points and notes pulled directly from the video
- **🎙️ Voice input** — ask questions by speaking instead of typing
- **📅 Smart planner** — add study tasks (subject auto-detected by AI), track completion, and generate an AI-built study timetable
- **🗂️ AI flashcard generator** — turns any topic or pasted notes into flip-through flashcards
- **📥 Export to PDF** — download any AI response as a clean PDF for offline review
- **📊 Weekly recap** — AI-generated summary of what you studied and accomplished
- **📈 Usage dashboard** — stats on questions asked, tasks completed, and subjects explored
- **🔥 Streaks & XP system** — gamified progress tracking with levels (Beginner → Legend)
- **🎨 Custom themes** — 11 aesthetic themes with gradients and animated doodles, plus an AI-powered "vibe quiz" that recommends a theme based on your personality
- **👤 Multi-user support** — simple name-based login keeps everyone's data separate
- **🕘 Session history** — past conversations are saved and tagged by subject, filterable from the sidebar

---

## 🛠️ Tech stack

- **Python** — core language
- **Streamlit** — web app framework and UI
- **Google Gemini API** (`google-genai`) — LLM for chat, document/image/video understanding, and audio transcription
- **SQLite** — lightweight local database for tasks, chat history, XP, and streaks
- **FPDF2** — PDF generation for note exports

---

## 🚀 Running it locally

1. Clone this repo:
   ```bash
   git clone https://github.com/YOUR_USERNAME/ai-study-assistant.git
   cd ai-study-assistant
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Get a free Gemini API key from [Google AI Studio](https://aistudio.google.com), then set it as an environment variable:
   ```bash
   # Windows (PowerShell)
   $env:GEMINI_API_KEY="your_key_here"

   # Mac/Linux
   export GEMINI_API_KEY="your_key_here"
   ```

4. Run the app:
   ```bash
   streamlit run app.py
   ```

---

## 📌 What I learned building this

This project started as a simple terminal chatbot and grew into a full-featured app, one piece at a time. Along the way I learned:
- Working with LLM APIs (prompting, multimodal inputs, handling rate limits/errors gracefully)
- Designing and querying a relational database (SQLite) for persistent app state
- Building a real UI/UX with Streamlit, including session state management
- Debugging real deployment issues (dependency management, environment-specific bugs)
- Thinking about product details like gamification, theming, and multi-user data separation

---

## 🔮 Possible future improvements

- Proper authentication (passwords) instead of name-only login
- Persistent cloud database so data survives redeploys
- Mobile-responsive polish
- Shareable flashcard decks between users

---

## 📬 Connect

Built by Tejasvi M —
 [LinkedIn](https://linkedin.com/in/tejasvi-m007) ·
 [GitHub](https://github.com/tej270)
