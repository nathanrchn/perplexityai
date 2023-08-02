from time import sleep
from uuid import uuid4
from requests import Session
from threading import Thread
from json import loads, dumps
from random import getrandbits
from websocket import WebSocketApp

from Answer import Answer, Details

class Perplexity:
    """A class to interact with the Perplexity website.
    To get started you need to create an instance of this class.
    For now this class only support one Answer at a time.
    """
    def __init__(self) -> None:
        self.user_agent: dict = { "User-Agent": "" }
        self.session: Session = self.init_session()

        self.searching = False
        self.t: str = self.get_t()
        self.answer: Answer = None
        self.ask_for_details = False
        self.sid: str = self.get_sid()
        self.frontend_uuid = str(uuid4())
        self.frontend_session_id = str(uuid4())

        assert self.ask_anonymous_user(), "Failed to ask anonymous user"
        self.ws: WebSocketApp = self.init_websocket()
        self.n = 1
        self.ws_thread: Thread = Thread(target=self.ws.run_forever).start()
        self.auth_session()

        sleep(1)

    def init_session(self) -> Session:
        session: Session = Session()

        uuid: str = str(uuid4())
        session.get(url=f"https://www.perplexity.ai/search/{uuid}", headers=self.user_agent)

        return session

    def get_t(self) -> str:
        return format(getrandbits(32), "08x")

    def get_sid(self) -> str:
        response = loads(self.session.get(
            url=f"https://www.perplexity.ai/socket.io/?EIO=4&transport=polling&t={self.t}",
            headers=self.user_agent
        ).text[1:])

        return response["sid"]

    def ask_anonymous_user(self) -> bool:
        response = self.session.post(
            url=f"https://www.perplexity.ai/socket.io/?EIO=4&transport=polling&t={self.t}&sid={self.sid}",
            data="40{\"jwt\":\"anonymous-ask-user\"}",
            headers=self.user_agent
        ).text

        return response == "OK"

    def on_message(self, ws: WebSocketApp, message: str) -> None:
        if message == "2":
            ws.send("3")
        elif message == "3probe":
            ws.send("5")

        if (self.searching or self.ask_for_details) and message.startswith(str(430 + self.n)):
            response = loads(message[3:])[0]

            if self.searching:
                self.answer = Answer(
                    uuid=response["uuid"],
                    gpt4=response["gpt4"],
                    text=response["text"],
                    search_focus=response["search_focus"],
                    backend_uuid=response["backend_uuid"],
                    query_str=response["query_str"],
                    related_queries=response["related_queries"]
                )
                self.searching = False
            else:
                self.answer.details = Details(
                    uuid=response["uuid"],
                    text=response["text"]
                )
                self.ask_for_details = False

    def get_cookies_str(self) -> str:
        cookies = ""
        for key, value in self.session.cookies.get_dict().items():
            cookies += f"{key}={value}; "
        return cookies[:-2]

    def init_websocket(self) -> WebSocketApp:
        return WebSocketApp(
            url=f"wss://www.perplexity.ai/socket.io/?EIO=4&transport=websocket&sid={self.sid}",
            header=self.user_agent,
            cookie=self.get_cookies_str(),
            on_open=lambda ws: ws.send("2probe"),
            on_message=self.on_message,
            on_error=lambda ws, err: print(f"Error: {err}"),
        )

    def auth_session(self) -> None:
        self.session.get(url="https://www.perplexity.ai/api/auth/session", headers=self.user_agent)

    def search(self, query: str, search_focus: str = "internet") -> Answer:
        """A function to search for a query. You can specify the search focus between: "internet", "scholar", "news", "youtube", "reddit", "wikipedia".
        Return the Answer object.
        """
        assert not self.searching, "Already searching"
        assert search_focus in ["internet", "scholar", "news", "youtube", "reddit", "wikipedia"], "Invalid search focus"
        self.searching = True
        self.n += 1
        ws_message: str = f"{420 + self.n}" + dumps([
            "perplexity_ask",
            query,
            {
                "source": "default",
                "last_backend_uuid": None,
                "read_write_token": "",
                "conversational_enabled": True,
                "frontend_session_id": self.frontend_session_id,
                "search_focus": search_focus,
                "frontend_uuid": self.frontend_uuid,
                "web_search_images": True,
                "gpt4": False
            }
        ])
        self.ws.send(ws_message)
        while self.searching:
            sleep(0.1)
        return self.answer

    def ask_detailed(self) -> Answer:
        """A function to ask for more details about the answer.
        Return the Answer object.
        """
        assert self.answer is not None, "Answer is None"
        assert not self.searching, "Already searching"

        self.ask_for_details = True
        self.n += 1
        ws_message: str = f"{420 + self.n}" + dumps([
            "perplexity_ask_detailed",
            self.answer.backend_uuid,
            {"frontend_uuid": str(uuid4())}
        ])
        self.ws.send(ws_message)
        while self.ask_for_details:
            sleep(0.1)
        return self.answer
    
    def close(self) -> None:
        """A function to close the websocket.
        """
        self.ws.close()
