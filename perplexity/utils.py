from typing import Iterable, Dict

def return_just_next_token(answer: Iterable[Dict]) -> str:
    length = 0
    for partial_answer in answer:
        if "answer" in partial_answer:
            yield partial_answer["answer"][length:]
            length = len(partial_answer["answer"])
        elif "output" in partial_answer:
            yield partial_answer["output"][length:]
            length = len(partial_answer["output"])
