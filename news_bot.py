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
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {"published_ids": []}
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
            system="Ты — редактор VPN-канала. Пиши кратко, интересно и с эмодзи."
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
    
    # Собираем заголовки для ИИ
    news_text = "\n".join([f"- {a.title}" for a in new_articles])
    
    # Собираем ссылки для отправки (отдельно от ИИ, чтобы не сломать разметку)
    links_text = "\n".join([f"🔗 <a href='{a.link}'>Источник {i+1}</a>" for i, a in enumerate(new_articles)])

    prompt = (
        f"Ниже список новостей. Сделай из них краткую сводку в виде списка (каждый пункт с новой строки). "
        f"Начни каждый пункт с подходящего эмодзи. Не пиши вводных слов, только сами пункты:\n{news_text}"
    )
    
    summary = ask_ai(prompt)
    
    if not summary:
        print("Не удалось получить ответ от ИИ. Публикация отменена.")
        return

    # --- ОЧИСТКА ТЕКСТА ---
    clean_summary = summary.replace('<', '&lt;').replace('>', '&gt;')
    
    print("Отправка в Telegram...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # Формируем итоговый текст: Заголовок + Сводка + Ссылки
    final_text = f"📰 <b>Сводка новостей</b>\n\n{clean_summary}\n\n<b>Источники:</b>\n{links_text}"
    
    payload = {
        "chat_id": CHANNEL_ID,
        "text": final_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True # Отключает огромные превью картинок из ссылок
    }
    
    res = requests.post(url, json=payload)
    
    if res.status_code == 200:
        print("Успешно опубликовано!")
        save_state(state)
    else:
        print(f"Ошибка Telegram: {res.text}")
        # На всякий случай пробуем отправить без разметки, если Telegram снова закапризничает
        fallback_text = f"📰 Сводка новостей\n\n{summary}\n\nИсточники:\n" + "\n".join([a.link for a in new_articles])
        fallback_payload = {"chat_id": CHANNEL_ID, "text": fallback_text}
        requests.post(url, json=fallback_payload)

if __name__ == "__main__":
    main()
