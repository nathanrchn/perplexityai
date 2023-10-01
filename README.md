# perplexityai
A python api to use perplexity.ai

# Installation
You can install the package with pip and git:
```bash
pip install git+https://github.com/nathanrchn/perplexityai.git
```

# Basic Usage
You can just import the Perplexity class and use it like this:
```python
from perplexity import Perplexity

perplexity = Perplexity()
answer = perplexity.search("What is the meaning of life?")
for a in answer:
    print(a)
perplexity.close()
```

# Advanced Usage
With the new version, you can now sign in to your account and use the api to its full potential.
For now the only provider supported is email, but more will be added in the future.
```python
from perplexity import Perplexity

perplexity = Perplexity("example@email.com")
```
And then you will receive an email from Perplexity AI. Copy the link associated with the `Sign in` button in the middle of the email.
The program will create a new file: `.perplexity_session` for keeping the session cookies.

I you are logged in, you can now upload files to your account.
```python
perplexity.upload("path/to/file")
```
or
```python
perplexity.upload("https://example.com/file")
```
