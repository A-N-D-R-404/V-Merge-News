import feedparser
import json
import os
import sys
import requests
import time
from pollinations import Pollinations

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
STATE_FILE = "published_news.json"
RSS_URL = "https://news.google.com/rss/search?q=VPN&hl=ru&gl=RU&ceid=RU:ru"

pollinations_client = Pollinations()

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"published_ids": []}

def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False)

def ask_ai(prompt_text):
    try:
        print("Отправка запроса к ИИ...")
        time.sleep(3) 
        response = pollinations_client.generate_text(
            prompt_text,
            model="openai",
            system="Ты — редактор VPN-канала. Пиши кратко, интересно и с эмодзи. Обязательно используй Markdown для ссылок."
        )
        return response
    except Exception as e:
        print(f"Ошибка ИИ Pollinations: {e}")
        return None

def main():
    if not TELEGRAM_TOKEN or not CHANNEL_ID:
        print("Ошибка: Не заданы TELEGRAM_BOT_TOKEN или TELEGRAM_CHANNEL_ID")
        return

    print("Загрузка новостей...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(RSS_URL, headers=headers, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при скачивании новостей: {e}")
        return

    feed = feedparser.parse(response.text)
    
    if not feed.entries:
        print("Новости не найдены.")
        return

    state = load_state()
    new_articles = []
    
    for entry in feed.entries[:5]: 
        news_id = entry.get('id', entry.get('link', entry.title))
        
        if news_id not in state["published_ids"]:
            new_articles.append(entry)
            state["published_ids"].append(news_id)

    if not new_articles:
        print("Новых новостей нет.")
        return

    print(f"Найдено новых новостей: {len(new_articles)}. Отправляем в ИИ...")
    
    # Формируем текст для ИИ так, чтобы он видел ссылки
    news_text = ""
    for a in new_articles:
        # Берем ссылку на статью
        link = a.get('link', '')
        title = a.get('title', '')
        news_text += f"- Заголовок: {title}\n  Ссылка: {link}\n"

    # ПРОМПТ: Просим сделать список с кликабельными ссылками
    prompt = (
        f"Ниже список новостей. Сделай из них краткую сводку в виде списка (каждый пункт с новой строки). "
        f"В каждом пункте ОБЯЗАТЕЛЬНО сделай кликабельную ссылку на источник в формате Markdown: [Название](URL). "
        f"Не пиши вводных слов, только сами пункты с эмодзи:\n{news_text}"
    )
    
    summary = ask_ai(prompt)
    
    if not summary:
        print("Не удалось получить ответ от ИИ. Публикация отменена.")
        return

    print("Отправка в Telegram...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": f"📰 **Сводка новостей**\n\n{summary}",
        "parse_mode": "Markdown",
        "disable_web_page_preview": True # Отключаем превью ссылок, чтобы пост был компактным
    }
    
    res = requests.post(url, json=payload)
    if res.status_code == 200:
        print("Успешно опубликовано!")
        save_state(state)
    else:
        print(f"Ошибка Telegram: {res.text}")

if __name__ == "__main__":
    main()
