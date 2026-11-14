# jsonpeel

Peek inside JSON from the terminal — pretty-print it, pull out one value by dot-path, or diff two files. Zero dependencies, standard library only.

## Why I made this

I kept piping API responses and config files into `python -m json.tool` and then squinting. It prints the whole blob or nothing. I wanted three small things in one place: a readable print, a way to grab `user.addresses[0].city` without opening an editor, and a quick diff when a config file changes and nobody remembers what changed.

So I built jsonpeel. It does those three things and stays out of the way.

## Quick look

```console
$ curl -s https://api.github.com/users/codewithkrrish | jsonpeel -q "login"
"codewithkrrish"

$ jsonpeel config.json
{
  "server": {
    "host": "localhost",
    "port": 8080
  },
  "debug": true
}

$ jsonpeel config.json --keys
server.host
server.port
debug
```

Colour is on when output goes to a terminal, off when piped or written to a file. Keys are cyan, strings green, numbers yellow, `true`/`false`/`null` magenta.

Diffing two files:

```console
$ jsonpeel old.json --diff new.json
~ server.port: 8080 -> 9090
+ server.workers: 4
- debug: true
$ echo $?
1
```

Like `diff`, it exits 1 when the files differ and prints `identical` (to stderr) when they don't.

## Install

Needs Python 3.9 or newer. Not on PyPI yet, so install straight from GitHub:

```console
pip install git+https://github.com/codewithkrrish/jsonpeel.git
```

Or clone it and run it without installing anything:

```console
git clone https://github.com/codewithkrrish/jsonpeel.git
cd jsonpeel
python -m jsonpeel data.json
```

## Usage

```
jsonpeel [FILE] [options]
```

Read from a file, or from stdin when no file is given. `jsonpeel -` reads stdin explicitly.

| Flag | What it does |
| --- | --- |
| `-q PATH`, `--query PATH` | Print only the value at a dot-path, e.g. `user.name`, `items[0].id` |
| `--keys` | List every leaf path in the document, one per line |
| `--validate` | Only check the JSON is valid; prints `valid JSON` to stderr |
| `--diff OTHER` | Compare FILE with OTHER, show added / removed / changed values |
| `--indent N` | Spaces per level (default 2) |
| `--sort-keys` | Sort object keys alphabetically |
| `--compact` | Single-line minified output |
| `--color auto\|always\|never` | Colour output (default `auto`: only on a terminal) |
| `-o FILE`, `--output FILE` | Write the result to a file instead of stdout |
| `--force` | Overwrite the `-o` file if it already exists |
| `--dry-run` | With `-o`: show what would be written, write nothing |

Exit codes: `0` success, `1` a problem (bad JSON, missing key, files differ in `--diff` mode), `2` a usage error.

A few things worth knowing:

- Query paths use dots and `[n]` indexes. Negative indexes work too: `items[-1]` is the last item.
- Errors are one plain line on stderr, never a traceback. `jsonpeel data.json -q user.age` on a file with no `age` key just says `jsonpeel: no such key: 'user.age'`.
- `-o` refuses to overwrite an existing file unless you pass `--force`, and writes go through a temp file plus rename, so a crash can't leave a half-written file behind.

## Limitations

Honest ones, because every tool has them:

- Keys containing a literal dot can't be queried with `-q` yet — the dot is always a separator. (Workaround: `--keys` plus a quick grep, or use the whole document.)
- `--diff` compares by position in arrays, not by matching items — reordering a list shows up as a pile of changes.
- Colouring is hand-rolled ANSI, so if your terminal doesn't speak ANSI you'll want `--color never`.
- It reads the whole document into memory, so it's not the tool for multi-gigabyte JSON streams.

## Project structure

```
jsonpeel/
├── src/jsonpeel/
│   ├── __init__.py   # version
│   ├── cli.py        # argument parsing, exit codes, nothing else
│   ├── core.py       # loading, dot-paths, diff, rendering, atomic writes
│   └── errors.py     # the one exception type the CLI turns into a message
├── tests/
│   ├── test_core.py
│   └── test_cli.py
└── pyproject.toml
```

The split is deliberate: `core.py` has no idea about the terminal, so everything in it is importable and testable on its own. Run the tests with `pytest` — 42 of them, covering happy paths and the awkward cases (empty input, corrupt JSON, missing keys, overwrites, bad flags).

## License

MIT — see [LICENSE](LICENSE).

## Author

Krrish — [github.com/codewithkrrish](https://github.com/codewithkrrish)
