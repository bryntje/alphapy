"""
Tests for status cog release notes: markdown truncation and dangling header cleanup.
"""

import pytest
from cogs.status import _drop_dangling_last_header, _truncate_release_notes_md


class TestDropDanglingLastHeader:
    """Tests for _drop_dangling_last_header."""

    def test_returns_unchanged_when_last_line_is_not_header(self):
        text = "Line one.\n\nLine two.\nLast content."
        assert _drop_dangling_last_header(text) == text

    def test_drops_trailing_blank_lines_then_checks_last(self):
        text = "Content here.\n\n## Improved\n"
        assert _drop_dangling_last_header(text) == "Content here."

    def test_drops_single_trailing_header(self):
        text = "Fixed\n- Bullet one\n- Bullet two\n\n## Improved"
        assert _drop_dangling_last_header(text) == "Fixed\n- Bullet one\n- Bullet two"

    def test_drops_header_with_trailing_blanks(self):
        text = "Some text.\n\n## Section\n\n  \n"
        assert _drop_dangling_last_header(text) == "Some text."

    def test_empty_after_strip_returns_empty(self):
        assert _drop_dangling_last_header("\n\n## Only\n\n") == ""

    def test_keeps_content_ending_with_non_header(self):
        text = "Ends with normal line."
        assert _drop_dangling_last_header(text) == text


class TestTruncateReleaseNotesMd:
    """Tests for _truncate_release_notes_md."""

    def test_empty_input_returns_empty(self):
        assert _truncate_release_notes_md("", 100) == ""
        assert _truncate_release_notes_md("   ", 100) == ""

    def test_short_text_unchanged(self):
        text = "Short release notes."
        assert _truncate_release_notes_md(text, 500) == text

    def test_normalizes_leading_hashtag_three(self):
        text = "### Fixed\n- Item"
        assert _truncate_release_notes_md(text, 500).startswith("## Fixed")

    def test_truncates_by_sections_when_over_max(self):
        text = "## Fixed\n- A\n- B\n\n## Improved\n- C\n- D"
        out = _truncate_release_notes_md(text, 25)
        assert len(out) <= 25
        assert "## Fixed" in out or "Fixed" in out
        assert out.strip() and not out.strip().endswith("## Improved")

    def test_result_never_ends_with_bare_header(self):
        text = "## Fixed\n- One\n- Two\n\n## Improved\n- Three"
        for max_len in (20, 40, 60, 100):
            out = _truncate_release_notes_md(text, max_len)
            if out.strip():
                last_line = out.strip().split("\n")[-1].strip()
                assert not last_line.startswith("## "), f"Result should not end with header: {out!r}"

    def test_strips_improved_section_when_ends_with_read_full(self):
        body = "## Fixed\n- Item\n\n## Improved\nRead full release notes on GitHub."
        out = _truncate_release_notes_md(body, 500)
        assert "## Improved" not in out
        assert "Read full release notes on GitHub." not in out
        assert "## Fixed" in out or "Fixed" in out
