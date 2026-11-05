import feedparser
import json
import os
import sys
import requests
import time
import re
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

def clean_html_tags(text):
    # Разрешаем только безопасные теги b, i, a, code, pre
    allowed_tags = ['b', 'i', 'a', 'code', 'pre']
    
    # Функция для обработки найденных тегов
    def replace_tag(match):
        full_tag = match.group(0)
        tag_name = match.group(2).lower()
        
        if tag_name in allowed_tags:
            return full_tag
        return "" # Удаляем неразрешенные теги
    
    # Ищем все теги <...>
    cleaned = re.sub(r'(<\/?)([a-zA-Z0-9]+)([^>]*>)', replace_tag, text)
    
    # Убираем "висячие" закрывающие теги, если им нет пары
    for tag in ['</b>', '</i>', '</a>', '</code>', '</pre>']:
        open_tag = tag.replace('/', '')
        if cleaned.count(open_tag) < cleaned.count(tag):
            # Если закрывающих больше, чем открывающих, удаляем лишние
            cleaned = cleaned.replace(tag, '', cleaned.count(tag) - cleaned.count(open_tag))
    
    return cleaned

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
    
    news_text = "\n".join([f"- {a.title} (Ссылка: {a.link})" for a in new_articles])

    prompt = (
        f"Ниже список новостей (в скобках указаны ссылки на источники). "
        f"Сделай из них краткую сводку в виде списка (каждый пункт с новой строки). "
        f"Начни каждый пункт с подходящего эмодзи. ВАЖНО: В конце каждого пункта напиши ссылку на источник в формате <a href='ССЫЛКА'>Источник</a>:\n{news_text}"
    )
    
    summary = ask_ai(prompt)
    
    if not summary:
        print("Не удалось получить ответ от ИИ. Публикация отменена.")
        return

    # --- ОЧИСТКА ТЕКСТА ---
    clean_summary = summary.replace('<', '&lt;').replace('>', '&gt;')
    # Восстанавливаем разрешенные теги
    clean_summary = clean_summary.replace("&lt;a href=&quot;", "<a href='").replace("&quot;&gt;", "'>").replace("&lt;/a&gt;", "</a>")
    
    # Дополнительная очистка от висячих тегов
    clean_summary = clean_html_tags(clean_summary)
    
    print("Отправка в Telegram...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    final_text = f"📰 <b>Сводка новостей</b>\n\n{clean_summary}"
    
    payload = {
        "chat_id": CHANNEL_ID,
        "text": final_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    res = requests.post(url, json=payload)
    
    if res.status_code == 200:
        print("Успешно опубликовано!")
        save_state(state)
    else:
        print(f"Ошибка Telegram: {res.text}")
        # Если ИИ сломал разметку, отправляем вообще без ссылок и разметки
        fallback_text = f"📰 Сводка новостей\n\n{summary}\n\nИсточники:\n" + "\n".join([a.link for a in new_articles])
        fallback_payload = {"chat_id": CHANNEL_ID, "text": fallback_text}
        requests.post(url, json=fallback_payload)

if __name__ == "__main__":
    main()
