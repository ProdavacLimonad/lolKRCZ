"""Settings for lolKRCZ. The defaults match a standard macOS install; override any key in `config.json` next to this
file (see config.example.json). Unknown keys are rejected.

  host_locale   the locale Riot installs and League runs as. It decides the in-game font: the game picks one font
                file per locale, and the Korean client's font is the one assigned to ko_KR.   default "ko_KR"
  text_locale   the locale whose text you want to read. Its genuine Localized/Global and UI wads are swapped in
                under the host locale's names while LoL runs.                                  default "cs_CZ"
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__)) + '/'

DEFAULTS = {
    'lol_app': '/Applications/League of Legends.app',
    'riot_app': '/Users/Shared/Riot Games/Riot Client.app',
    'riot_metadata': '/Users/Shared/Riot Games/Metadata',
    'riot_logs': '~/Library/Logs/Riot Games/Riot Client/Riot Client Logs',
    'patchline': 'live',
    'host_locale': 'ko_KR',
    'text_locale': 'cs_CZ',
    'min_free_gb': 6.0,       # setup/refresh abort below this much free disk (a locale download is ~3.5 GB)
    'settle_seconds': 10,     # watcher: the client must be up this long before the swap
    'quit_seconds': 6,        # watcher: client and game gone this long before the swap is undone
}

LOCALE_RE = re.compile(r'[a-z]{2}_[A-Z]{2}')


def load():
    cfg = dict(DEFAULTS)
    path = HERE + 'config.json'
    if os.path.exists(path):
        with open(path) as f:
            user = json.load(f)
        unknown = sorted(set(user) - set(DEFAULTS))
        if unknown:
            raise SystemExit('config.json: unknown keys %s' % unknown)
        cfg.update(user)
    for k in ('host_locale', 'text_locale'):
        if not LOCALE_RE.fullmatch(cfg[k]):
            raise SystemExit('config.json: %s must look like cs_CZ, got %r' % (k, cfg[k]))
    if cfg['host_locale'] == cfg['text_locale']:
        raise SystemExit('config.json: host_locale and text_locale must differ (there is nothing to swap otherwise)')
    return cfg


CFG = load()
HOST, TEXT = CFG['host_locale'], CFG['text_locale']
LOL_DIR = CFG['lol_app'].rstrip('/') + '/Contents/LoL/'
FINAL = LOL_DIR + 'Game/DATA/FINAL/'
MANIFEST = LOL_DIR + 'Game.manifest'
CLIENT_SETTINGS = LOL_DIR + 'Config/LeagueClientSettings.yaml'
RIOT_APP = CFG['riot_app']
LOGDIR = os.path.expanduser(CFG['riot_logs']).rstrip('/') + '/'
YAML = '%s/league_of_legends.%s/league_of_legends.%s.product_settings.yaml' % (
    CFG['riot_metadata'].rstrip('/'), CFG['patchline'], CFG['patchline'])
ORIG = HERE + 'orig/'             # clones of the host locale's own wads, to put back
STATE = ORIG + 'state.json'
TEXTDIR = HERE + 'text/'          # genuine wads of the text locale, kept because Riot deletes them when it switches locale
TEXT_STATE = TEXTDIR + 'state.json'


def text_wads(locale):
    """Relative names (inside FINAL) of the two locale wads that carry the text of `locale`."""
    return ['Localized/Global.%s.wad.client' % locale, 'UI.%s.wad.client' % locale]


def yaml_locale():
    """The locale Riot currently has installed (settings.locale of product_settings.yaml)."""
    with open(YAML) as f:
        m = re.search(r'(?m)^    locale: "(%s)"' % LOCALE_RE.pattern, f.read())
    return m.group(1) if m else None


def yaml_available():
    """locale_data.available_locales of product_settings.yaml: the locales Riot offers for your region."""
    with open(YAML) as f:
        return re.findall(r'(?m)^    - "(%s)"' % LOCALE_RE.pattern, f.read())
