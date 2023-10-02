def return_just_next_token(answer: iter[dict]) -> str:
    length = 0
    for partial_answer in answer:
        yield partial_answer["answer"][length:]
        length = len(partial_answer["answer"])