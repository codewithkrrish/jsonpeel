"""Tests for jsonpeel.core — loading, querying, listing and diffing."""

import json

import pytest

from jsonpeel.core import (
    colourise,
    diff_json,
    get_path,
    list_paths,
    load_json,
    parse_path,
    render,
)
from jsonpeel.errors import JsonPeelError

SAMPLE = {
    "user": {"name": "krrish", "tags": ["dev", "bots"], "meta": {}},
    "count": 3,
    "active": True,
    "note": None,
}


# --- loading ---------------------------------------------------------------

def test_load_valid_object():
    assert load_json('{"a": 1}', "test") == {"a": 1}


def test_load_valid_from_array_and_scalar():
    assert load_json("[1, 2]", "test") == [1, 2]
    assert load_json('"hi"', "test") == "hi"


def test_load_empty_input():
    with pytest.raises(JsonPeelError, match="empty input"):
        load_json("   \n", "test")


def test_load_invalid_json_names_the_problem():
    with pytest.raises(JsonPeelError) as excinfo:
        load_json('{"a": }', "broken.json")
    assert "broken.json" in str(excinfo.value)
    assert "line 1" in str(excinfo.value)


# --- dot-path parsing ------------------------------------------------------

def test_parse_path_plain_and_indexed():
    assert parse_path("user.name") == ["user", "name"]
    assert parse_path("items[0].id") == ["items", 0, "id"]
    assert parse_path("[0].a") == [0, "a"]
    assert parse_path("a[-1]") == ["a", -1]


def test_parse_path_empty_and_broken():
    with pytest.raises(JsonPeelError):
        parse_path("")
    with pytest.raises(JsonPeelError):
        parse_path("a[")
    with pytest.raises(JsonPeelError):
        parse_path("a[one]")


# --- querying --------------------------------------------------------------

def test_get_path_nested_and_index():
    assert get_path(SAMPLE, "user.name") == "krrish"
    assert get_path(SAMPLE, "user.tags[1]") == "bots"
    assert get_path(SAMPLE, "user.tags[-1]") == "bots"
    assert get_path(SAMPLE, "count") == 3


def test_get_path_missing_key():
    with pytest.raises(JsonPeelError, match="no such key: 'user.age'"):
        get_path(SAMPLE, "user.age")


def test_get_path_index_into_object():
    with pytest.raises(JsonPeelError, match="is not an array"):
        get_path(SAMPLE, "user[0]")


def test_get_path_key_into_array():
    with pytest.raises(JsonPeelError, match="is not an object"):
        get_path(SAMPLE, "user.tags.name")


def test_get_path_index_out_of_range():
    with pytest.raises(JsonPeelError, match="out of range"):
        get_path(SAMPLE, "user.tags[9]")


# --- listing paths ---------------------------------------------------------

def test_list_paths():
    assert list_paths(SAMPLE) == [
        "user.name",
        "user.tags[0]",
        "user.tags[1]",
        "user.meta",
        "count",
        "active",
        "note",
    ]


def test_list_paths_empty_containers():
    assert list_paths({}) == []
    assert list_paths({"a": {}}) == ["a"]
    assert list_paths({"a": []}) == ["a"]


# --- diffing ---------------------------------------------------------------

def test_diff_identical():
    assert diff_json(SAMPLE, SAMPLE) == []


def test_diff_changed_added_removed():
    lines = diff_json({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4})
    assert lines == ["~ b: 2 -> 3", "+ c: 4"]


def test_diff_removed_and_nested():
    lines = diff_json({"a": {"x": 1, "y": 2}}, {"a": {"x": 1}})
    assert lines == ["- a.y: 2"]


def test_diff_lists_by_index():
    lines = diff_json([1, 2], [1, 2, 3])
    assert lines == ["+ [2]: 3"]


def test_diff_type_change():
    assert diff_json({"a": 1}, {"a": "1"}) == ['~ a: 1 -> "1"']


# --- rendering -------------------------------------------------------------

def test_render_pretty_and_compact():
    pretty = render({"b": 1, "a": 2}, indent=2)
    assert pretty == '{\n  "b": 1,\n  "a": 2\n}'
    assert render({"b": 1, "a": 2}, compact=True) == '{"b":1,"a":2}'
    assert render({"b": 1, "a": 2}, sort_keys=True).index('"a"') < render(
        {"b": 1, "a": 2}, sort_keys=True
    ).index('"b"')


def test_render_keeps_unicode_readable():
    assert "café" in render({"drink": "café"})


def test_colourise_marks_keys_strings_numbers_literals():
    coloured = colourise('{\n  "name": "krrish",\n  "n": 3,\n  "ok": true\n}')
    assert "\x1b[36m\"name\"" in coloured  # cyan key
    assert "\x1b[32m\"krrish\"" in coloured  # green string
    assert "\x1b[33m3" in coloured  # yellow number
    assert "\x1b[35mtrue" in coloured  # magenta literal
    assert coloured.endswith("\x1b[0m}") or "\x1b[0m" in coloured


def test_render_plain_when_colour_disabled():
    assert "\x1b[" not in render({"a": 1}, compact=True, colour=False)
    assert "\x1b[" not in render({"a": 1}, colour=False)
