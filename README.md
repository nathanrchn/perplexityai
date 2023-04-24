# perplexityai
A python api to use perplexity.ai

# Usage
```python
perplexity = Perplexity()
answer = perplexity.search("What is the meaning of life?")
print(answer.json_answer_text["answer"])
```