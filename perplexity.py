from os import listdir
from uuid import uuid4
from time import sleep, time
from threading import Thread
from json import loads, dumps
from random import getrandbits
from urllib.parse import quote
from websocket import WebSocketApp
from requests import Session, get, post

class Perplexity:
    def __init__(self, email: str = None) -> None:
        self.session: Session = Session()
        self.user_agent: dict = { "User-Agent": "Ask/2.2.1/334 (iOS; iPhone) isiOSOnMac/false" }
        self.session.headers.update(self.user_agent)

        if ".perplexity_session" in listdir():
            self._recover_session(email)
        else:
            self._init_session_without_login()

            if email:
                self._login(email)

        self.email: str = email
        self.t: str = self._get_t()
        self.sid: str = self._get_sid()
    
        self.n: int = 1
        self.queue: list = []
        self.finished: bool = True
        self.backend_uuid: str = None
        self.frontend_uuid: str = str(uuid4())
        self.frontend_session_id: str = str(uuid4())

        assert self._ask_anonymous_user(), "failed to ask anonymous user"
        self.ws: WebSocketApp = self.init_websocket()
        self.ws_thread: Thread = Thread(target=self.ws.run_forever).start()
        self._auth_session()

        while not (self.ws.sock and self.ws.sock.connected):
            sleep(0.01)

    def _recover_session(self, email: str) -> None:
        with open(".perplexity_session", "r") as f:
            perplexity_session: dict = loads(f.read())

        if email in perplexity_session:
            self.session.cookies.update(perplexity_session[email])
        else:
            self._login(email, perplexity_session)
    
    def _login(self, email: str, ps: dict = None) -> None:
        self.session.post(url="https://www.perplexity.ai/api/auth/signin-email", data={"email": email})

        email_link: str = str(input("paste the link you received by email: "))
        self.session.get(email_link)

        if ps:
            ps[email] = self.session.cookies.get_dict()
        else:
            ps = {email: self.session.cookies.get_dict()}

        with open(".perplexity_session", "w") as f:
            f.write(dumps(ps))

    def _init_session_without_login(self) -> None:
        self.session.get(url=f"https://www.perplexity.ai/search/{str(uuid4())}")
        self.session.headers.update(self.user_agent)
    
    def _auth_session(self) -> None:
        self.session.get(url="https://www.perplexity.ai/api/auth/session")

    def _get_t(self) -> str:
        return format(getrandbits(32), "08x")

    def _get_sid(self) -> str:
        return loads(self.session.get(
            url=f"https://www.perplexity.ai/socket.io/?EIO=4&transport=polling&t={self.t}"
        ).text[1:])["sid"]

    def _ask_anonymous_user(self) -> bool:
        response = self.session.post(
            url=f"https://www.perplexity.ai/socket.io/?EIO=4&transport=polling&t={self.t}&sid={self.sid}",
            data="40{\"jwt\":\"anonymous-ask-user\"}"
        ).text

        return response == "OK"

    def _get_cookies_str(self) -> str:
        cookies = ""
        for key, value in self.session.cookies.get_dict().items():
            cookies += f"{key}={value}; "
        return cookies[:-2]
    
    def _write_file_url(self, filename: str, file_url: str) -> None:
        if ".perplexity_files_url" in listdir():
            with open(".perplexity_files_url", "r") as f:
                perplexity_files_url: dict = loads(f.read())
        else:
            perplexity_files_url: dict = {}

        perplexity_files_url[filename] = file_url

        with open(".perplexity_files_url", "w") as f:
            f.write(dumps(perplexity_files_url))

    def init_websocket(self) -> WebSocketApp:
        def on_open(ws: WebSocketApp) -> None:
            ws.send("2probe")
            ws.send("5")

        def on_message(ws: WebSocketApp, message: str) -> None:
            if message == "2":
                ws.send("3")
            elif not self.finished:
                if message.startswith("42"):
                    message : list = loads(message[2:])
                    content: dict = message[1]
                    content.update(loads(content["text"]))
                    content.pop("text")
                    self.queue.append(content)
                    if message[0] == "query_answered":
                        self.finished = True
                elif message.startswith("43"):
                    message: dict = loads(message[3:])[0]
                    self.queue.append(message)
                    self.finished = True

        return WebSocketApp(
            url=f"wss://www.perplexity.ai/socket.io/?EIO=4&transport=websocket&sid={self.sid}",
            header=self.user_agent,
            cookie=self._get_cookies_str(),
            on_open=on_open,
            on_message=on_message,
            on_error=lambda ws, err: print(f"websocket error: {err}")
        )

    def search(self, query: str, mode: str = "concise", search_focus: str = "internet", attachments: list[str] = [], language: str = "en-GB", timeout: float = None) -> dict:
        assert self.finished, "already searching"
        assert mode in ["concise", "copilot"], "invalid mode"
        assert len(attachments) <= 4, "too many attachments: max 4"
        assert search_focus in ["internet", "scholar", "writing", "wolfram", "youtube", "reddit"], "invalid search focus"
        self.finished = False
        self.n += 1
        ws_message: str = f"{420 + self.n}" + dumps([
            "perplexity_ask",
            query,
            {
                "version": "2.1",
                "source": "default", # "ios"
                "frontend_session_id": self.frontend_session_id,
                "language": language,
                "timezone": "CET",
                "attachments": attachments,
                "search_focus": search_focus,
                "frontend_uuid": self.frontend_uuid,
                "mode": mode,
                # "use_inhouse_model": True
            }
        ])
        self.ws.send(ws_message)

        start_time: float = time()
        while (not self.finished) or len(self.queue) != 0:
            if timeout and time() - start_time > timeout:
                self.finished = True
                return {"error": "timeout"}
            if len(self.queue) != 0:
                yield self.queue.pop(0)

    def upload(self, filename: str) -> str:
        assert self.finished, "already searching"
        assert filename.split(".")[-1] in ["txt", "pdf"], "invalid file format"

        if filename.startswith("http"):
            file = get(filename).content
        else:
            with open(filename, "rb") as f:
                file = f.read()

        self.finished = False
        self.n += 1
        ws_message: str = f"{420 + self.n}" + dumps([
            "get_upload_url",
            {
                "version": "2.1",
                "source": "default",
                "content_type": "text/plain" if filename.split(".")[-1] == "txt" else "application/pdf",
            }
        ])

        self.ws.send(ws_message)

        while not self.finished or len(self.queue) != 0:
            if len(self.queue) != 0:
                upload_data = self.queue.pop(0)

        assert not upload_data["rate_limited"], "rate limited"
        
        post(
            url=upload_data["url"],
            files={
                "acl": (None, upload_data["fields"]["acl"]),
                "Content-Type": (None, upload_data["fields"]["Content-Type"]),
                "key": (None, upload_data["fields"]["key"]),
                "AWSAccessKeyId": (None, upload_data["fields"]["AWSAccessKeyId"]),
                "x-amz-security-token": (None, upload_data["fields"]["x-amz-security-token"]),
                "policy": (None, upload_data["fields"]["policy"]),
                "signature": (None, upload_data["fields"]["signature"]),
                "file": (filename, file)
            }
        )

        file_url: str = upload_data["url"] + upload_data["fields"]["key"].split("$")[0] + filename

        self._write_file_url(filename, file_url)

        return file_url
    
    def threads(self, query: str = None, limit: int = None) -> list[dict]:
        assert self.finished, "already searching"

        if not limit: limit = 20
        data: dict = {"version": "2.1", "source": "default", "limit": limit, "offset": 0}
        if query: data["search_term"] = query

        self.finished = False
        self.n += 1
        ws_message: str = f"{420 + self.n}" + dumps([
            "list_ask_threads",
            data
        ])

        self.ws.send(ws_message)

        while not self.finished or len(self.queue) != 0:
            if len(self.queue) != 0:
                return self.queue.pop(0)
    
    def close(self) -> None:
        self.ws.close()

        if self.email:
            with open(".perplexity_session", "r") as f:
                perplexity_session: dict = loads(f.read())

            perplexity_session[self.email] = self.session.cookies.get_dict()

            with open(".perplexity_session", "w") as f:
                f.write(dumps(perplexity_session))
