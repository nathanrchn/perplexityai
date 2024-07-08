from time import time
from uuid import uuid4
from json import loads, dumps
from random import getrandbits
from aiohttp import ClientSession
from dataclasses import dataclass
from typing import AsyncGenerator
from asyncio import run, ensure_future, gather

MODELS = [
    "pplx-7b-online",
    "pplx-70b-online"
    "pplx-7b-chat",
    "pplx-70b-chat",
    "mistral-7b-instruct",
    "codellama-34b-instruct",
    "llama-2-70b-chat",
    "llava-7b-chat",
    "mixtral-8x7b-instruct",
]

@dataclass
class Session:
    session: ClientSession
    sid: str
    busy: bool

class AsyncLabs:
    def __init__(self) -> None:
        self.sessions: dict = {}
        self.user_agent: dict = { "User-Agent": "Ask/2.2.1/334 (iOS; iPhone) isiOSOnMac/false", "X-Client-Name": "Perplexity-iOS" }

    async def _get_sid(self, session: ClientSession) -> str:
        async with session.get(url=f"https://labs-api.perplexity.ai/socket.io/?transport=polling&EIO=4") as response:
            return loads((await response.text())[1:])["sid"]

    async def _add_session(self) -> (str, Session):
        uuid = str(uuid4())
        session = ClientSession()
        session.headers.update(self.user_agent)

        sid = await self._get_sid(session)
        t = format(getrandbits(32), "08x")

        self.sessions[uuid] = Session(session=session, sid=sid, busy=False)
        async with session.post(
            url=f"https://labs-api.perplexity.ai/socket.io/?EIO=4&transport=polling&t={t}&sid={sid}",
            data="40{\"jwt\":\"anonymous-ask-user\"}"
        ) as response:
            assert (await response.text()) == "OK", "failed to ask anonymous user"

        return (uuid, self.sessions[uuid])
    
    async def add_n_sessions(self, n: int) -> list:
        tasks = [ensure_future(self.add_session()) for _ in range(n)]
        return await gather(*tasks)
    
    def _get_cookies_str(self, cookie_jar) -> str:
        cookies_str = ""
        for cookie in cookie_jar:
            cookies_str += f"{cookie.key}={cookie.value}; "
        return cookies_str[:-2]
    
    async def create(self, messages: list[dict], model: str) -> AsyncGenerator[dict, None]:
        session: Session = None
        _, session = await self._add_session()
        session.busy = True

        headers = self.user_agent.copy()
        headers["Cookie"] = self._get_cookies_str(session.session.cookie_jar)

        async with session.session.ws_connect(
            url=f"wss://labs-api.perplexity.ai/socket.io/?EIO=4&transport=websocket&sid={session.sid}",
            headers=headers,
        ) as ws:
            await ws.send_str("2probe")
            await ws.send_str("5")
            await ws.send_str("42[\"perplexity_playground\",{\"version\":\"2.1\",\"source\":\"default\",\"model\":\"" + model + "\",\"messages\":" + dumps(messages) + "}]")
            async for msg in ws:
                msg = msg.data
                if msg == "2":
                    await ws.send_str("3")
                elif msg.startswith("42"):
                    msg = loads(msg[2:])[1]
                    if "status" not in msg:
                        yield msg
                    elif msg["status"] == "completed":
                        yield msg
                        break
                    elif msg["status"] == "failed":
                        break

        session.busy = False

    async def create_sync(self, messages: list[dict], model: str) -> list[dict]:
        return [message async for message in self.create(messages, model)]
        
    async def close(self) -> None:
        for session in self.sessions.values():
            await session.session.close()
    
async def main() -> None:
    labs = AsyncLabs()

    tasks = [ensure_future(labs.create_sync([{"role": "user", "content": "Wo is the current french president ?", "priority": 0}], "mixtral-8x7b-instruct")) for _ in range(3)]
    messages = await gather(*tasks)

    for message in messages:
        for m in message:
            print(m)

    print(labs.sessions)
    await labs.close()

if __name__ == "__main__":
    run(main())