import os
import json
import time
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
PORT = int(os.environ.get("PORT", "10000"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY topilmadi")


def telegram(method, data):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    body = urllib.parse.urlencode(data).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def send_message(chat_id, text):
    telegram("sendMessage", {
        "chat_id": chat_id,
        "text": text[:4000]
    })


def ask_ai(question):
    url = "https://api.openai.com/v1/chat/completions"

    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Siz O'zbekiston madaniy merosi bo'yicha AI "
                    "yordamchisiz. Savollarga o'zbek tilida aniq, "
                    "tushunarli va foydali javob bering. "
                    "Madaniy meros obyektlari, tarixiy-me'moriy "
                    "yodgorliklar, restavratsiya va loyiha "
                    "hujjatlari bo'yicha yordam bering."
                )
            },
            {
                "role": "user",
                "content": question
            }
        ],
        "temperature": 0.3
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}"
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=90) as response:
        result = json.loads(response.read().decode("utf-8"))

    return result["choices"][0]["message"]["content"]


def bot_loop():
    offset = 0

    print("Telegram bot ishga tushdi")

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
                        "Мен Madaniy Meros AI ёрдамчисиман.\n\n"
                        "Маданий мерос, тарихий-меъморий "
                        "объектлар ва лойиҳалар бўйича "
                        "саволингизни ёзинг."
                    )
                    continue

                try:
                    answer = ask_ai(text)
                    send_message(chat_id, answer)

                except Exception as error:
                    print("OpenAI xatosi:", error)

                    send_message(
                        chat_id,
                        "AI жавобида хатолик юз берди. "
                        "Бироздан кейин қайта уриниб кўринг."
                    )

        except Exception as error:
            print("Telegram xatosi:", error)
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
            b"Madaniy Meros AI Bot ishlayapti!"
        )

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return


def start_server():
    server = HTTPServer(
        ("0.0.0.0", PORT),
        Handler
    )

    print(f"Server {PORT} portda ishga tushdi")
    server.serve_forever()


if __name__ == "__main__":

    threading.Thread(
        target=start_server,
        daemon=True
    ).start()

    bot_loop()
