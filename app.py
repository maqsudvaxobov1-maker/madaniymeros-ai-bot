import os
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import Request, urlopen
from urllib.parse import urlencode

TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", "10000"))

if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

API = f"https://api.telegram.org/bot{TOKEN}/"


def telegram(method, data=None):
    if data is None:
        data = {}

    body = urlencode(data).encode("utf-8")
    req = Request(API + method, data=body)

    with urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def send_message(chat_id, text):
    telegram("sendMessage", {
        "chat_id": chat_id,
        "text": text
    })


def bot_loop():
    offset = 0

    print("Telegram bot ishga tushdi")

    while True:
        try:
            result = telegram("getUpdates", {
                "offset": offset,
                "timeout": 30
            })

            if not result.get("ok"):
                time.sleep(5)
                continue

            for update in result.get("result", []):
                offset = update["update_id"] + 1

                message = update.get("message")

                if not message:
                    continue

                chat_id = message["chat"]["id"]
                text = message.get("text", "").strip()

                if text == "/start":
                    answer = (
                        "Ассалому алайкум! 👋\n\n"
                        "Madaniy Meros AI ботга хуш келибсиз.\n\n"
                        "Маданий мерос объектлари бўйича "
                        "саволингизни ёзинг."
                    )

                elif text:
                    answer = (
                        "Саволингиз қабул қилинди. ✅\n\n"
                        f"Сизнинг саволингиз:\n{text}\n\n"
                        "Madaniy Meros AI хизмати ишлаяпти."
                    )

                else:
                    answer = "Илтимос, матнли савол юборинг."

                send_message(chat_id, answer)

        except Exception as e:
            print("Bot xatosi:", e)
            time.sleep(5)


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8"
            )
            self.end_headers()
            self.wfile.write(b"OK")
            return

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8"
        )
        self.end_headers()

        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Madaniy Meros AI Bot</title>
        </head>
        <body>
            <h1>Madaniy Meros AI Bot</h1>
            <p>Telegram bot server ishlayapti.</p>
        </body>
        </html>
        """

        self.wfile.write(html.encode("utf-8"))


def start_server():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Server port {PORT} da ishga tushdi")
    server.serve_forever()


threading.Thread(
    target=bot_loop,
    daemon=True
).start()

start_server()
