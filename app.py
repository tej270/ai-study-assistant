import streamlit as st
from google import genai
from google.genai import types
import re
import sqlite3
import uuid
import json
import time
import os
from datetime import date, timedelta, datetime
from fpdf import FPDF

# ---------- Database ----------
def init_db():
    conn = sqlite3.connect("study_data.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, subject TEXT, task TEXT, due_date TEXT, done INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, session_id TEXT, role TEXT, content TEXT, timestamp TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS activity_log (
        user_id TEXT, date TEXT, PRIMARY KEY (user_id, date)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS session_tags (
        session_id TEXT PRIMARY KEY, user_id TEXT, tag TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS user_xp (
        user_id TEXT PRIMARY KEY, xp INTEGER DEFAULT 0
    )""")
    conn.commit(); conn.close()

def tag_session(user_id, session_id, tag):
    conn = sqlite3.connect("study_data.db")
    conn.execute("INSERT OR IGNORE INTO session_tags (session_id, user_id, tag) VALUES (?, ?, ?)", (session_id, user_id, tag))
    conn.commit(); conn.close()

def get_sessions(user_id):
    conn = sqlite3.connect("study_data.db")
    rows = conn.execute("""SELECT ch.session_id, MIN(ch.timestamp), COUNT(*), st.tag
                            FROM chat_history ch LEFT JOIN session_tags st ON ch.session_id = st.session_id
                            WHERE ch.user_id = ?
                            GROUP BY ch.session_id ORDER BY MIN(ch.timestamp) DESC""", (user_id,)).fetchall()
    conn.close(); return rows

def log_activity(user_id):
    conn = sqlite3.connect("study_data.db")
    conn.execute("INSERT OR IGNORE INTO activity_log (user_id, date) VALUES (?, ?)", (user_id, str(date.today())))
    conn.commit(); conn.close()

def get_streak(user_id):
    conn = sqlite3.connect("study_data.db")
    rows = conn.execute("SELECT date FROM activity_log WHERE user_id = ? ORDER BY date DESC", (user_id,)).fetchall()
    conn.close()
    dates = set(r[0] for r in rows)
    streak = 0
    check_date = date.today()
    while str(check_date) in dates:
        streak += 1
        check_date -= timedelta(days=1)
    return streak

def add_task(user_id, subject, task, due_date):
    conn = sqlite3.connect("study_data.db")
    conn.execute("INSERT INTO tasks (user_id, subject, task, due_date) VALUES (?, ?, ?, ?)", (user_id, subject, task, due_date))
    conn.commit(); conn.close()

def get_tasks(user_id):
    conn = sqlite3.connect("study_data.db")
    rows = conn.execute("SELECT id, subject, task, due_date, done FROM tasks WHERE user_id = ? ORDER BY due_date", (user_id,)).fetchall()
    conn.close(); return rows

def toggle_task(user_id, task_id, done):
    conn = sqlite3.connect("study_data.db")
    conn.execute("UPDATE tasks SET done = ? WHERE id = ? AND user_id = ?", (int(done), task_id, user_id))
    conn.commit(); conn.close()
    if done:
        log_activity(user_id)
        add_xp(user_id, 20)

def delete_task(user_id, task_id):
    conn = sqlite3.connect("study_data.db")
    conn.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    conn.commit(); conn.close()

def save_message(user_id, session_id, role, content):
    conn = sqlite3.connect("study_data.db")
    conn.execute("INSERT INTO chat_history (user_id, session_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
                 (user_id, session_id, role, content, datetime.now().isoformat()))
    conn.commit(); conn.close()
    log_activity(user_id)
    if role == "user":
        add_xp(user_id, 5)

def get_session_messages(session_id):
    conn = sqlite3.connect("study_data.db")
    rows = conn.execute("SELECT role, content FROM chat_history WHERE session_id = ? ORDER BY id", (session_id,)).fetchall()
    conn.close(); return [{"role": r, "content": c} for r, c in rows]

def add_xp(user_id, amount):
    conn = sqlite3.connect("study_data.db")
    conn.execute("INSERT INTO user_xp (user_id, xp) VALUES (?, 0) ON CONFLICT(user_id) DO NOTHING", (user_id,))
    conn.execute("UPDATE user_xp SET xp = xp + ? WHERE user_id = ?", (amount, user_id))
    conn.commit(); conn.close()

def get_xp(user_id):
    conn = sqlite3.connect("study_data.db")
    row = conn.execute("SELECT xp FROM user_xp WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row[0] if row else 0

def get_level_info(xp):
    levels = [(0, "🌱 Beginner"), (100, "📘 Learner"), (300, "🎯 Scholar"),
              (600, "🚀 Achiever"), (1000, "🏆 Master"), (1500, "👑 Legend")]
    current = levels[0]
    next_level = None
    for i, (threshold, name) in enumerate(levels):
        if xp >= threshold:
            current = (threshold, name)
            next_level = levels[i + 1] if i + 1 < len(levels) else None
    return current, next_level

def get_week_data(user_id):
    conn = sqlite3.connect("study_data.db")
    week_ago = str(datetime.now() - timedelta(days=7))
    chats = conn.execute(
        "SELECT content FROM chat_history WHERE role='user' AND user_id=? AND timestamp >= ?", (user_id, week_ago)
    ).fetchall()
    completed_tasks = conn.execute(
        "SELECT subject, task FROM tasks WHERE done=1 AND user_id=?", (user_id,)
    ).fetchall()
    conn.close()
    return [c[0] for c in chats], completed_tasks

def generate_weekly_recap(user_id):
    questions, tasks = get_week_data(user_id)
    if not questions and not tasks:
        return "Not enough activity yet this week to build a recap — come back after you've used the app a bit more!"
    questions_text = "\n".join([f"- {q}" for q in questions[:30]])
    tasks_text = "\n".join([f"- {t[0]}: {t[1]}" for t in tasks[:30]])
    prompt = f"""Based on this student's activity this week, write a short, encouraging weekly recap (4-6 sentences). Mention what topics/subjects they focused on, celebrate progress, and give one gentle suggestion for next week.

Questions they asked this week:
{questions_text if questions_text else "None"}

Tasks they completed:
{tasks_text if tasks_text else "None"}
"""
    result = generate_with_retry("gemini-flash-lite-latest", prompt)
    return result.text

def get_usage_stats(user_id):
    conn = sqlite3.connect("study_data.db")
    total_messages = conn.execute("SELECT COUNT(*) FROM chat_history WHERE role='user' AND user_id=?", (user_id,)).fetchone()[0]
    total_tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE user_id=?", (user_id,)).fetchone()[0]
    completed_tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE done=1 AND user_id=?", (user_id,)).fetchone()[0]
    total_sessions = conn.execute("SELECT COUNT(DISTINCT session_id) FROM chat_history WHERE user_id=?", (user_id,)).fetchone()[0]
    subjects = conn.execute(
        "SELECT tag, COUNT(*) FROM session_tags WHERE user_id=? GROUP BY tag ORDER BY COUNT(*) DESC", (user_id,)
    ).fetchall()
    conn.close()
    return {"messages": total_messages, "tasks_total": total_tasks, "tasks_done": completed_tasks,
            "sessions": total_sessions, "subjects": subjects}

def extract_youtube_url(text):
    match = re.search(r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]+)', text)
    return match.group(1) if match else None

def generate_with_retry(model, contents, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(model=model, contents=contents)
        except Exception:
            if attempt < max_retries - 1:
                st.toast(f"⏳ Server busy, retrying... ({attempt + 1}/{max_retries})")
                time.sleep(3)
            else:
                st.error("The AI is currently overloaded. Please try again in a minute.")
                st.stop()

def generate_flashcards(topic_or_notes):
    prompt = f"""Create exactly 5 flashcards for studying this content. Respond ONLY with valid JSON, no markdown formatting, no backticks, in this exact structure:
[{{"question": "...", "answer": "..."}}]

Content to make flashcards from:
{topic_or_notes}
"""
    result = generate_with_retry("gemini-flash-lite-latest", prompt)
    text = result.text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(text)

def text_to_pdf_bytes(text, title="My Notes"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 10, title)
    pdf.ln(4)
    pdf.set_font("Helvetica", size=12)
    safe_text = text.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 8, safe_text)
    return bytes(pdf.output())

@st.cache_data(ttl=86400)
def get_daily_tip(today_str):
    prompt = "Give me one short, punchy study tip or productivity hack for today. One or two sentences only, no preamble, no quotation marks."
    result = generate_with_retry("gemini-flash-lite-latest", prompt)
    return result.text.strip()

# ---------- Themes ----------
THEMES = {
    "🌙 Midnight": {"colors": ["#0f0f1a", "#1a1a2e", "#2d1b4e"], "text": "#f5f5f5", "accent": "#7c3aed", "panel": "#1a1c23",
                    "quote": "Deep focus happens after dark.", "doodles": ["✨", "🌙", "⭐"]},
    "☀️ Light":    {"colors": ["#ffffff", "#f0f4ff", "#e0ebff"], "text": "#1a1a1a", "accent": "#2563eb", "panel": "#f3f4f6",
                    "quote": "Clarity comes with clean space.", "doodles": ["☁️", "🌤️", "✨"]},
    "🌊 Ocean":    {"colors": ["#0a1f2e", "#0e3a53", "#145a7a"], "text": "#e0f2fe", "accent": "#06b6d4", "panel": "#132f42",
                    "quote": "Stay calm, keep flowing forward.", "doodles": ["🌊", "🐚", "🫧"]},
    "🌸 Sakura":   {"colors": ["#fff5f7", "#ffe4ec", "#ffd0e0"], "text": "#7a2e45", "accent": "#ec4899", "panel": "#ffe4ec",
                    "quote": "Soft effort, steady bloom.", "doodles": ["🌸", "🌷", "🦋"]},
    "💆 Self Care": {"colors": ["#faf3ff", "#f0e4ff", "#e5d4ff"], "text": "#4a2e5c", "accent": "#a855f7", "panel": "#f0e4ff",
                    "quote": "You deserve the same care you give others.", "doodles": ["🕯️", "🌷", "🧘"]},
    "💖 Self Love": {"colors": ["#fff0f3", "#ffd6e0", "#ffb3c6"], "text": "#7a1f3d", "accent": "#f43f5e", "panel": "#ffd6e0",
                    "quote": "Be gentle with yourself today.", "doodles": ["💖", "🌹", "✨"]},
    "🔮 Destiny":  {"colors": ["#1a0b2e", "#2e1065", "#4c1d95"], "text": "#ede9fe", "accent": "#a78bfa", "panel": "#2e1065",
                    "quote": "Trust the path you're carving.", "doodles": ["🔮", "✨", "🌟"]},
    "✈️ Travel":   {"colors": ["#ff9a56", "#ff6b9d", "#845ec2"], "text": "#fff", "accent": "#ff6b9d", "panel": "#c9506e",
                    "quote": "New places, new perspective.", "doodles": ["✈️", "🗺️", "🧭"]},
    "🌌 Galaxy":   {"colors": ["#0d0221", "#1a0b3d", "#3a0ca3"], "text": "#e0d9ff", "accent": "#a78bfa", "panel": "#1a0b3d",
                    "quote": "Think big, one star at a time.", "doodles": ["🌟", "🪐", "☄️"]},
    "🌕 Moon & Stars": {"colors": ["#03071e", "#0a1128", "#1b263b"], "text": "#e6e6fa", "accent": "#f4d35e", "panel": "#0a1128",
                    "quote": "Even the moon needs darkness to shine.", "doodles": ["🌕", "⭐", "🌠"]},
    "☕ Coffee":   {"colors": ["#2b1d16", "#4a2e22", "#6b4130"], "text": "#f5e6d8", "accent": "#c08552", "panel": "#3a2820",
                    "quote": "Warm mind, steady grind.", "doodles": ["☕", "📖", "🍂"]},
}

def apply_theme(name):
    t = THEMES[name]
    gradient = f"linear-gradient(135deg, {', '.join(t['colors'])})"
    doodle_html = "".join([
        f'<span class="doodle" style="left:{10+i*30}%; animation-delay:{i*2}s;">{d}</span>'
        for i, d in enumerate(t["doodles"])
    ])
    st.markdown(f"""
        <style>
        .stApp {{ background: {gradient}; background-attachment: fixed; color: {t['text']}; }}
        [data-testid="stChatMessage"] {{ background-color: rgba(255,255,255,0.1); backdrop-filter: blur(6px); border-radius: 12px; }}
        section[data-testid="stSidebar"] {{ background-color: {t['panel']}; }}
        section[data-testid="stSidebar"] * {{ color: {t['text']} !important; }}
        .stButton>button {{ background-color: {t['accent']}; color: white; border-radius: 8px; border: none; }}
        .doodle {{ position: fixed; top: 100%; font-size: 28px; opacity: 0.5; animation: floatUp 14s linear infinite; z-index: 0; pointer-events: none; }}
        @keyframes floatUp {{ 0% {{ transform: translateY(0) rotate(0deg); opacity: 0; }} 10% {{ opacity: 0.5; }} 90% {{ opacity: 0.5; }} 100% {{ transform: translateY(-110vh) rotate(20deg); opacity: 0; }} }}
        </style>
        {doodle_html}
    """, unsafe_allow_html=True)
    st.caption(f"💭 *{t['quote']}*")

# ---------- App setup ----------
st.set_page_config(page_title="My AI Assistant", page_icon="🤖", layout="centered")
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# ---------- LOGIN GATE ----------
if "user_id" not in st.session_state:
    st.title("🤖 Welcome to My AI Assistant")
    st.write("Enter a name to get your own personal space — your tasks, chats, and progress will be saved under it.")
    name_input = st.text_input("What should we call you?")
    if st.button("🚀 Enter app") and name_input.strip():
        st.session_state.user_id = name_input.strip().lower().replace(" ", "_")
        st.rerun()
    st.stop()

user_id = st.session_state.user_id
init_db()

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]
if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.header(f"👤 {user_id}")
    if st.button("🚪 Log out"):
        for key in ["user_id", "session_id", "messages"]:
            st.session_state.pop(key, None)
        st.rerun()

    streak = get_streak(user_id)
    st.markdown(f"### 🔥 {streak} day streak" if streak > 0 else "### 🌱 Start your streak today!")

    xp = get_xp(user_id)
    (threshold, level_name), next_level = get_level_info(xp)
    st.markdown(f"### {level_name}")
    if next_level:
        progress = (xp - threshold) / (next_level[0] - threshold)
        st.progress(min(progress, 1.0))
        st.caption(f"{xp} XP · {next_level[0] - xp} XP to {next_level[1]}")
    else:
        st.caption(f"{xp} XP · Max level reached!")

    st.divider()
    theme_names = list(THEMES.keys())
    default_index = theme_names.index(st.session_state.get("pending_theme", theme_names[0]))
    theme_choice = st.selectbox("🎨 Theme", theme_names, index=default_index, key="theme")
    apply_theme(theme_choice)

    with st.expander("✨ Not sure? Take a quick vibe quiz"):
        q1 = st.radio("Pick a vibe:", ["🌙 Calm & focused", "🌊 Fresh & clear-headed", "🌸 Soft & creative", "🔥 Bold & energetic", "🌲 Grounded & steady"])
        q2 = st.radio("When do you study best?", ["Late night", "Early morning", "Afternoon", "Whenever, I'm flexible"])
        q3 = st.radio("Pick a color that speaks to you:", ["Purple", "Blue", "Pink", "Orange/Red", "Green"])
        if st.button("🎯 Get my theme"):
            theme_options = "\n".join([f"- {name}: {info['quote']}" for name, info in THEMES.items()])
            quiz_prompt = f"Based on these answers, pick the ONE best matching theme name from this exact list (respond with ONLY the theme name, nothing else):\n\n{theme_options}\n\nAnswers:\n- Vibe: {q1}\n- Study time: {q2}\n- Favorite color: {q3}"
            with st.spinner("Reading your vibe..."):
                result = generate_with_retry("gemini-flash-lite-latest", quiz_prompt)
            matched = next((name for name in THEMES if name in result.text.strip()), None)
            if matched:
                st.session_state.pending_theme = matched
                st.success(f"Your vibe is: {matched}")
                st.rerun()
            else:
                st.warning("Couldn't match a theme, try again!")

    st.divider()
    if st.button("🆕 New chat"):
        st.session_state.session_id = str(uuid.uuid4())[:8]
        st.session_state.messages = []
        st.rerun()

    st.subheader("🕘 Past Sessions")
    all_sessions = get_sessions(user_id)
    all_tags = sorted(set(s[3] for s in all_sessions if s[3]))
    tag_filter = st.selectbox("Filter by subject", ["All"] + all_tags)
    filtered = [s for s in all_sessions if tag_filter == "All" or s[3] == tag_filter]
    for sess_id, started, count, tag in filtered[:10]:
        tag_label = f"[{tag}] " if tag else ""
        label = f"{tag_label}{started[:16].replace('T', ' ')} · {count} msgs"
        if st.button(label, key=f"sess_{sess_id}"):
            st.session_state.session_id = sess_id
            st.session_state.messages = get_session_messages(sess_id)
            st.rerun()

    st.divider()
    st.subheader("📎 Upload a file")
    uploaded_file = st.file_uploader("Upload a PDF or a photo", type=["pdf", "png", "jpg", "jpeg"])
    if uploaded_file:
        st.success(f"Attached: {uploaded_file.name}")

st.title("🤖 My AI Assistant")
tip = get_daily_tip(str(date.today()))
st.markdown(f"""
    <div style="padding:12px 16px; border-radius:10px; margin-bottom:16px;
                background:rgba(255,255,255,0.08); border-left:4px solid currentColor;">
        💡 <b>Today's tip:</b> {tip}
    </div>
""", unsafe_allow_html=True)

tab1, tab2, tab3, tab4, tab5 = st.tabs(["💬 Chat", "📅 Planner", "🗂️ Flashcards", "📊 Recap", "📈 Stats"])

# ---------- TAB 1: CHAT ----------
with tab1:
    if not st.session_state.messages:
        st.markdown("### 👋 What do you want to work on?")
        suggestions = [
            "📚 Explain a topic I'm stuck on, step by step",
            "📄 I'll upload a PDF — summarize the key points",
            "🎥 Give me notes from a YouTube lecture link",
            "🗓️ Help me plan my study session for today",
        ]
        cols = st.columns(2)
        for i, s in enumerate(suggestions):
            if cols[i % 2].button(s, key=f"suggest_{i}", use_container_width=True):
                st.session_state.queued_prompt = s.split(" ", 1)[1]
                st.rerun()
        st.divider()

    for i, msg in enumerate(st.session_state.messages):
        st.chat_message(msg["role"]).write(msg["content"])
        if msg["role"] == "assistant":
            pdf_bytes = text_to_pdf_bytes(msg["content"])
            st.download_button("📥 Download as PDF", data=pdf_bytes, file_name=f"notes_{i}.pdf", mime="application/pdf", key=f"pdf_{i}")

    audio_value = st.audio_input("🎙️ Or ask by voice")

    prompt = st.chat_input("Ask a question, upload a file, or paste a YouTube link...")
    if not prompt and "queued_prompt" in st.session_state:
        prompt = st.session_state.pop("queued_prompt")

    voice_mode = False
    if not prompt and audio_value is not None:
        prompt = "🎤 Voice message"
        voice_mode = True

    if prompt:
        is_first_message = len(st.session_state.messages) == 0
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)
        save_message(user_id, st.session_state.session_id, "user", prompt)

        if is_first_message:
            tag_prompt = f"In ONE word (like Math, Physics, Chemistry, Biology, History, English, General), what subject does this question relate to: '{prompt}'"
            tag_result = generate_with_retry("gemini-flash-lite-latest", tag_prompt)
            tag_session(user_id, st.session_state.session_id, tag_result.text.strip())

        contents = []
        for m in st.session_state.messages[:-1]:
            role = "user" if m["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=m["content"])]))

        if voice_mode:
            current_parts = [
                types.Part.from_text(text="Listen to this audio. Do NOT just transcribe it. Instead, understand what I'm asking or saying, and respond directly to it as if I typed it to you as a message, the same way you'd normally reply in this conversation."),
                types.Part.from_bytes(data=audio_value.getvalue(), mime_type="audio/wav")
            ]
        else:
            current_parts = [types.Part.from_text(text=prompt)]

        youtube_url = extract_youtube_url(prompt)
        if youtube_url:
            current_parts.append(types.Part.from_uri(file_uri=youtube_url, mime_type="video/mp4"))
        if uploaded_file is not None:
            current_parts.append(types.Part.from_bytes(data=uploaded_file.getvalue(), mime_type=uploaded_file.type))
        contents.append(types.Content(role="user", parts=current_parts))

        with st.spinner("Thinking..."):
            response = generate_with_retry("gemini-flash-lite-latest", contents)

        st.session_state.messages.append({"role": "assistant", "content": response.text})
        save_message(user_id, st.session_state.session_id, "assistant", response.text)
        st.chat_message("assistant").write(response.text)

# ---------- TAB 2: PLANNER ----------
with tab2:
    st.subheader("Add a task")
    with st.form("add_task_form", clear_on_submit=True):
        task_name = st.text_input("Task / Topic (e.g. 'Newton's laws of motion')")
        due_date = st.date_input("Due date")
        if st.form_submit_button("Add task") and task_name:
            with st.spinner("Detecting subject..."):
                subject_prompt = f"In ONE word only (like Math, Physics, Chemistry, Biology, History, English, Computer Science), what subject does this topic belong to: '{task_name}'"
                subject_result = generate_with_retry("gemini-flash-lite-latest", subject_prompt)
                subject = subject_result.text.strip()
            add_task(user_id, subject, task_name, str(due_date))
            st.success(f"Task added under **{subject}**!")
            st.rerun()

    st.divider()
    tasks = get_tasks(user_id)

    if tasks:
        done_count = sum(1 for t in tasks if t[4])
        st.progress(done_count / len(tasks))
        st.caption(f"{done_count} of {len(tasks)} tasks completed")
        pct = done_count / len(tasks)
        if pct == 1: mood = "🎉 Everything done — you're on fire!"
        elif pct >= 0.7: mood = "🚀 Almost there, keep pushing!"
        elif pct >= 0.3: mood = "💪 Good progress, stay consistent."
        else: mood = "🌱 Just getting started — one task at a time."
        st.markdown(f"#### {mood}")

    st.subheader("Your tasks")
    for task_id, subj, task_name, due, done in tasks:
        col1, col2, col3 = st.columns([0.1, 0.75, 0.15])
        with col1:
            checked = st.checkbox("", value=bool(done), key=f"chk_{task_id}")
            if checked != bool(done):
                toggle_task(user_id, task_id, checked)
                if checked: st.balloons()
                st.rerun()
        with col2:
            style = "opacity:0.5; text-decoration: line-through;" if done else ""
            st.markdown(f"""<div style="padding:8px 12px; border-radius:8px; margin-bottom:4px; background:rgba(255,255,255,0.06); border-left:3px solid currentColor; {style}"><b>{subj}</b> — {task_name} <span style="opacity:0.7;">(due {due})</span></div>""", unsafe_allow_html=True)
        with col3:
            if st.button("🗑️", key=f"del_{task_id}"):
                delete_task(user_id, task_id)
                st.rerun()

    st.divider()
    if st.button("✨ Generate AI timetable from my pending tasks"):
        pending = [t for t in tasks if not t[4]]
        if pending:
            task_list_text = "\n".join([f"- {t[1]}: {t[2]} (due {t[3]})" for t in pending])
            timetable_prompt = f"Based on these pending study tasks, create a realistic day-by-day study timetable with specific time slots, up until the earliest due date:\n\n{task_list_text}"
            with st.spinner("Creating your timetable..."):
                response = generate_with_retry("gemini-flash-lite-latest", timetable_prompt)
            st.markdown(response.text)
        else:
            st.info("Add some tasks first, or mark ones incomplete to include them.")

# ---------- TAB 3: FLASHCARDS ----------
with tab3:
    st.subheader("Generate flashcards")
    topic_input = st.text_area("Paste your notes, or just type a topic:", height=120)
    if st.button("✨ Generate flashcards"):
        if topic_input.strip():
            with st.spinner("Creating flashcards..."):
                try:
                    st.session_state.flashcards = generate_flashcards(topic_input)
                    st.session_state.flip_states = [False] * len(st.session_state.flashcards)
                except Exception:
                    st.error("Couldn't generate flashcards, try rephrasing your input.")
        else:
            st.info("Type a topic or paste some notes first.")
    st.divider()
    if "flashcards" in st.session_state and st.session_state.flashcards:
        for i, card in enumerate(st.session_state.flashcards):
            shown_text = card["answer"] if st.session_state.flip_states[i] else card["question"]
            label = "💡 Answer" if st.session_state.flip_states[i] else "❓ Question"
            st.markdown(f"""<div style="padding:20px; border-radius:14px; margin-bottom:10px; background:rgba(255,255,255,0.07); border:1px solid rgba(255,255,255,0.15); min-height:80px;"><div style="opacity:0.6; font-size:0.8em; margin-bottom:6px;">{label} · Card {i+1}</div><div style="font-size:1.05em;">{shown_text}</div></div>""", unsafe_allow_html=True)
            if st.button("🔄 Flip", key=f"flip_{i}"):
                st.session_state.flip_states[i] = not st.session_state.flip_states[i]
                st.rerun()

# ---------- TAB 4: RECAP ----------
with tab4:
    st.subheader("Your weekly recap")
    st.caption("A look back at what you've worked on recently.")
    if st.button("✨ Generate my weekly recap"):
        with st.spinner("Looking back at your week..."):
            recap = generate_weekly_recap(user_id)
        st.markdown(f"""<div style="padding:20px; border-radius:14px; background:rgba(255,255,255,0.08); line-height:1.6;">{recap}</div>""", unsafe_allow_html=True)

# ---------- TAB 5: STATS ----------
with tab5:
    st.subheader("Your usage stats")
    stats = get_usage_stats(user_id)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💬 Questions asked", stats["messages"])
    col2.metric("🗂️ Chat sessions", stats["sessions"])
    col3.metric("✅ Tasks completed", stats["tasks_done"])
    col4.metric("📋 Total tasks", stats["tasks_total"])
    st.divider()
    if stats["subjects"]:
        st.subheader("Subjects you've explored")
        for subject, count in stats["subjects"]:
            st.markdown(f"**{subject}**")
            st.progress(min(count / max(c for _, c in stats["subjects"]), 1.0))
    else:
        st.info("Chat a bit more to start seeing subject breakdowns here!")