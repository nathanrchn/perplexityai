# perplexityai
A python api to use perplexity.ai

# Usage
You can just import the Perplexity class and use it like this:
```python
from perplexity import Perplexity

perplexity = Perplexity()
answer = perplexity.search("What is the meaning of life?")
for a in answer:
    print(a)
perplexity.close()
```

You can even create a cli tool with it:
```python
from perplexity import Perplexity

perplexity = Perplexity()

while True:
    inp = str(input("> "))
    c = perplexity.search(inp)
    if c:
        print(c)

perplexity.close()
```