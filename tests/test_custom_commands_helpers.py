"""Unit tests for custom_commands helper functions."""

from unittest.mock import MagicMock

from cogs.custom_commands import _paginate_list_lines, _resolve_response


def test_resolve_response_user_name_before_user_mention():
    message = MagicMock()
    message.author.display_name = "Display"
    message.author.mention = "<@999>"
    message.guild.name = "Guild"
    message.channel.mention = "<#1>"
    out = _resolve_response("Hello {user.name} — ping {user}", message, 3)
    assert out == "Hello Display — ping <@999>"


def test_paginate_list_lines_splits_at_limit():
    lines = ["x" * 100 for _ in range(50)]
    pages = _paginate_list_lines(lines, max_chars=500)
    assert len(pages) > 1
    assert all(len(p) <= 500 for p in pages)
    assert "\n".join(pages) == "\n".join(lines)
