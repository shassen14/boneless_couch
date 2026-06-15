# tests/unit/core/test_socials.py
import pytest

from couchd.core import socials

_LINKS = [
    {"name": "YouTube", "url": "https://youtube.com/@me"},
    {"name": "GitHub", "url": "https://github.com/me"},
]


@pytest.fixture
def links(mock_settings):
    mock_settings.SOCIAL_LINKS = _LINKS
    yield _LINKS
    mock_settings.SOCIAL_LINKS = []


def test_format_for_chat_joins_all(links):
    out = socials.format_for_chat()
    assert out == "YouTube: https://youtube.com/@me | GitHub: https://github.com/me"


def test_format_for_chat_custom_separator(links):
    assert socials.format_for_chat(sep=" • ").count(" • ") == 1


def test_format_for_chat_empty_returns_none(mock_settings):
    mock_settings.SOCIAL_LINKS = []
    assert socials.format_for_chat() is None


def test_find_by_name_case_insensitive_substring(links):
    assert socials.find_by_name("git") == "https://github.com/me"


def test_find_by_name_missing_returns_none(links):
    assert socials.find_by_name("twitter") is None


def test_timer_messages_one_per_social(links):
    msgs = socials.timer_messages()
    assert msgs == [
        "Find us on YouTube! https://youtube.com/@me",
        "Find us on GitHub! https://github.com/me",
    ]
