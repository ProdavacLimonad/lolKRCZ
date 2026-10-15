# lolKRCZ

**A Korean League of Legends client, read in Czech.** A searchable glossary of the League of Legends client UI in two or
three languages, built from your own installation. The defaults are Korean (what you see) and Czech (what you read), but
any pair of the client's languages works.

If your client is in a language you can't read (a foreign-region account, a Korean client for its font, a translated
interface you want to cross-check), you type a word in your language and see what the label looks like in the client,
or you pick a screen and see every label on it next to its translation. Rows are paired by Riot's own translation keys,
so the text on the right is the official translation, not a machine one.

It works on **Windows and macOS** (and anywhere Python runs, with `--lol`). It only **reads** your installation and
writes one self-contained HTML page. Nothing in the game is modified.

> Not affiliated with, endorsed by or sponsored by Riot Games. League of Legends is a trademark of Riot Games, Inc.
> The generated page contains Riot's strings, so keep it for yourself and don't publish it. This repository contains
> none of them.

## Quick start

You need Python 3.9 or newer. The translation tables are compressed with zstd, so install a decoder once:

```sh
pip install zstandard
```

Then run it (the install is found automatically):

```sh
python lol_glossary.py
```

This writes `lol-client-glossary.html` next to where you ran it. Open it in a browser. The defaults are
**what you see: Korean, what you read: Czech, plus English**. Pick other languages with `--see`, `--read` and `--also`:

```sh
python lol_glossary.py --see ja_jp --read en_us --also "" --ui en -o ja-to-en.html
python lol_glossary.py --lol "D:\Riot Games\League of Legends"
python lol_glossary.py --list-locales        # which languages your client has
```

| Option | Meaning |
|---|---|
| `--lol PATH` | Folder that contains `Plugins` (auto-detected when omitted) |
| `--see LOCALE` | Language of the client you look at (default `ko_kr`) |
| `--read LOCALE` | Language you read (default `cs_cz`) |
| `--also LOCALE` | Optional third column, `""` for none (default `en_us`) |
| `--ui cs\|en` | Language of the page itself (default: Czech when `--read` is Czech, otherwise English) |
| `-o FILE` | Output file (default `lol-client-glossary.html`) |
| `--list-locales` | Print the locales available in your client and exit |

Locale names are the lower-case codes League uses, for example `ko_kr`, `cs_cz`, `en_us`, `ja_jp`, `de_de`, `zh_cn`.

## Using the page

- Type in any of the languages. Accents are ignored (`nastaveni` finds `Nastavení`) and Hangul, kana and so on work too.
- **Only short labels** hides long sentences so buttons and tabs come first.
- The list on the left jumps to a screen (Settings, Store, Champion select, ...). Press `/` to focus the search box.
- `‹name›` marks a value the client fills in itself.
- Light and dark themes follow your system. The page works offline and needs no JavaScript to be read.

## Where the data comes from

Every client plugin (`Plugins/<plugin>/assets.wad`) carries `plugins/<plugin>/global/<locale>/trans.json` with the same
keys for every language. The tool reads those entries (WAD v3 files, entries addressed by the XXH64 hash of their
lower-cased path), decompresses them and pairs the texts by key. Developer filler such as "Lorem ipsum" is skipped.
Screens are named after the plugin that owns them, and the plugin id is shown as a tooltip.

## Windows notes

- Install folders are looked up in Riot's `RiotClientInstalls.json` (`%ProgramData%\Riot Games`), then in the usual
  `C:\Riot Games\League of Legends` and `D:\Riot Games\League of Legends`. Use `--lol` for anything else.
- The author developed this on macOS. The test suite builds synthetic client folders and runs on Windows, macOS and
  Linux in CI, but it has not been run against a real Windows installation of the client yet. If a folder layout or a
  table differs on your machine, please open an issue and attach the output of `python lol_glossary.py --list-locales`.
- Reading files while the client is open is fine, the tool never writes to the installation.

## Troubleshooting

| Message | What to do |
|---|---|
| `League of Legends not found` | Pass the folder that contains `Plugins` with `--lol` |
| `translation tables are zstd compressed` | `pip install zstandard` (or use Python 3.14, or a `zstd` command line tool) |
| `No translation tables for X and Y` | Run `--list-locales` and pick locales your client has |
| The page is missing a language | Riot only ships the tables of the languages the client supports for your region |

## Development

```sh
python -m unittest discover -s tests -v
```

The tool is a single file, `lol_glossary.py`, with no dependencies besides an optional zstd decoder.

## Česky

Nástroj vyrobí z tvé instalace LoL **prohledávatelný slovník klienta**: hledáš česky (nebo anglicky) a vidíš, jak
popisek vypadá například v korejském klientu, nebo projdeš obrazovku a máš vedle sebe všechny popisky a oficiální
český překlad Riotu. Instalaci jen čte, nic v ní nemění. Spuštění: `pip install zstandard`, pak `python lol_glossary.py`.
Výsledek (`lol-client-glossary.html`) obsahuje texty Riotu, nech si ho pro sebe a nezveřejňuj ho.

## License

MIT, see [LICENSE](LICENSE).
