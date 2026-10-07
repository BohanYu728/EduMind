"""真实 HTTP + 构建产物 + 隔离 stub 后端验收，无云端调用。"""

import mimetypes
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

BACKEND = Path(__file__).resolve().parents[1]
DIST = BACKEND.parent / "frontend" / "dist"
sys.path.insert(0, str(BACKEND))
os.environ["LLM_PROVIDER"] = "stub"
os.environ["ASR_PROVIDER"] = "stub"


def main():
    with tempfile.TemporaryDirectory(prefix="edumind-ui-") as isolated:
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(isolated) / 'test.db'}"
        os.chdir(isolated)

        import e2e_test
        from fastapi.testclient import TestClient

        from app.db.engine import engine
        from app.main import app

        with TestClient(app) as client:

            class Handler(BaseHTTPRequestHandler):
                def serve(self):
                    if self.path.startswith("/api/"):
                        length = int(self.headers.get("Content-Length", 0))
                        headers = {
                            key: value
                            for key, value in self.headers.items()
                            if key.lower() in {"content-type", "accept", "x-edumind-session"}
                        }
                        response = client.request(
                            self.command,
                            self.path,
                            headers=headers,
                            content=self.rfile.read(length) if length else None,
                        )
                        self.send_response(response.status_code)
                        for key, value in response.headers.items():
                            self.send_header(key, value)
                        self.end_headers()
                        self.wfile.write(response.content)
                    else:
                        path = (
                            DIST / (urlsplit(self.path).path.lstrip("/") or "index.html")
                        ).resolve()
                        if not path.is_relative_to(DIST.resolve()) or not path.is_file():
                            self.send_error(404)
                            return
                        content = path.read_bytes()
                        self.send_response(200)
                        self.send_header(
                            "Content-Type",
                            mimetypes.guess_type(str(path))[0] or "application/octet-stream",
                        )
                        self.send_header("Content-Length", str(len(content)))
                        self.end_headers()
                        self.wfile.write(content)

                do_GET = serve
                do_POST = serve
                do_DELETE = serve

                def log_message(self, format, *args):
                    pass

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            e2e_test.BASE = f"http://127.0.0.1:{server.server_port}"
            try:
                result = e2e_test.main()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
        engine.dispose()
        os.chdir(BACKEND)
        return result


if __name__ == "__main__":
    raise SystemExit(main())
