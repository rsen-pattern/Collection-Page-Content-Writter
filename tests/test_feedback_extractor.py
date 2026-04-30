"""Tests for feedback_extractor module."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.feedback_extractor import extract_banned_phrases


class TestExtractBannedPhrases:
    def test_empty_feedback_returns_empty(self):
        assert extract_banned_phrases("fake-key", "") == []

    def test_whitespace_only_returns_empty(self):
        assert extract_banned_phrases("fake-key", "   ") == []

    def test_parses_one_phrase_per_line(self):
        with patch("core.feedback_extractor.OpenAI") as mock_openai:
            instance = mock_openai.return_value
            instance.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="perfect for\ndiscover our range"))]
            )
            result = extract_banned_phrases("key", "Don't use 'perfect for' or 'discover our range'.")
            assert result == ["perfect for", "discover our range"]

    def test_handles_none_response(self):
        with patch("core.feedback_extractor.OpenAI") as mock_openai:
            instance = mock_openai.return_value
            instance.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="NONE"))]
            )
            result = extract_banned_phrases("key", "Be more concise.")
            assert result == []

    def test_handles_none_lowercase(self):
        with patch("core.feedback_extractor.OpenAI") as mock_openai:
            instance = mock_openai.return_value
            instance.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="none"))]
            )
            result = extract_banned_phrases("key", "General tone feedback only.")
            assert result == []

    def test_filters_overlong_extractions(self):
        long_line = " ".join(["word"] * 15)
        with patch("core.feedback_extractor.OpenAI") as mock_openai:
            instance = mock_openai.return_value
            instance.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=f"perfect for\n{long_line}"))]
            )
            result = extract_banned_phrases("key", "any feedback")
            assert result == ["perfect for"]

    def test_strips_quotes_and_bullets(self):
        with patch("core.feedback_extractor.OpenAI") as mock_openai:
            instance = mock_openai.return_value
            instance.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="- 'perfect for'\n* \"discover our range\""))]
            )
            result = extract_banned_phrases("key", "any")
            assert "perfect for" in result
            assert "discover our range" in result

    def test_empty_lines_skipped(self):
        with patch("core.feedback_extractor.OpenAI") as mock_openai:
            instance = mock_openai.return_value
            instance.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="perfect for\n\n\ndiscover our range\n"))]
            )
            result = extract_banned_phrases("key", "any")
            assert result == ["perfect for", "discover our range"]

    def test_base_url_gets_v1_appended(self):
        with patch("core.feedback_extractor.OpenAI") as mock_openai:
            instance = mock_openai.return_value
            instance.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="NONE"))]
            )
            extract_banned_phrases("key", "feedback", base_url="https://bifrost.pattern.com")
            call_kwargs = mock_openai.call_args[1]
            assert call_kwargs["base_url"].endswith("/v1")
