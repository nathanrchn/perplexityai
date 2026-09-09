from io import StringIO
import unittest
from unittest.mock import patch

from perplexity.cli import OutputWriter, build_parser, run


class FakeRenderer:
    instances = []

    def __init__(self):
        self.rendered = []
        self.closed = False
        FakeRenderer.instances.append(self)

    def render(self, text):
        self.rendered.append(text)

    def tidyup(self):
        self.closed = True


class FakePerplexity:
    instances = []

    def __init__(self, account):
        self.account = account
        self.closed = False
        FakePerplexity.instances.append(self)

    def search(self, prompt, mode):
        self.prompt = prompt
        self.mode = mode
        return [
            {
                "blocks": [
                    {
                        "intended_usage": "ask_text",
                        "markdown_block": {"answer": "# Hello"},
                    }
                ]
            },
            {
                "blocks": [
                    {
                        "intended_usage": "ask_text",
                        "markdown_block": {"answer": "# Hello\n\nWorld"},
                    }
                ]
            },
        ]

    def close(self):
        self.closed = True


class FakePerplexityWithThread(FakePerplexity):
    def search(self, prompt, mode):
        events = super().search(prompt, mode)
        for event in events:
            event["thread_url_slug"] = "thread-slug-123"
        return events


class TtyStringIO(StringIO):
    def isatty(self):
        return True


class OutputWriterTest(unittest.TestCase):
    def setUp(self):
        FakeRenderer.instances = []

    def test_raw_writes_plain_text_without_streamdown(self):
        stream = StringIO()
        writer = OutputWriter(raw=True, stream=stream)

        with patch("perplexity.cli._load_streamdown", side_effect=AssertionError("unexpected streamdown")):
            writer.write("# Hello")
            writer.write("\n")
            writer.close()

        self.assertEqual(stream.getvalue(), "\n# Hello\n")
        self.assertEqual(FakeRenderer.instances, [])

    def test_rendered_output_uses_streamdown_and_tidyup(self):
        stream = StringIO()
        writer = OutputWriter(raw=False, stream=stream)

        with patch("perplexity.cli._load_streamdown", side_effect=FakeRenderer):
            writer.write("# Hello")
            writer.write("\n")
            writer.close()

        self.assertEqual(stream.getvalue(), "\n")
        self.assertEqual(FakeRenderer.instances[0].rendered, ["# Hello\n", "\n"])
        self.assertTrue(FakeRenderer.instances[0].closed)


class CliRunTest(unittest.TestCase):
    def setUp(self):
        FakePerplexity.instances = []
        FakeRenderer.instances = []

    def test_run_streams_parsed_output_to_streamdown_by_default(self):
        args = build_parser().parse_args(["-a", "me@example.com", "hello", "world"])

        with patch("perplexity.cli.Perplexity", FakePerplexity):
            with patch("perplexity.cli._load_streamdown", side_effect=FakeRenderer):
                self.assertEqual(run(args), 0)

        self.assertEqual(FakePerplexity.instances[0].account, "me@example.com")
        self.assertEqual(FakePerplexity.instances[0].prompt, "hello world")
        self.assertEqual(FakePerplexity.instances[0].mode, "concise")
        self.assertEqual(FakeRenderer.instances[0].rendered, ["# Hello\n\n", "World\n", "\n"])
        self.assertTrue(FakeRenderer.instances[0].closed)
        self.assertTrue(FakePerplexity.instances[0].closed)

    def test_run_raw_prints_parsed_markdown_without_event_dump(self):
        args = build_parser().parse_args(["--raw", "--pro", "hello"])
        stream = StringIO()

        with patch("perplexity.cli.Perplexity", FakePerplexity):
            with patch("perplexity.cli.sys.stdout", stream):
                self.assertEqual(run(args), 0)

        self.assertEqual(stream.getvalue(), "\n# Hello\n\nWorld\n")
        self.assertEqual(FakePerplexity.instances[0].mode, "copilot")
        self.assertEqual(FakeRenderer.instances, [])

    def test_run_prints_thread_url(self):
        args = build_parser().parse_args(["--raw", "hello"])
        stream = StringIO()

        with patch("perplexity.cli.Perplexity", FakePerplexityWithThread):
            with patch("perplexity.cli.sys.stdout", stream):
                self.assertEqual(run(args), 0)

        self.assertTrue(
            stream.getvalue().endswith(
                "\nhttps://www.perplexity.ai/search/thread-slug-123\n"
            ),
            stream.getvalue(),
        )

    def test_run_colors_thread_url_on_tty(self):
        args = build_parser().parse_args(["--raw", "hello"])
        stream = TtyStringIO()

        with patch("perplexity.cli.Perplexity", FakePerplexityWithThread):
            with patch("perplexity.cli.sys.stdout", stream):
                self.assertEqual(run(args), 0)

        self.assertIn(
            "\n\033[38;5;250mhttps://www.perplexity.ai/search/thread-slug-123\033[0m\n",
            stream.getvalue(),
        )

    def test_run_omits_thread_url_when_disabled(self):
        args = build_parser().parse_args(["--raw", "--no-url", "hello"])
        stream = StringIO()

        with patch("perplexity.cli.Perplexity", FakePerplexityWithThread):
            with patch("perplexity.cli.sys.stdout", stream):
                self.assertEqual(run(args), 0)

        self.assertNotIn("perplexity.ai/search", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
