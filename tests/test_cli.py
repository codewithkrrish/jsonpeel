"""Tests for the jsonpeel CLI — flags, files, exit codes, no tracebacks."""

import io
import json
import os
import subprocess
import sys

import pytest

from jsonpeel.cli import main

DOC = {"user": {"name": "krrish", "tags": ["dev", "bots"]}, "count": 3}
DOC_TEXT = json.dumps(DOC)


def run_cli(argv, stdin_text=None, monkeypatch=None):
    """Run main() capturing stdout/stderr; returns (exit_code, out, err)."""
    if monkeypatch is not None and stdin_text is not None:
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
    import contextlib

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture()
def doc_file(tmp_path):
    path = tmp_path / "doc.json"
    path.write_text(DOC_TEXT, encoding="utf-8")
    return str(path)


# --- happy paths -----------------------------------------------------------

def test_pretty_print_file(doc_file):
    code, out, _ = run_cli([doc_file])
    assert code == 0
    assert json.loads(out) == DOC
    assert '\n  "user": {' in out


def test_pretty_print_from_stdin(monkeypatch):
    code, out, _ = run_cli([], stdin_text=DOC_TEXT, monkeypatch=monkeypatch)
    assert code == 0
    assert json.loads(out) == DOC


def test_query_flag(doc_file):
    code, out, _ = run_cli([doc_file, "-q", "user.name"])
    assert code == 0
    assert out.strip() == '"krrish"'
    code, out, _ = run_cli([doc_file, "-q", "user.tags[0]"])
    assert out.strip() == '"dev"'


def test_keys_flag(doc_file):
    code, out, _ = run_cli([doc_file, "--keys"])
    assert code == 0
    assert out.splitlines() == [
        "user.name",
        "user.tags[0]",
        "user.tags[1]",
        "count",
    ]


def test_validate_flag(doc_file):
    code, _, err = run_cli([doc_file, "--validate"])
    assert code == 0
    assert "valid JSON" in err


def test_compact_and_sort(doc_file):
    code, out, _ = run_cli([doc_file, "--compact", "--sort-keys"])
    assert code == 0
    assert out.strip() == '{"count":3,"user":{"name":"krrish","tags":["dev","bots"]}}'


def test_diff_identical_and_different(doc_file, tmp_path):
    code, _, err = run_cli([doc_file, "--diff", doc_file])
    assert code == 0
    assert "identical" in err

    other = tmp_path / "other.json"
    other.write_text(json.dumps({"user": {"name": "krrish", "tags": ["dev"]}, "count": 4}))
    code, out, _ = run_cli([doc_file, "--diff", str(other)])
    assert code == 1  # like diff(1): differences found
    assert '~ count: 3 -> 4' in out
    assert '- user.tags[1]: "bots"' in out


# --- output files ----------------------------------------------------------

def test_output_file_written_atomically(doc_file, tmp_path):
    target = tmp_path / "out.json"
    code, out, _ = run_cli([doc_file, "-o", str(target)])
    assert code == 0
    assert out == ""  # nothing on stdout when writing to a file
    assert json.loads(target.read_text()) == DOC
    # no stray temp files left behind
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".jsonpeel-")]


def test_output_refuses_to_overwrite_without_force(doc_file, tmp_path):
    target = tmp_path / "out.json"
    target.write_text("keep me")
    code, _, err = run_cli([doc_file, "-o", str(target)])
    assert code == 1
    assert "--force" in err
    assert target.read_text() == "keep me"


def test_output_force_overwrites(doc_file, tmp_path):
    target = tmp_path / "out.json"
    target.write_text("old")
    code, _, _ = run_cli([doc_file, "-o", str(target), "--force"])
    assert code == 0
    assert json.loads(target.read_text()) == DOC


def test_dry_run_writes_nothing(doc_file, tmp_path):
    target = tmp_path / "out.json"
    code, out, err = run_cli([doc_file, "-o", str(target), "--dry-run"])
    assert code == 0
    assert not target.exists()
    assert "dry run" in err
    assert json.loads(out) == DOC


# --- errors: human messages, correct codes, no tracebacks ------------------

def test_missing_file(doc_file):
    code, _, err = run_cli(["/no/such/file.json"])
    assert code == 1
    assert "cannot read" in err
    assert "Traceback" not in err


def test_invalid_json_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{oops")
    code, _, err = run_cli([str(bad)])
    assert code == 1
    assert "invalid JSON" in err
    assert "Traceback" not in err


def test_invalid_json_stdin(monkeypatch):
    code, _, err = run_cli([], stdin_text="not json", monkeypatch=monkeypatch)
    assert code == 1
    assert "invalid JSON" in err


def test_empty_stdin(monkeypatch):
    code, _, err = run_cli([], stdin_text="  ", monkeypatch=monkeypatch)
    assert code == 1
    assert "empty input" in err


def test_missing_query_key(doc_file):
    code, _, err = run_cli([doc_file, "-q", "user.age"])
    assert code == 1
    assert "no such key" in err


def test_bad_flag_combo(doc_file):
    code, _, err = run_cli([doc_file, "--diff", doc_file, "--keys"])
    assert code == 1
    assert "--diff cannot be combined" in err


def test_negative_indent(doc_file):
    code, _, err = run_cli([doc_file, "--indent", "-1"])
    assert code == 1
    assert "--indent" in err


def test_unknown_flag_exits_2(doc_file):
    with pytest.raises(SystemExit) as excinfo:
        main([doc_file, "--nope"])
    assert excinfo.value.code == 2


# --- the real entry point --------------------------------------------------

def test_module_entry_point(tmp_path):
    """`python -m jsonpeel` works exactly like the console script."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(os.path.dirname(__file__), "..", "src")
    doc = tmp_path / "doc.json"
    doc.write_text(DOC_TEXT)
    proc = subprocess.run(
        [sys.executable, "-m", "jsonpeel", str(doc), "-q", "count"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "3"
