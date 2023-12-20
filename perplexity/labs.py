from os import listdir
from uuid import uuid4
from time import sleep, time
from threading import Thread
from json import loads, dumps
from random import getrandbits
from websocket import WebSocketApp
from requests import Session, get, post

class Labs:
    def __init__(self) -> None:
        self.history: list = []
        self.session: Session = Session()
        self.user_agent: dict = { "User-Agent": "Ask/2.2.1/334 (iOS; iPhone) isiOSOnMac/false", "X-Client-Name": "Perplexity-iOS" }
        self.session.headers.update(self.user_agent)
        self._init_session_without_login()

        self.t: str = self._get_t()
        self.sid: str = self._get_sid()
    
        self.queue: list = []
        self.finished: bool = True

        assert self._ask_anonymous_user(), "failed to ask anonymous user"
        self.ws: WebSocketApp = self._init_websocket()
        self.ws_thread: Thread = Thread(target=self.ws.run_forever).start()
        self._auth_session()

        while not (self.ws.sock and self.ws.sock.connected):
            sleep(0.01)

    def _init_session_without_login(self) -> None:
        self.session.get(url=f"https://www.perplexity.ai/search/{str(uuid4())}")
        self.session.headers.update(self.user_agent)
    
    def _auth_session(self) -> None:
        self.session.get(url="https://www.perplexity.ai/api/auth/session")

    def _get_t(self) -> str:
        return format(getrandbits(32), "08x")

    def _get_sid(self) -> str:
        return loads(self.session.get(
            url=f"https://labs-api.perplexity.ai/socket.io/?transport=polling&EIO=4"
        ).text[1:])["sid"]

    def _ask_anonymous_user(self) -> bool:
        response = self.session.post(
            url=f"https://labs-api.perplexity.ai/socket.io/?EIO=4&transport=polling&t={self.t}&sid={self.sid}",
            data="40{\"jwt\":\"anonymous-ask-user\"}"
        ).text

        return response == "OK"

    def _get_cookies_str(self) -> str:
        cookies = ""
        for key, value in self.session.cookies.get_dict().items():
            cookies += f"{key}={value}; "
        return cookies[:-2]

    def _init_websocket(self) -> WebSocketApp:
        def on_open(ws: WebSocketApp) -> None:
            ws.send("2probe")
            ws.send("5")

        def on_message(ws: WebSocketApp, message: str) -> None:
            if message == "2":
                ws.send("3")
            elif message.startswith("42"):
                message = loads(message[2:])[1]
                if "status" not in message:
                    self.queue.append(message)
                elif message["status"] == "completed":
                    self.finished = True
                    self.history.append({"role": "assistant", "content": message["output"], "priority": 0})
                elif message["status"] == "failed":
                    self.finished = True

        headers: dict = self.user_agent
        headers["Cookie"] = self._get_cookies_str()

        return WebSocketApp(
            url=f"wss://labs-api.perplexity.ai/socket.io/?EIO=4&transport=websocket&sid={self.sid}",
            header=headers,
            on_open=on_open,
            on_message=on_message,
            on_error=lambda ws, err: print(f"websocket error: {err}")
        )
    
    def _c(self, prompt: str, model: str) -> dict:
        assert self.finished, "already searching"
        assert model in [
            "mixtral-8x7b-instruct",
            "llava-7b-chat",
            "llama-2-70b-chat",
            "codellama-34b-instruct",
            "mistral-7b-instruct",
            "pplx-7b-chat",
            "pplx-70b-chat",
            "pplx-7b-online",
            "pplx-70b-online"
        ]
        self.finished = False
        self.history.append({"role": "user", "content": prompt, "priority": 0})
        self.ws.send("42[\"perplexity_playground\",{\"version\":\"2.1\",\"source\":\"default\",\"model\":\"" + model + "\",\"messages\":" + dumps(self.history) + "}]")
    
    def chat(self, prompt: str, model: str = "mistral-7b-instruct") -> dict:
        self._c(prompt, model)

        while (not self.finished) or (len(self.queue) != 0):
            if len(self.queue) > 0:
                yield self.queue.pop(0)

    def chat_sync(self, prompt: str, model: str = "mistral-7b-instruct") -> dict:
        self._c(prompt, model)

        while not self.finished:
            pass

        return self.queue.pop(-1)

    def close(self) -> None:
        self.ws.close()
