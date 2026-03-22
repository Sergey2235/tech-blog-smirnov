import streamlit as st
import requests
from github import Github
from datetime import datetime
import sqlite3
import pandas as pd

# --- База данных ---
def init_db():
    conn = sqlite3.connect("data.db")
    conn.execute("CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, repo TEXT, mode TEXT, status TEXT, time TEXT)")
    conn.commit()
    conn.close()

init_db()

# --- Настройки страницы ---
st.set_page_config(page_title="LLM Code Auditor", page_icon="🤖")

# Токен и настройки
TOKEN = "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"

st.title("🤖 LLM Code Quality Automation")
st.markdown("---")

# --- Боковая панель (Настройки) ---
with st.sidebar:
    st.header("⚙️ Настройки LLM")
    url_llm = st.text_input("DeepSeek URL", "http://127.0.0.1:1234/v1/chat/completions")
    model = st.text_input("Модель", "deepseek-r1-distill-qwen-14b")
    tokens = st.number_input("Лимит токенов", 100, 16000, 4000)
    temp = st.slider("Температура (креативность)", 0.0, 1.0, 0.3)
    
    st.divider()
    st.info("Приложение проверит файлы .py и создаст отчет в GitHub")

# --- Основной интерфейс ---
tabs = st.tabs(["🚀 Запуск", "📜 История проверок"])

with tabs[0]:
    repo_url = st.text_input("Ссылка на GitHub репозиторий:", "https://github.com/Sergey2235/-Ser")
    mode = st.selectbox("Режим анализа:", ["Полный аудит", "Поиск уязвимостей", "Чистота кода"])
    
    if st.button("🔥 Запустить анализ и отправить коммит", use_container_width=True):
        try:
            # 1. Доступ к GitHub
            st.write("📡 Подключаюсь к GitHub...")
            g = Github(TOKEN)
            repo_name = repo_url.split("github.com/")[-1].strip("/")
            repo = g.get_repo(repo_name)
            
            # 2. Чтение кода
            st.write("📂 Собираю файлы...")
            files = repo.get_contents("")
            code_content = ""
            for f in files:
                if f.name.endswith(".py"):
                    code_content += f"\n\n# --- FILE: {f.name} ---\n"
                    code_content += f.decoded_content.decode()[:3000] # Берем начало файла
            
            if not code_content:
                st.error("В репозитории нет Python файлов!")
            else:
                # 3. Запрос к DeepSeek
                st.write("🧠 DeepSeek анализирует код...")
                prompt = f"Ты эксперт. Проведи {mode}. Найди ошибки и предложи исправления для этого кода:\n{code_content}"
                
                res = requests.post(url_llm, json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": tokens,
                    "temperature": temp
                }, timeout=300)
                
                if res.status_code == 200:
                    report = res.json()['choices'][0]['message']['content']
                    st.success("✅ Анализ готов!")
                    st.expander("Посмотреть отчет").markdown(report)
                    
                    # 4. Коммит в GitHub
                    st.write("✍️ Записываю коммит в репозиторий...")
                    filename = f"audits/report_{datetime.now().strftime('%H%M%S')}.md"
                    repo.create_file(
                        path=filename,
                        message=f"LLM Audit: {mode}",
                        content=report,
                        branch="main"
                    )
                    st.balloons()
                    st.success(f"🚀 Отчет успешно сохранен: {filename}")
                    
                    # 5. Сохранение в историю
                    conn = sqlite3.connect("data.db")
                    conn.execute("INSERT INTO audit_logs (repo, mode, status, time) VALUES (?, ?, ?, ?)",
                               (repo_name, mode, "Успешно", datetime.now().strftime("%Y-%m-%d %H:%M")))
                    conn.commit()
                    conn.close()
                else:
                    st.error(f"Ошибка LLM сервера: {res.status_code}")
        
        except Exception as e:
            st.error(f"Произошла ошибка: {e}")

with tabs[1]:
    st.header("История")
    conn = sqlite3.connect("data.db")
    df = pd.read_sql_query("SELECT * FROM audit_logs ORDER BY id DESC", conn)
    st.dataframe(df, use_container_width=True)
    conn.close()

