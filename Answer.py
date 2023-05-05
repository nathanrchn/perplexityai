from json import loads

class Answer:
    def __init__(self, uuid: str, gpt4: bool, text: str, search_focus: str, backend_uuid: str, query_str: str, related_queries: list[str]) -> None:
        self.uuid = uuid
        self.gpt4 = gpt4
        self.text = text
        self.search_focus = search_focus
        self.backend_uuid = backend_uuid
        self.query_str = query_str
        self.related_queries = related_queries

        self.json_answer_text = loads(self.text)

        self.details: Details = None

class Details:
    def __init__(self, uuid: str, text: str) -> None:
        self.uuid = uuid
        self.text = text

        self.json_answer_text = loads(self.text)