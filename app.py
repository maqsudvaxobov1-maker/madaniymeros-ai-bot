import os
import json
import time
import threading
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN topilmadi")

if not OPENAI_API_KEY:
    raise Exception("OPENAI_API_KEY topilmadi")


def telegram(method, data):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode(),
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def send_message(chat_id, text):
    telegram("sendMessage", {
        "chat_id": chat_id,
        "text": text[:4000]
    })


def openai_answer(question):
    url = "https://api.openai.com/v1/chat/completions"

    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Siz Madaniy Meros AI yordamchisisiz. "
                    "O'zbekiston madaniy merosi, tarixiy-me'moriy "
                    "obyektlar va restavratsiya loyihalari bo'yicha "
                    "o'zbek tilida aniq va foydali javob bering."
                )
            },
            {
                "role": "user",
                "content": question
            }
        ]
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + OPENAI_API_KEY
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=90) as response:
        result = json.loads(response.read().decode())

    return result["choices"][0]["message"]["content"]


def telegram_bot():
    print("TELEGRAM BOT ISHLADI")

    offset = 0

    while True:
        try:
            result = telegram("getUpdates", {
                "offset": offset,
                "timeout": 30
            })

            for update in result.get("result", []):
                offset = update["update_id"] + 1

                message = update.get("message")

                if not message:
                    continue

                chat_id = message["chat"]["id"]
                text = message.get("text", "").strip()

                if text == "/start":
                    send_message(
                        chat_id,
                        "Ассалому алайкум! 👋\n\n"
                        "Мен Madaniy Meros AI ботман.\n\n"
                        "Маданий мерос бўйича саволингизни ёзинг."
                    )
                    continue

                if text:
                    try:
                        answer = openai_answer(text)
                        send_message(chat_id, answer)

                    except Exception as error:
                        print("OPENAI ERROR:", error)

                        send_message(
                            chat_id,
                            "AI билан боғланишда хатолик юз берди."
                        )

        except Exception as error:
            print("TELEGRAM ERROR:", error)
            time.sleep(5)


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Madaniy Meros AI Bot ishlayapti!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return


def web_server():
    server = HTTPServer(
        ("0.0.0.0", PORT),
        Handler
    )

    print("WEB SERVER ISHLADI")
    server.serve_forever()


threading.Thread(
    target=web_server,
    daemon=True
).start()

telegram_bot()
