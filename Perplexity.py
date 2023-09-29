from os import listdir
from time import sleep
from uuid import uuid4
from threading import Thread
from requests import Session
from json import loads, dumps
from random import getrandbits
from urllib.parse import quote
from websocket import WebSocketApp

class Perplexity:
    def __init__(self, email: str = None) -> None:
        if ".perplexity_session" in listdir():
            self.session: Session = self._recover_session()
        else:
            self.user_agent: dict = { "User-Agent": "Ask/2.2.1/334 (iOS; iPhone) isiOSOnMac/false" }
            self.session: Session = self._init_session_without_login()

            if email:
                self._login(email)

        self.t: str = self._get_t()
        self.sid: str = self._get_sid()
    
        self.n: int = 1
        self.queue: list = []
        self.searching: bool = False
        self.backend_uuid: str = None
        self.frontend_uuid: str = str(uuid4())
        self.frontend_session_id: str = str(uuid4())

        assert self._ask_anonymous_user(), "failed to ask anonymous user"
        self.ws: WebSocketApp = self.init_websocket()
        self.ws_thread: Thread = Thread(target=self.ws.run_forever).start()
        self._auth_session()

        # Wait for the websocket to connect
        while not (self.ws.sock and self.ws.sock.connected):
            sleep(0.01)
    
    def _login(self, email: str) -> None:
        self.session.post(url="https://www.perplexity.ai/api/auth/signin-email", data={"email": email})

        email_link: str = str(input("paste the link you received by email: "))
        self.session.get(email_link)

        with open(".perplexity_session", "w") as f:
            f.write(dumps(self.session.cookies.get_dict()))

    def _recover_session(self) -> Session:
        session: Session = Session()

        with open(".perplexity_session", "r") as f:
            session.cookies.update(loads(f.read()))

        return session

    def _init_session_without_login(self) -> Session:
        session: Session = Session()

        uuid: str = str(uuid4())
        session.get(url=f"https://www.perplexity.ai/search/{uuid}")
        session.headers.update(self.user_agent)

        return session
    
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

    def init_websocket(self) -> WebSocketApp:
        def on_open(ws: WebSocketApp) -> None:
            ws.send("2probe")
            ws.send("5")

        def on_message(ws: WebSocketApp, message: str) -> None:
            if message == "2":
                ws.send("3")
            elif message.startswith("42"):
                message = loads(message[2:])
                self.queue.append(message[1])
                if message[0] == "query_answered":
                    self.searching = False

        return WebSocketApp(
            url=f"wss://www.perplexity.ai/socket.io/?EIO=4&transport=websocket&sid={self.sid}",
            header=self.user_agent,
            cookie=self._get_cookies_str(),
            on_open=on_open,
            on_message=on_message,
            on_error=lambda ws, err: print(f"websocket error: {err}")
        )

    def search(self, query: str, mode: str = "concise", search_focus: str = "internet", attachments: list[str] = [], language: str = "en-GB") -> dict:
        assert not self.searching, "already searching"
        assert mode in ["concise", "copilot"], "invalid mode"
        assert search_focus in ["internet", "scholar", "writing", "wolfram", "youtube", "reddit"], "invalid search focus"
        self.searching = True
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

        while self.searching or len(self.queue) != 0:
            if len(self.queue) != 0:
                yield self.queue.pop(0)
    
    def close(self) -> None:
        self.ws.close()
