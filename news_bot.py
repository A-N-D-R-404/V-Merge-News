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

def sanitize_telegram_html(text):
    """
    Ищет все ссылки (в тегах a или просто в тексте) и делает из них 
    аккуратные кликабельные слова "Источник". Удаляет весь остальной мусор.
    """
    # Паттерн для поиска ссылок внутри тегов <a> или просто голых ссылок
    # Ищем либо <a href="...">...</a>, либо просто http(s)://...
    url_pattern = r'(?:<a\s+href=[\'"]?([^\'">]+)[\'"]?>.*?</a>)|(https?://[^\s<]+)'
    
    def replace_url(match):
        # Если ссылка была в теге <a>, берем URL из первой группы
        url = match.group(1) if match.group(1) else match.group(2)
        # Очищаем URL от возможных лишних кавычек в конце
        url = url.strip('\'">')
        # Возвращаем красивый кликабельный текст
        return f"<a href='{url}'>🔗 Источник</a>"

    # Заменяем все ссылки (и теги, и голые) на наши красивые
    cleaned_text = re.sub(url_pattern, replace_url, text, flags=re.IGNORECASE)
    
    # Удаляем оставшиеся случайные HTML-теги (кроме <a>, <b>, <i>, <code>)
    # Это уберет мусор, если ИИ сгенерировал что-то странное
    allowed_tags = ['a', 'b', 'i', 'code', 'pre']
    
    def tag_replacer(match):
        tag = match.group(0)
        # Извлекаем имя тега (например, из <div> получаем div)
        tag_name = re.search(r'<(/?)(\w+)', tag)
        if tag_name and tag_name.group(2).lower() in allowed_tags:
            return tag
        return ""

    cleaned_text = re.sub(r'<[^>]+>', tag_replacer, cleaned_text)
    
    # Экранируем оставшиеся угловые скобки, которые не являются тегами
    # (на случай, если ИИ написал что-то вроде "5 < 10")
    cleaned_text = cleaned_text.replace(" < ", " &lt; ").replace(" > ", " &gt; ")

    return cleaned_text

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

    # Используем новую умную очистку
    clean_summary = sanitize_telegram_html(summary)
    
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
        # Если Telegram снова закапризничает, отправляем вообще без разметки
        fallback_text = f"📰 Сводка новостей\n\n{re.sub(r'<[^>]+>', '', summary)}\n\nИсточники:\n" + "\n".join([a.link for a in new_articles])
        fallback_payload = {"chat_id": CHANNEL_ID, "text": fallback_text}
        requests.post(url, json=fallback_payload)

if __name__ == "__main__":
    main()
