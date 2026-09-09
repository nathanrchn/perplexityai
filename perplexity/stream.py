from re import Match, search, sub
from typing import Any, Dict, Iterable, Optional


class AnswerStreamParser:
    """Extract live answer text deltas from Perplexity websocket events."""

    THREAD_URL_BASE = "https://www.perplexity.ai/search"

    def __init__(self) -> None:
        self.text = ""
        self.raw_text = ""
        self.thread_slug: Optional[str] = None
        self._chunk_count = 0
        self._source_urls: set[str] = set()
        self._annotations: list[dict[str, Any]] = []
        self.sources: list[dict[str, str]] = []

    def feed(self, event: Dict[str, Any]) -> str:
        self._collect_thread_slug(event)
        self._collect_sources(event)
        state = self._event_state(event)
        if state is None:
            return ""
        raw_text, chunk_count = state
        text = self._stable_answer_text(self._format_answer_text(raw_text))
        self.raw_text = raw_text

        if text.startswith(self.text):
            delta = text[len(self.text):]
            self.text = text
            self._chunk_count = chunk_count
            return delta

        if self.text.startswith(text):
            return ""

        prefix_len = self._common_prefix_len(self.text, text)
        if prefix_len == len(self.text):
            delta = text[prefix_len:]
            self.text = text
            self._chunk_count = chunk_count
            return delta

        return ""

    def parse(self, events: Iterable[Dict[str, Any]]) -> Iterable[str]:
        for event in events:
            delta = self.feed(event)
            if delta:
                yield delta

    def format_answer(self, citations: bool = False) -> str:
        if not citations:
            return self.text

        markers = self._citation_markers()
        if not markers:
            return self.text

        text = self.text
        for offset, marker in sorted(markers.items(), reverse=True):
            if 0 <= offset <= len(text):
                text = text[:offset] + marker + text[offset:]
        return text

    def has_citations(self) -> bool:
        return bool(self._citation_markers())

    def format_sources(self, cited_only: bool = False) -> str:
        sources = self._cited_sources() if cited_only else self.sources
        if not sources:
            return ""

        lines = ["", "---", "", "## Sources", ""]
        for default_index, source in enumerate(sources, start=1):
            index = source.get("number", str(default_index))
            name = source.get("name") or source.get("url") or "Source"
            url = source.get("url", "")
            if url:
                lines.append(f"- **[{index}]** [{name}]({url})")
            else:
                lines.append(f"- **[{index}]** {name}")
        return "\n".join(lines)

    def thread_url(self) -> str:
        if not self.thread_slug:
            return ""
        return f"{self.THREAD_URL_BASE}/{self.thread_slug}"

    def _collect_thread_slug(self, event: Dict[str, Any]) -> None:
        if self.thread_slug:
            return
        for key in ("thread_url_slug", "backend_uuid"):
            value = event.get(key)
            if isinstance(value, str) and value:
                self.thread_slug = value
                return

    def _collect_sources(self, event: Dict[str, Any]) -> None:
        blocks = event.get("blocks")
        if not isinstance(blocks, list):
            return

        for block in blocks:
            web_result_block = block.get("web_result_block")
            if not isinstance(web_result_block, dict):
                continue
            web_results = web_result_block.get("web_results")
            if not isinstance(web_results, list):
                continue
            for result in web_results:
                if not isinstance(result, dict):
                    continue
                url = result.get("url")
                if not isinstance(url, str) or not url or url in self._source_urls:
                    continue
                name = result.get("name")
                self._source_urls.add(url)
                self.sources.append({
                    "name": name if isinstance(name, str) else url,
                    "url": url,
                })

    def _event_state(self, event: Dict[str, Any]) -> Optional[tuple[str, int]]:
        blocks = event.get("blocks")
        if not isinstance(blocks, list):
            return None

        for usage in ("ask_text_0_markdown", "ask_text"):
            for block in blocks:
                if block.get("intended_usage") == usage:
                    markdown_block = block.get("markdown_block")
                    self._collect_annotations(markdown_block)
                    state = self._markdown_block_state(markdown_block)
                    if state is not None:
                        return state

        for block in blocks:
            if isinstance(block.get("markdown_block"), dict):
                markdown_block = block["markdown_block"]
                self._collect_annotations(markdown_block)
                state = self._markdown_block_state(markdown_block)
                if state is not None:
                    return state

        return None

    def _markdown_block_state(self, block: Any) -> Optional[tuple[str, int]]:
        if not isinstance(block, dict):
            return None

        chunks = block.get("chunks")
        answer = block.get("answer")
        if isinstance(answer, str):
            chunk_count = len(chunks) if isinstance(chunks, list) else self._chunk_count
            return answer, chunk_count

        if not isinstance(chunks, list):
            return None

        chunk_text = "".join(chunk for chunk in chunks if isinstance(chunk, str))
        offset = block.get("chunk_starting_offset", 0)
        if isinstance(offset, int) and offset == self._chunk_count:
            return self.raw_text + chunk_text, offset + len(chunks)

        if offset == 0:
            return chunk_text, len(chunks)

        return None

    def _common_prefix_len(self, left: str, right: str) -> int:
        length = min(len(left), len(right))
        for index in range(length):
            if left[index] != right[index]:
                return index
        return length

    def _format_answer_text(self, text: str) -> str:
        lines = text.splitlines(keepends=True)
        in_fence = False
        formatted_lines = []

        for line in lines:
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                formatted_lines.append(line)
            elif in_fence:
                formatted_lines.append(line)
            else:
                formatted_lines.append(self._format_inline_citations(line))

        return "".join(formatted_lines)

    def _format_inline_citations(self, text: str) -> str:
        parts = text.split("`")
        for index in range(0, len(parts), 2):
            parts[index] = self._space_citations(parts[index])
        return "`".join(parts)

    def _space_citations(self, text: str) -> str:
        def format_marker(match: Match[str]) -> str:
            formatted = f"`{match.group(0)}`"
            if match.start() == 0:
                return formatted
            return " " + formatted

        return sub(r"(?<![\s\[`])\[\d+\](?:\[\d+\])*", format_marker, text)

    def _stable_answer_text(self, text: str) -> str:
        incomplete_marker = search(r"(?<![\s\[])\[\d*$", text)
        if incomplete_marker:
            return text[:incomplete_marker.start()]
        return text

    def _collect_annotations(self, block: Any) -> None:
        if not isinstance(block, dict):
            return

        annotations = block.get("inline_token_annotations")
        if not isinstance(annotations, list):
            return

        self._annotations = [
            annotation for annotation in annotations
            if isinstance(annotation, dict)
        ]

    def _citation_markers(self) -> dict[int, str]:
        markers: dict[int, list[int]] = {}
        for annotation in self._annotations:
            end = self._annotation_end(annotation)
            if end is None:
                continue
            numbers = self._annotation_source_numbers(annotation)
            if not numbers:
                continue
            markers.setdefault(end, [])
            for number in numbers:
                if number not in markers[end]:
                    markers[end].append(number)

        return {
            offset: "".join(f"`[{number}]`" for number in sorted(numbers))
            for offset, numbers in markers.items()
        }

    def _annotation_end(self, annotation: dict[str, Any]) -> Optional[int]:
        for key in ("end", "end_index", "end_offset", "stop", "stop_index"):
            value = annotation.get(key)
            if isinstance(value, int):
                return value

        span = annotation.get("span") or annotation.get("text_span") or annotation.get("token_span")
        if isinstance(span, dict):
            for key in ("end", "end_index", "end_offset", "stop", "stop_index"):
                value = span.get(key)
                if isinstance(value, int):
                    return value

        return None

    def _annotation_source_numbers(self, annotation: dict[str, Any]) -> list[int]:
        values = []
        for key in (
            "source_index", "source_indices", "source_ids", "source_id",
            "citation_index", "citation_indices", "citation_ids", "citation_id",
            "web_result_index", "web_result_indices",
        ):
            if key in annotation:
                values.extend(self._flatten(annotation[key]))

        for key in ("url", "source_url", "citation_url"):
            value = annotation.get(key)
            if isinstance(value, str):
                number = self._source_number_for_url(value)
                if number:
                    values.append(number)

        numbers: list[int] = []
        for value in values:
            number = self._normalize_source_number(value)
            if number and number not in numbers:
                numbers.append(number)
        return numbers

    def _normalize_source_number(self, value: Any) -> Optional[int]:
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        if not isinstance(value, int):
            return None
        if 0 <= value < len(self.sources):
            return value + 1
        if 1 <= value <= len(self.sources):
            return value
        return None

    def _source_number_for_url(self, url: str) -> Optional[int]:
        for index, source in enumerate(self.sources, start=1):
            if source.get("url") == url:
                return index
        return None

    def _flatten(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            values: list[Any] = []
            for item in value:
                values.extend(self._flatten(item))
            return values
        if isinstance(value, dict):
            values: list[Any] = []
            for key in (
                "index", "indices", "id", "ids", "source_index",
                "source_indices", "citation_index", "citation_indices",
                "url", "source_url", "citation_url",
            ):
                if key in value:
                    values.extend(self._flatten(value[key]))
            return values
        return [value]

    def _cited_sources(self) -> list[dict[str, str]]:
        numbers = sorted({
            number
            for annotation in self._annotations
            for number in self._annotation_source_numbers(annotation)
        })
        return [
            {"number": str(number), **self.sources[number - 1]}
            for number in numbers
            if 1 <= number <= len(self.sources)
        ]
