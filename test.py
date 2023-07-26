from Perplexity import Perplexity

perplexity = Perplexity()

while True:
    inp = str(input("> "))
    c = perplexity.search(inp)
    if c:
        print(c.json_answer_text["answer"])