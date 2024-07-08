from time import time
from uuid import uuid4
from json import loads, dumps
from random import getrandbits
from aiohttp import ClientSession
from aiohttp.client import ClientWebSocketResponse
from dataclasses import dataclass
from asyncio import run, ensure_future, gather, sleep

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
    connection: ClientWebSocketResponse
    sid: str
    busy: bool

class FastLabs:
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

        self.sessions[uuid] = Session(session=session, connection=None, sid=sid, busy=False)
        async with session.post(
            url=f"https://labs-api.perplexity.ai/socket.io/?EIO=4&transport=polling&t={t}&sid={sid}",
            data="40{\"jwt\":\"anonymous-ask-user\"}"
        ) as response:
            assert (await response.text()) == "OK", "failed to ask anonymous user"

        return (uuid, self.sessions[uuid])
    
    async def _get_connection(self) -> Session:
        for session in self.sessions.values():
            if not session.busy:
                return session
            
        _, session = await self._add_session()
        headers = self.user_agent.copy()
        headers["Cookie"] = self._get_cookies_str(session.session.cookie_jar)

        session.connection = await session.session.ws_connect(
            url=f"wss://labs-api.perplexity.ai/socket.io/?EIO=4&transport=websocket&sid={session.sid}",
            headers=headers,
        )
        # await ws.send_str("2probe")
        # await ws.send_str("5")
        await session.connection.send_str("2probe")
        await session.connection.send_str("5")
        return session
    
    # async def add_n_sessions(self, n: int) -> list:
    #     tasks = [ensure_future(self.add_session()) for _ in range(n)]
    #     return await gather(*tasks)
    
    def _get_cookies_str(self, cookie_jar) -> str:
        cookies_str = ""
        for cookie in cookie_jar:
            cookies_str += f"{cookie.key}={cookie.value}; "
        return cookies_str[:-2]
    
    async def create(self, messages: list[dict], model: str) -> dict:
        session: Session = None
        start = time()
        session = await self._get_connection()
        session.busy = True

        await session.connection.send_str("42[\"perplexity_playground\",{\"version\":\"2.1\",\"source\":\"default\",\"model\":\"" + model + "\",\"messages\":" + dumps(messages) + "}]")
        print(f"took {time() - start} seconds to connect")
        async for msg in session.connection:
            msg = msg.data
            if msg == "2":
                await session.connection.send_str("3")
            elif msg.startswith("42"):
                print(msg)
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
    labs = FastLabs()

    # tasks = [ensure_future(labs.create_sync([{'role': 'user', 'content': "Translate this full part of a textbook from English to French:\n\n\n\n\n- Market share: This measures the organization's position in the market. An increase in market share can indicate successful innovation.\n\n\n\n- Profitability: This measures the organization's financial performance. An increase in profitability can indicate successful innovation.\n\n\n\n- Customer satisfaction: This measures the organization's ability to meet customer needs and expectations. An increase in customer satisfaction can indicate successful innovation.\n\n\n\nIn conclusion, measuring innovation performance requires a comprehensive set of metrics that reflect the multifaceted nature of innovation. These metrics should be aligned with the organization's strategic objectives and take into account the inputs, processes, outputs, and outcomes of innovation. By doing so, organizations can gain a deeper understanding of their innovation performance and make informed decisions about their innovation strategy and planning.\n\n\n\n```\n\n#### 5.3c Analyzing Innovation Performance\n\n\n\nAfter identifying the appropriate metrics and collecting the necessary data, the next step in measuring innovation performance is to analyze the results. This involves interpreting the data, identifying trends, and drawing conclusions about the organization's innovation performance.\n\n\n\n##### Analyzing Inputs to Innovation\n\n\n\nWhen analyzing inputs to innovation, organizations should consider not only the quantity of resources invested but also the quality of these investments. For example, an organization might invest a large amount of money in R&D, but if these funds are not used effectively, the organization's innovation performance may not improve. Similarly, an organization might have a large number of employees involved in innovation activities, but if these employees lack the necessary skills or motivation, their efforts may not lead to successful innovation.\n\n\n\n##### Analyzing Innovation Processes\n\n\n\nIn analyzing innovation processes, organizations should look for signs of efficiency and effectiveness. For example, a shorter time to market can indicate that an organization is able to quickly turn ideas into marketable products or services. However, organizations should also be aware that rushing a product to market can sometimes lead to lower quality or missed opportunities for further innovation.\n\n\n\nAn organization's innovation pipeline can provide valuable insights into its innovation performance. A healthy pipeline with a steady flow of projects at different stages of development can indicate that the organization has a sustainable approach to innovation. However, if the pipeline is clogged with projects that are not progressing, this could suggest problems with the organization's innovation processes.\n\n\n\n##### Analyzing Outputs of Innovation\n\n\n\nOutputs of innovation are perhaps the most tangible indicators of an organization's innovation performance. When analyzing these outputs, organizations should consider both the quantity and quality of new products or services. For example, an organization might produce a large number of new products, but if these products do not meet customer needs or fail to gain market share, the organization's innovation performance may be lacking.\n\n\n\nIn addition to new products or services, organizations should also consider other outputs of innovation, such as patents or publications. These can provide evidence of an organization's innovative capabilities and contribute to its reputation as an innovator.\n\n\n\nIn conclusion, analyzing innovation performance involves a careful examination of the inputs, processes, and outputs of innovation. By interpreting the data and identifying trends, organizations can gain valuable insights into their innovation performance and identify areas for improvement.\n\n```\n\n\n\n### 5.4 Innovation Portfolio Management\n\n\n\nInnovation Portfolio Management (IPM) is a strategic approach that involves managing an organization's innovation activities as a portfolio of investments. This approach allows organizations to balance their resources and risks across a range of innovation projects, ensuring that they are not overly reliant on any single project or type of innovation. \n\n\n\n#### 5.4a Understanding Innovation Portfolio Management\n\n\n\nInnovation Portfolio Management is based on the principle that not all innovations are created equal. Some innovations may have a high potential for success but also carry a high level of risk, while others may be more certain but offer lower potential returns. By managing their innovation activities as a portfolio, organizations can balance these risks and rewards, ensuring that they have a mix of projects that can deliver both short-term wins and long-term growth.\n\n\n\n\n\n", 'priority': 0}], "mixtral-8x7b-instruct")) for _ in range(3)]
    # await gather(*tasks)

    async for c in labs.create([{'role': 'user', 'content': "Translate this full part of a textbook from English to French:\n\n\n\n\n- Market share: This measures the organization's position in the market. An increase in market share can indicate successful innovation.\n\n\n\n- Profitability: This measures the organization's financial performance. An increase in profitability can indicate successful innovation.\n\n\n\n- Customer satisfaction: This measures the organization's ability to meet customer needs and expectations. An increase in customer satisfaction can indicate successful innovation.\n\n\n\nIn conclusion, measuring innovation performance requires a comprehensive set of metrics that reflect the multifaceted nature of innovation. These metrics should be aligned with the organization's strategic objectives and take into account the inputs, processes, outputs, and outcomes of innovation. By doing so, organizations can gain a deeper understanding of their innovation performance and make informed decisions about their innovation strategy and planning.\n\n\n\n```\n\n#### 5.3c Analyzing Innovation Performance\n\n\n\nAfter identifying the appropriate metrics and collecting the necessary data, the next step in measuring innovation performance is to analyze the results. This involves interpreting the data, identifying trends, and drawing conclusions about the organization's innovation performance.\n\n\n\n##### Analyzing Inputs to Innovation\n\n\n\nWhen analyzing inputs to innovation, organizations should consider not only the quantity of resources invested but also the quality of these investments. For example, an organization might invest a large amount of money in R&D, but if these funds are not used effectively, the organization's innovation performance may not improve. Similarly, an organization might have a large number of employees involved in innovation activities, but if these employees lack the necessary skills or motivation, their efforts may not lead to successful innovation.\n\n\n\n##### Analyzing Innovation Processes\n\n\n\nIn analyzing innovation processes, organizations should look for signs of efficiency and effectiveness. For example, a shorter time to market can indicate that an organization is able to quickly turn ideas into marketable products or services. However, organizations should also be aware that rushing a product to market can sometimes lead to lower quality or missed opportunities for further innovation.\n\n\n\nAn organization's innovation pipeline can provide valuable insights into its innovation performance. A healthy pipeline with a steady flow of projects at different stages of development can indicate that the organization has a sustainable approach to innovation. However, if the pipeline is clogged with projects that are not progressing, this could suggest problems with the organization's innovation processes.\n\n\n\n##### Analyzing Outputs of Innovation\n\n\n\nOutputs of innovation are perhaps the most tangible indicators of an organization's innovation performance. When analyzing these outputs, organizations should consider both the quantity and quality of new products or services. For example, an organization might produce a large number of new products, but if these products do not meet customer needs or fail to gain market share, the organization's innovation performance may be lacking.\n\n\n\nIn addition to new products or services, organizations should also consider other outputs of innovation, such as patents or publications. These can provide evidence of an organization's innovative capabilities and contribute to its reputation as an innovator.\n\n\n\nIn conclusion, analyzing innovation performance involves a careful examination of the inputs, processes, and outputs of innovation. By interpreting the data and identifying trends, organizations can gain valuable insights into their innovation performance and identify areas for improvement.\n\n```\n\n\n\n### 5.4 Innovation Portfolio Management\n\n\n\nInnovation Portfolio Management (IPM) is a strategic approach that involves managing an organization's innovation activities as a portfolio of investments. This approach allows organizations to balance their resources and risks across a range of innovation projects, ensuring that they are not overly reliant on any single project or type of innovation. \n\n\n\n#### 5.4a Understanding Innovation Portfolio Management\n\n\n\nInnovation Portfolio Management is based on the principle that not all innovations are created equal. Some innovations may have a high potential for success but also carry a high level of risk, while others may be more certain but offer lower potential returns. By managing their innovation activities as a portfolio, organizations can balance these risks and rewards, ensuring that they have a mix of projects that can deliver both short-term wins and long-term growth.\n\n\n\n\n\n", 'priority': 0}], "mixtral-8x7b-instruct"):
        print(c)

    # await sleep(1)

    # tasks = [ensure_future(labs.create_sync([{"role": "user", "content": "Wo is the current french president ?", "priority": 0}], "mixtral-8x7b-instruct")) for _ in range(2)]
    # await gather(*tasks)

    print(len(labs.sessions))
    await labs.close()

if __name__ == "__main__":
    run(main())