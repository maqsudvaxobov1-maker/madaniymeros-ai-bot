import os
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", 10000))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")
            return

        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Madaniy Meros AI Bot</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background: #f5f5f5;
                    padding: 30px;
                }
                .box {
                    max-width: 700px;
                    margin: auto;
                    background: white;
                    padding: 30px;
                    border-radius: 15px;
                    box-shadow: 0 2px 10px #ccc;
                }
                h1 {
                    text-align: center;
                }
                p {
                    font-size: 18px;
                    line-height: 1.6;
                }
            </style>
        </head>
        <body>
            <div class="box">
                <h1>🏛 Madaniy Meros AI Bot</h1>
                <p>Ассалому алайкум!</p>
                <p>
                    Маданий мерос объектлари бўйича ахборот ва
                    лойиҳа ҳужжатларини кўриб чиқиш тизими ишга тушди.
                </p>
                <p>✅ Сервер ишлаяпти.</p>
            </div>
        </body>
        </html>
        """

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

server = HTTPServer(("0.0.0.0", PORT), Handler)

print(f"Server started on port {PORT}")

server.serve_forever()
