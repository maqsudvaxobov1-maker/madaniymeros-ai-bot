import os
import json
import time
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

PORT = int(os.environ.get("PORT", "10000"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY topilmadi")


def telegram(method, data=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    if data is None:
        data = {}

    body = json.dumps(data).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def ask_openai(text):
    url = "https://api.openai.com/v1/responses"

    payload = {
        "model": "gpt-5.6-luna",
        "input": [
            {
                "role": "system",
                "content": (
                    "Siz Madaniy Meros AI yordamchisiz. "
                    "O'zbekistondagi madaniy meros obyektlari, "
                    "tarixiy-me'moriy yodgorliklar va loyihalar "
                    "bo'yicha foydali va aniq javob bering. "
                    "Javoblarni o'zbek tilida bering."
                )
            },
            {
                "role": "user",
                "content": text
            }
        ]
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}"
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=90) as response:
        result = json.loads(response.read().decode("utf-8"))

    return result["output"][0]["content"][0]["text"]


def send_message(chat_id, text):
    # Telegram bir xabarda 4096 belgigacha qabul qiladi.
    for i in range(0, len(text), 4000):
        telegram(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text[i:i + 4000]
            }
        )


def bot_loop():
    print("Telegram bot ishga tushdi.")

    offset = 0

    while True:
        try:
            result = telegram(
                "getUpdates",
                {
                    "offset": offset,
                    "timeout": 30
                }
            )

            for update in result.get("result", []):
                offset = update["update_id"] + 1

                message = update.get("message")

                if not message:
                    continue

                chat_id = message["chat"]["id"]
                text = message.get("text", "").strip()

                if not text:
                    continue

                if text == "/start":
                    send_message(
                        chat_id,
                        "Ассалому алайкум! 👋\n\n"
                        "Madaniy Meros AI ботга хуш келибсиз.\n\n"
                        "Маданий мерос объектлари бўйича "
                        "саволингизни ёзинг."
                    )
                    continue

                try:
                    answer = ask_openai(text)
                    send_message(chat_id, answer)

                except Exception as e:
                    print("OpenAI xatosi:", e)

                    send_message(
                        chat_id,
                        "Кечирасиз, ҳозир жавоб беришда хатолик юз берди. "
                        "Бироздан сўнг қайта уриниб кўринг."
                    )

        except Exception as e:
            print("Bot xatosi:", e)
            time.sleep(5)


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )
        self.end_headers()
        self.wfile.write(
            b"Madaniy Meros AI bot ishlayapti!"
        )

    def log_message(self, format, *args):
        return


def start_server():
    server = HTTPServer(("0.0.0.0", PORT), Handler)

    print(f"Web server port {PORT} da ishga tushdi.")

    server.serve_forever()


if __name__ == "__main__":

    import threading

    web_thread = threading.Thread(
        target=start_server,
        daemon=True
    )

    web_thread.start()

    bot_loop()
