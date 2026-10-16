# lolKRCZ

**Play League of Legends with the Korean client's font and Czech text. macOS only, using only genuine Riot files.**

League chooses the in-game font from the locale it runs as, and the Korean client's font (UttumDotum) is assigned to
`ko_KR`. lolKRCZ lets Riot install `ko_KR` and, only while the game runs, puts the genuine Czech text files in place of the
Korean ones. You get the Korean font with Czech text. The two locales are configurable, so any "font of locale A, text of
locale B" pair works.

> **Unofficial, use at your own risk.** Not affiliated with, endorsed by or sponsored by Riot Games. Riot does not
> support modifying game files. This tool never edits a file, it only swaps one genuine Riot file for another while the
> game runs and swaps it back afterwards, and it never touches the game or client executables. macOS has no Vanguard.
> It can still stop working with any patch. League of Legends is a trademark of Riot Games, Inc.

## Know this before you start

- **The client menu is Korean.** Client and game share one locale, so with `ko_KR` installed the lobby, shop and other
  client screens are in Korean. That is the price of the Korean font.
- **UttumDotum has no glyphs for Czech accented letters** (checked in its character map: none of `áčďéěíňóřšťúůýž` are
  in it). What the game draws for them depends on its own fallback. Look at your own screen before you rely on it.
- **macOS only** (APFS `clonefile`). Windows is not supported: it cannot be tested here and Vanguard is much stricter.
- Developed and tested on one machine (EUNE, `cs_CZ` to `ko_KR`). The code is unit tested against a fake install, the
  one-command setup in `krcz_refresh.py` is built from steps the author ran by hand, but it has not been run end to end
  in exactly this form against Riot's servers. Treat it as a working prototype.

## How it works

1. **Font by locale.** `UI.wad.client` holds `ux/fonts`, a Riot PROP file where every font type has a default font and
   per-locale overrides. `ko_kr` maps to `UttumDotum.ttf`, `cs_cz` has no override. Run `python3 tools/show_fonts.py`
   to see the table of your own install.
2. **Host locale.** Riot installs `ko_KR`, so the game runs as `ko_KR` and picks that font. The text it shows comes from
   `Localized/Global.ko_KR.wad.client` and `UI.ko_KR.wad.client`.
3. **Swap, never edit.** Riot's wads are signed. A modified one is rejected (`WadFileMountError`, then the client starts a
   repair). Genuine files are fine under any name, so `krcz` keeps Riot's genuine `Global.cs_CZ` and `UI.cs_CZ` in `text/`
   and clones them over the `ko_KR` ones. Size and mtime are kept (APFS `clonefile`).
4. **Only while LoL runs.** Riot Client checks the files when it starts and on every Play click and re-downloads anything
   that differs (3 GB or more). So the swap is made about 10 seconds after the client is up and undone when LoL quits, by a small
   background watcher.
5. **The client must ask for `ko_KR` at every start.** LeagueClient passes `LeagueClientSettings.yaml` `globals.locale` to
   Riot Client as `--locale`. If that says `cs_CZ`, Riot reinstalls Czech and deletes `ko_KR`. Setup pins it to `ko_KR`.

## Setup

Needs macOS, Python 3.9+, League installed (the text locale should already be a language Riot offers for your region,
see `locale_data.available_locales` in Riot's `product_settings.yaml`) and at least 6 GB of free disk during setup (the
scripts check it, a locale download is about 3.5 GB).

```sh
git clone https://github.com/ProdavacLimonad/lolKRCZ.git && cd lolKRCZ
cp config.example.json config.json        # optional: change host_locale / text_locale
# quit League and Riot Client, then
python3 -I krcz_refresh.py --dry-run      # checks only
python3 -I krcz_refresh.py --force        # installs the text locale, keeps its files, installs the host locale, pins the client
python3 -I install_agent.py               # writes the LaunchAgent plist, then:
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.lolkrcz.watch.plist
```

Setup takes a few minutes of downloading (about 7 GB). If Riot Client waits for a click on Update or Play, a notification
tells you. From then on just start League as usual: about ten seconds after the client appears the text is swapped, and it
is undone when you quit. `krcz_watch.log` shows what happened.

After a LoL patch the watcher refuses to swap outdated files and sends a notification. Quit League and run
`python3 -I krcz_refresh.py` again.

## Commands

| Script | What it does |
|---|---|
| `krcz_refresh.py` | The whole setup and the rebuild after a patch (`--dry-run`, `--force`) |
| `krcz_watch.py` | The watcher (run by the LaunchAgent): swap on, swap off, recovers after a crash or reboot |
| `krcz.py` | The pieces by hand: `stash-text`, `snapshot`, `on`, `off`, `status` |
| `krcz_install.py LOCALE` | Make Riot install one locale and wait for it |
| `install_agent.py` | Write the LaunchAgent plist (`--label`, `--show`) |
| `tools/show_fonts.py` | Print the font file League uses for every locale |

Settings live in `config.json` (`host_locale`, `text_locale`, install paths); see `krcz_config.py`.

## Undo

```sh
launchctl bootout gui/$(id -u)/com.lolkrcz.watch      # stop the watcher
python3 -I krcz.py off                                # with League closed: Riot's own files back
cp "/Applications/League of Legends.app/Contents/LoL/Config/LeagueClientSettings.yaml.bak-krcz" \
   "/Applications/League of Legends.app/Contents/LoL/Config/LeagueClientSettings.yaml"
```

Then start League normally: Riot reinstalls your original locale (a few GB). Delete the clone folder when you are done.

## Tests

```sh
python3 -m unittest discover -s tests -v          # macOS: a fake install, the real swap code
```

## Česky

Hra bere písmo podle locale, ve kterém běží, a písmo korejského klienta (UttumDotum) patří locale `ko_KR`. lolKRCZ nechá
Riot nainstalovat `ko_KR` a jen během hry podsune pravé české textové soubory (`Global.cs_CZ`, `UI.cs_CZ`) na místo
korejských, takže máš korejské písmo a český text. Nic se neupravuje, jen se klonují pravé soubory Riotu a po hře se vrací
zpět. Menu klienta je kvůli tomu korejsky a UttumDotum nemá české znaky s diakritikou, takže jejich vzhled si zkontroluj
na vlastní obrazovce. Jen macOS, neoficiální, na vlastní riziko. Postup je v sekci Setup výše.

## License

MIT, see [LICENSE](LICENSE).
