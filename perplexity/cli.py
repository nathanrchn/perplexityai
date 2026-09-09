import argparse
import shutil
import sys
from typing import Optional, TextIO

import argcomplete

from perplexity.config import configure_mail
from perplexity import AnswerStreamParser, Perplexity


LIGHT_GREY = "\033[38;5;250m"
COLOR_RESET = "\033[0m"


class OutputWriter:
    def __init__(self, raw: bool = False, stream: Optional[TextIO] = None) -> None:
        self.raw = raw
        self.stream = stream or sys.stdout
        self._renderer = None
        self._buffer = ""
        self._started = False

    def write(self, text: str) -> None:
        if not text:
            return

        if self.raw:
            self._begin()
            self.stream.write(text)
            self.stream.flush()
            return

        self._buffer += text
        last_para = self._buffer.rfind("\n\n")
        if last_para >= 0:
            to_render = self._buffer[:last_para + 2]
            self._buffer = self._buffer[last_para + 2:]
            self._render(to_render)

    def dim(self, text: str) -> str:
        if not text or not self._colors_enabled():
            return text
        return f"{LIGHT_GREY}{text}{COLOR_RESET}"

    def _colors_enabled(self) -> bool:
        isatty = getattr(self.stream, "isatty", None)
        return bool(isatty and isatty())

    def close(self) -> None:
        if self._buffer:
            self._render(self._buffer)
            self._buffer = ""
        if self._renderer is not None:
            self._render_trailing()
            self._renderer.tidyup()
        self.stream.flush()

    def _render(self, text: str) -> None:
        self._begin()
        renderer = self._streamdown()
        if hasattr(renderer, "state"):
            renderer.state.list_item_stack = []
            renderer.state.in_list = False
            renderer.state.list_indent_text = 0
        renderer.render(text)

    def _begin(self) -> None:
        if self._started:
            return
        self._started = True
        self.stream.write("\n")

    def _render_trailing(self) -> None:
        self._streamdown().render("\n")

    def _streamdown(self):
        if self._renderer is None:
            self._renderer = _load_streamdown()
        return self._renderer


def _load_streamdown():
    import streamdown
    import streamdown.sdlib as sdlib

    sd = streamdown.Streamdown()
    sd.setup()
    _patch_streamdown(sd, sdlib)
    return sd


def _patch_streamdown(sd, sdlib) -> None:
    terminal_cols = shutil.get_terminal_size().columns
    sd.state.WidthArg = min(terminal_cols, 100)
    sd.width_calc()

    orig_emit_h = sdlib.emit_h

    def emit_h_left(level, text):
        from streamdown.sdlib import line_format, text_wrap, BOLD, FG, FGRESET

        if level > 2:
            return orig_emit_h(level, text)
        text = line_format(text)
        res = []
        for line in text_wrap(text):
            if level == 1:
                res.append(f"{sd.state.space_left()}\n{sd.state.space_left()}{BOLD[0]}{line}{BOLD[1]}\n")
            else:
                res.append(f"{sd.state.space_left()}\n{sd.state.space_left()}{BOLD[0]}{FG}{sd.Style.Bright}{line}{BOLD[1]}{FGRESET}")
        return "\n".join(res)

    sdlib.emit_h = emit_h_left


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Perplexity CLI")
    parser.add_argument("-a", "--account", metavar="EMAIL", help="account email for authenticated requests")
    parser.add_argument("-r", "--raw", action="store_true", help="print parsed markdown without terminal rendering")
    parser.add_argument("-s", "--sources", action="store_true", help="append sources")
    parser.add_argument("-p", "--pro", action="store_true", help="use Pro search")
    parser.add_argument("--no-url", action="store_true", help="do not print the perplexity thread url")
    parser.add_argument("prompt", nargs="+", help="search prompt")
    return parser


def configure(argv: list[str]) -> int:
    config_parser = argparse.ArgumentParser(
        prog=f"{argv[0]} config",
        description="Configure perplexity-cli",
    )
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    config_subparsers.add_parser("mail", help="configure IMAP mail login")
    config_args = config_parser.parse_args(argv[2:])
    if config_args.config_command == "mail":
        configure_mail()
    return 0


def run(args: argparse.Namespace) -> int:
    perplexity = Perplexity(args.account)
    writer = OutputWriter(raw=args.raw)
    try:
        answer = perplexity.search(" ".join(args.prompt), mode="copilot" if args.pro else "concise")
        stream_parser = AnswerStreamParser()
        for event in answer:
            delta = stream_parser.feed(event)
            writer.write(delta)

        if stream_parser.text:
            writer.write("\n")

        if args.sources:
            sources = stream_parser.format_sources(cited_only=stream_parser.has_citations())
            if sources:
                writer.write(sources + "\n")

        if not args.no_url:
            url = stream_parser.thread_url()
            if url:
                writer.write(f"\n{writer.dim(url)}\n")
        return 0
    finally:
        try:
            writer.close()
        finally:
            perplexity.close()


def main(argv: Optional[list[str]] = None) -> int:
    argv = argv or sys.argv
    try:
        if len(argv) > 1 and argv[1] == "config":
            return configure(argv)

        parser = build_parser()
        argcomplete.autocomplete(parser)
        return run(parser.parse_args(argv[1:]))
    except KeyboardInterrupt:
        sys.stderr.write("\n")
        sys.stderr.flush()
        return 130
