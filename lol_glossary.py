#!/usr/bin/env python3
"""lol-client-glossary: a searchable glossary of the League of Legends client UI in two or three languages.

Every client plugin (Plugins/<plugin>/assets.wad) ships its translation tables (trans.json) for all locales under the
same keys. This tool pairs the text of the language your client is in (default ko_kr) with the text of the language
you read (default cs_cz) and optionally a third one (default en_us), and writes one self-contained HTML page you can
search while you play.

    python lol_glossary.py                      # auto-detects the install, writes ./lol-client-glossary.html
    python lol_glossary.py --lol "D:\\Riot Games\\League of Legends"
    python lol_glossary.py --see ja_jp --read en_us --also "" --ui en -o glossary.html
    python lol_glossary.py --list-locales

It only reads your installation. The output contains Riot's strings, so keep it for yourself and do not publish it.
Not affiliated with Riot Games. Needs Python 3.9+ and, for the compressed tables, `pip install zstandard`
(or Python 3.14, or a `zstd` command line tool).
"""
import argparse
import glob
import gzip
import html
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time

__version__ = '1.0.0'

# ----------------------------------------------------------------------------------------------- path hashing (WAD)
_M = (1 << 64) - 1
_P1, _P2, _P3, _P4, _P5 = (11400714785074694791, 14029467366897019727, 1609587929392839161,
                           9650029242287828579, 2870177450012600261)


def _rotl(x, r):
    return ((x << r) | (x >> (64 - r))) & _M


def _round(acc, inp):
    return (_rotl((acc + inp * _P2) & _M, 31) * _P1) & _M


def _merge(acc, val):
    return ((acc ^ _round(0, val)) * _P1 + _P4) & _M


def xxh64(data, seed=0):
    """XXH64, the hash League WADs use for the (lower-cased) path of every entry."""
    n, i = len(data), 0
    if n >= 32:
        v1, v2, v3, v4 = (seed + _P1 + _P2) & _M, (seed + _P2) & _M, seed & _M, (seed - _P1) & _M
        while i <= n - 32:
            v1 = _round(v1, int.from_bytes(data[i:i + 8], 'little'))
            v2 = _round(v2, int.from_bytes(data[i + 8:i + 16], 'little'))
            v3 = _round(v3, int.from_bytes(data[i + 16:i + 24], 'little'))
            v4 = _round(v4, int.from_bytes(data[i + 24:i + 32], 'little'))
            i += 32
        h = (_rotl(v1, 1) + _rotl(v2, 7) + _rotl(v3, 12) + _rotl(v4, 18)) & _M
        for v in (v1, v2, v3, v4):
            h = _merge(h, v)
    else:
        h = (seed + _P5) & _M
    h = (h + n) & _M
    while i + 8 <= n:
        h = (_rotl(h ^ _round(0, int.from_bytes(data[i:i + 8], 'little')), 27) * _P1 + _P4) & _M
        i += 8
    if i + 4 <= n:
        h = (_rotl(h ^ ((int.from_bytes(data[i:i + 4], 'little') * _P1) & _M), 23) * _P2 + _P3) & _M
        i += 4
    while i < n:
        h = (_rotl(h ^ ((data[i] * _P5) & _M), 11) * _P1) & _M
        i += 1
    h ^= h >> 33
    h = (h * _P2) & _M
    h ^= h >> 29
    h = (h * _P3) & _M
    return h ^ (h >> 32)


def path_hash(path):
    return xxh64(path.lower().encode('utf-8'))


# ----------------------------------------------------------------------------------------------------- WAD reading
HEADER = 268   # 'RW', major, minor, 256 byte signature, 8 byte checksum; then a u32 entry count and 32 byte entries


class Wad:
    """Read-only view of a League WAD v3 file (only the table of contents is held in memory)."""

    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            head = f.read(HEADER + 4)
            if head[:2] != b'RW' or head[2] != 3:
                raise ValueError('%s is not a WAD v3 file' % path)
            n = struct.unpack('<I', head[HEADER:HEADER + 4])[0]
            raw = f.read(32 * n)
        self.entries = {}
        for k in range(n):
            h, off, csz, sz, typ, _dup, _sub, _sha = struct.unpack_from('<QIIIBBHQ', raw, 32 * k)
            self.entries[h] = (off, csz, sz, typ)

    def read(self, h):
        """Uncompressed bytes of the entry with path hash h, or None when the WAD has no such entry."""
        e = self.entries.get(h)
        if e is None:
            return None
        off, csz, sz, typ = e
        with open(self.path, 'rb') as f:
            f.seek(off)
            blob = f.read(csz)
        if typ == 0:
            return blob
        if typ == 1:
            return gzip.decompress(blob)
        if typ == 3:
            return zstd_decompress(blob)
        raise ValueError('unsupported WAD compression type %d in %s' % (typ, self.path))


def zstd_decompress(blob):
    try:
        import zstandard
        return zstandard.ZstdDecompressor().decompressobj().decompress(blob)
    except ImportError:
        pass
    try:
        from compression import zstd   # Python 3.14+
        return zstd.decompress(blob)
    except ImportError:
        pass
    exe = shutil.which('zstd')
    if exe:
        return subprocess.run([exe, '-d', '-c'], input=blob, capture_output=True, check=True).stdout
    raise SystemExit('The translation tables are zstd compressed. Install a decoder:  pip install zstandard')


# ------------------------------------------------------------------------------------------------ finding the install
def candidate_installs():
    env = os.environ.get('LOL_DIR')
    out = [env] if env else []
    out.append('/Applications/League of Legends.app/Contents/LoL')                       # macOS
    pd = os.environ.get('ProgramData', r'C:\ProgramData')
    try:                                                                                 # Windows: Riot's own list
        with open(os.path.join(pd, 'Riot Games', 'RiotClientInstalls.json'), encoding='utf-8') as f:
            for root in (json.load(f).get('associated_client') or {}):
                out.append(os.path.join(root.rstrip('/\\'), ''))
    except (OSError, ValueError):
        pass
    for base in (r'C:\Riot Games', r'D:\Riot Games', os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'Riot Games')):
        out.append(os.path.join(base, 'League of Legends'))
    return out


def find_lol(explicit=None):
    """Directory that contains Plugins/ (the macOS bundle's Contents/LoL or the Windows League of Legends folder)."""
    cands = [explicit] if explicit else candidate_installs()
    for c in cands:
        if not c:
            continue
        for sub in ('', os.path.join('Contents', 'LoL')):
            d = os.path.join(c, sub) if sub else c
            if os.path.isdir(os.path.join(d, 'Plugins')):
                return d
    raise SystemExit('League of Legends not found. Pass its folder with --lol "<path to the folder that holds Plugins>".')


# ------------------------------------------------------------------------------------------------------ translations
KNOWN_LOCALES = ['ar_ae', 'cs_cz', 'de_de', 'el_gr', 'en_au', 'en_gb', 'en_ph', 'en_sg', 'en_us', 'es_ar', 'es_es', 'es_mx',
                 'fr_fr', 'hu_hu', 'id_id', 'it_it', 'ja_jp', 'ko_kr', 'pl_pl', 'pt_br', 'ro_ro', 'ru_ru', 'th_th', 'tr_tr',
                 'vi_vn', 'zh_cn', 'zh_tw']


def trans_hash(plugin, locale):
    return path_hash('plugins/%s/global/%s/trans.json' % (plugin, locale))


def plugin_wads(plugins_dir):
    return {os.path.basename(os.path.dirname(w)): w for w in sorted(glob.glob(os.path.join(plugins_dir, '*', 'assets.wad')))}


def load_table(wad, plugin, locale):
    data = wad.read(trans_hash(plugin, locale))
    return json.loads(data.decode('utf-8-sig')) if data else None      # some tables start with a BOM


def txt(v):
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def collect(plugins_dir, see, read, also):
    """[(plugin, [(see text, read text, also text)])] for every plugin that has both tables, rows sorted by the read text."""
    sections = []
    for plugin, path in plugin_wads(plugins_dir).items():
        try:
            wad = Wad(path)
        except ValueError:
            continue
        a, b = load_table(wad, plugin, see), load_table(wad, plugin, read)
        if not a or not b:
            continue
        c = (load_table(wad, plugin, also) or (load_table(wad, plugin, 'default') if also == 'en_us' else None) or {}) if also else {}
        rows = []
        for k, v in a.items():
            if k in b and txt(v).strip():
                row = (txt(v), txt(b[k]), txt(c.get(k, '')))
                if any('lorem ipsum' in x.lower() for x in row):     # developer filler strings in Riot's tables
                    continue
                rows.append(row)
        rows.sort(key=lambda r: r[1].lower())
        if rows:
            sections.append((plugin, rows))
    return sections


# --------------------------------------------------------------------------------------------------------------- UI
SECTIONS = [   # plugin id -> (English title, Czech title)
    ('rcp-fe-lol-navigation', 'Main bar and navigation', 'Hlavní lišta a navigace'),
    ('rcp-fe-lol-parties', 'Play: lobby and game modes', 'Hra: lobby a výběr režimu'),
    ('rcp-fe-lol-champ-select', 'Champion select', 'Výběr šampiona'),
    ('rcp-fe-lol-postgame', 'Post-game', 'Po zápase'),
    ('rcp-fe-lol-settings', 'Settings', 'Nastavení'),
    ('rcp-fe-lol-social', 'Friends and chat', 'Přátelé a chat'),
    ('rcp-fe-lol-collections', 'Collection', 'Sbírka'),
    ('rcp-fe-lol-champion-details', 'Champion details', 'Detail šampiona'),
    ('rcp-fe-lol-profiles', 'Profile', 'Profil'),
    ('rcp-fe-lol-match-history', 'Match history', 'Historie zápasů'),
    ('rcp-fe-lol-leagues', 'Leagues and ladders', 'Ligy a žebříčky'),
    ('rcp-fe-lol-store', 'Store', 'Obchod'),
    ('rcp-fe-lol-yourshop', 'Your Shop', 'Tvůj obchod'),
    ('rcp-fe-lol-loot', 'Loot and crafting', 'Loot a crafting'),
    ('rcp-fe-lol-clash', 'Clash', 'Clash'),
    ('rcp-fe-lol-event-hub', 'Events', 'Eventy'),
    ('rcp-fe-lol-l10n', 'Common texts and currencies', 'Společné texty a měny'),
    ('rcp-fe-lol-shared-components', 'Shared interface parts', 'Sdílené prvky rozhraní'),
    ('rcp-fe-lol-premade-voice', 'Voice chat', 'Hlasový chat'),
    ('rcp-fe-lol-highlights', 'Highlights', 'Highlighty'),
    ('rcp-fe-lol-skins-picker', 'Skin picker', 'Výběr skinu'),
    ('rcp-fe-lol-new-player-experience', 'New player experience', 'Nový hráč'),
    ('rcp-fe-lol-esports-spectate', 'Esports spectating', 'Sledování esportu'),
    ('rcp-fe-lol-tft', 'Teamfight Tactics', 'Teamfight Tactics'),
    ('rcp-fe-tft', 'Teamfight Tactics (other)', 'Teamfight Tactics (ostatní)'),
    ('rcp-fe-lol-tft-promethium', 'Teamfight Tactics: Promethium', 'Teamfight Tactics: Promethium'),
    ('rcp-fe-lol-tft-team-planner', 'Teamfight Tactics: team planner', 'Teamfight Tactics: plánovač týmu'),
    ('rcp-fe-lol-objectives', 'Objectives', 'Cíle (objectives)'),
]
ORDER = [p for p, _, _ in SECTIONS]
TITLES = {'en': {p: en for p, en, _ in SECTIONS}, 'cs': {p: cs for p, _, cs in SECTIONS}}

STRINGS = {
    'en': dict(title='League of Legends client glossary', in_client='What you see in the client',
               help='Search in your language to see what the label looks like in the client, or browse a screen on the left. '
                    'Values in angle brackets, like \u2039name\u203a, are filled in by the client. Press / to jump to the search.',
               placeholder='Search in any of the languages', short='Only short labels', all='{n} texts',
               found='Found {n} of {m}', none='Nothing found. Try a shorter word or turn off "Only short labels".',
               nav='Client screens', search='Search'),
    'cs': dict(title='Slovník klienta League of Legends', in_client='Co vidíš v klientu',
               help='Hledej ve svém jazyce a zjistíš, jak popisek vypadá v klientu, nebo projdi obrazovku vlevo. '
                    'Hodnoty ve špičatých závorkách, třeba \u2039jméno\u203a, klient doplní sám. Klávesa / skočí do hledání.',
               placeholder='Hledat v kterémkoli z jazyků', short='Jen krátké popisky', all='{n} textů',
               found='Nalezeno {n} z {m}', none='Nic nenalezeno. Zkus kratší výraz nebo vypni „Jen krátké popisky“.',
               nav='Obrazovky klienta', search='Hledat'),
}
LANGS = {
    'en': dict(ko='Korean', cs='Czech', en='English', ja='Japanese', de='German', fr='French', es='Spanish', it='Italian',
               pl='Polish', pt='Portuguese', ru='Russian', tr='Turkish', zh='Chinese', hu='Hungarian', ro='Romanian',
               el='Greek', ar='Arabic', th='Thai', vi='Vietnamese', id='Indonesian'),
    'cs': dict(ko='Korejsky', cs='Česky', en='Anglicky', ja='Japonsky', de='Německy', fr='Francouzsky', es='Španělsky',
               it='Italsky', pl='Polsky', pt='Portugalsky', ru='Rusky', tr='Turecky', zh='Čínsky', hu='Maďarsky',
               ro='Rumunsky', el='Řecky', ar='Arabsky', th='Thajsky', vi='Vietnamsky', id='Indonésky'),
}

CSS = """
:root{--bg:#EEF1F5;--panel:#E3E8EF;--ink:#0A1428;--mute:#52607A;--read:#7A5C1E;--line:#C9D1DD;--focus:#0A7D75;--chip:#D7DEE8}
@media (prefers-color-scheme:dark){:root{--bg:#0A1428;--panel:#0F1D38;--ink:#EDE6D6;--mute:#9AA7BA;--read:#C8AA6E;--line:#22314F;--focus:#0AC8B9;--chip:#1A2A48}}
*{box-sizing:border-box}
html{scroll-padding-top:6.5rem}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
[lang=ko]{font-family:"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",system-ui,sans-serif}
[lang=ja]{font-family:"Hiragino Sans","Yu Gothic UI","Meiryo","Noto Sans JP",system-ui,sans-serif}
[lang=zh]{font-family:"PingFang SC","Microsoft YaHei","Noto Sans SC",system-ui,sans-serif}
[lang=th]{font-family:"Thonburi","Leelawadee UI","Noto Sans Thai",system-ui,sans-serif}
header{padding:1.1rem 1.25rem .4rem;max-width:90rem;margin:0 auto}
h1{margin:0 0 .2rem;font-size:1.35rem;font-weight:650;letter-spacing:-.01em}
.help{margin:0;color:var(--mute);font-size:.92rem;max-width:68ch}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:.6rem 1.25rem}
.bar>div{display:flex;gap:1.25rem;align-items:center;flex-wrap:wrap;max-width:90rem;margin:0 auto}
#q{flex:1 1 22rem;max-width:34rem;padding:.55rem .8rem;font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:6px}
#q:focus-visible,a:focus-visible,#short:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
.chk{display:flex;gap:.45rem;align-items:center;color:var(--ink);font-size:.92rem;cursor:pointer}
#stat{color:var(--mute);font-size:.9rem;margin-left:auto}
#none{margin:2rem 0;color:var(--mute)}
.shell{display:grid;grid-template-columns:16rem minmax(0,1fr);gap:0 2rem;padding:0 1.25rem 4rem;max-width:90rem;margin:0 auto}
nav{position:sticky;top:4.3rem;align-self:start;max-height:calc(100vh - 5rem);overflow:auto;padding:1rem 0}
nav ul{list-style:none;margin:0;padding:0}
nav a{display:flex;justify-content:space-between;gap:.5rem;padding:.3rem .5rem;border-radius:4px;color:var(--ink);text-decoration:none;font-size:.92rem}
nav a:hover{background:var(--panel)}
nav .n{color:var(--mute);font-variant-numeric:tabular-nums}
main{min-width:0}
section{content-visibility:auto;contain-intrinsic-size:auto 40rem;padding-top:1.4rem}
h2{margin:0 0 .4rem;font-size:1.15rem;font-weight:650;padding-bottom:.4rem;border-bottom:2px solid var(--read)}
h2 .c{color:var(--mute);font-weight:400;font-size:.9rem;margin-left:.4rem}
.heads,.r{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1.1fr) minmax(0,.9fr);gap:0 1.25rem}
.heads.two,.r.two{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
.heads{position:sticky;top:3.85rem;z-index:4;background:var(--bg);padding:.4rem 0;color:var(--mute);font-size:.85rem;border-bottom:1px solid var(--line)}
.r{padding:.5rem 0;border-bottom:1px solid var(--line);align-items:baseline}
.r[hidden],section[hidden],nav li[hidden]{display:none}
.r .s{font-size:1.12rem;font-weight:600}
.r .d{color:var(--read);font-weight:600}
.r .a{color:var(--mute);font-size:.92rem}
.r span{white-space:pre-line;overflow-wrap:anywhere}
.ph{font:.85em ui-monospace,Menlo,Consolas,monospace;background:var(--chip);padding:0 .3em;border-radius:3px;white-space:nowrap}
.ph::before{content:"\\2039"}
.ph::after{content:"\\203A"}
@media (max-width:860px){.shell{grid-template-columns:1fr}nav{position:static;max-height:none}.heads{display:none}.r,.r.two{grid-template-columns:1fr;gap:.1rem}html{scroll-padding-top:5.5rem}#stat{margin-left:0}}
"""

JS = r"""
(function(){
var UI=__UI__;
var q=document.getElementById('q'),stat=document.getElementById('stat'),short=document.getElementById('short'),none=document.getElementById('none');
var rows=[].slice.call(document.querySelectorAll('.r')),secs=[].slice.call(document.querySelectorAll('section'));
function norm(s){return s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();}
function fmt(n){return n.toLocaleString(document.documentElement.lang||undefined);}
var idx=rows.map(function(r){return norm(r.textContent);});
var len=rows.map(function(r){return r.querySelector('.d').textContent.length;}),t;
function run(){
 var v=norm(q.value.trim()),only=short.checked,shown=0;
 rows.forEach(function(r,i){var ok=(!v||idx[i].indexOf(v)>-1)&&(!only||len[i]<=40);r.hidden=!ok;if(ok)shown++;});
 secs.forEach(function(s){
  var n=s.querySelectorAll('.r:not([hidden])').length;
  s.hidden=n===0;
  var c=s.querySelector('h2 .c');if(c)c.textContent=fmt(n);
  var m=document.querySelector('nav [data-n="'+s.id+'"]');if(m){m.textContent=fmt(n);m.closest('li').hidden=n===0;}
 });
 none.hidden=shown>0;
 stat.textContent=(v||only)?UI.found.replace('{n}',fmt(shown)).replace('{m}',fmt(rows.length)):UI.all.replace('{n}',fmt(rows.length));
}
q.addEventListener('input',function(){clearTimeout(t);t=setTimeout(run,120);});
short.addEventListener('change',run);
document.addEventListener('keydown',function(e){if(e.key==='/'&&document.activeElement!==q){e.preventDefault();q.focus();}});
run();
})();
"""

PH = re.compile(r'\{\{\s*([^{}]*?)\s*\}\}')


def lang_of(locale):
    return locale.split('_')[0]


def cell(cls, lang, s):
    """Riot's {{name}} placeholders (filled in by the client) become a small chip showing \u2039name\u203a."""
    return '<span class="%s" lang="%s">%s</span>' % (cls, lang, PH.sub(r'<span class="ph">\1</span>', html.escape(s)))


def build_page(sections, see, read, also, ui):
    S = STRINGS[ui]
    lang_names = LANGS[ui]
    titles = TITLES[ui]
    sections = sorted(sections, key=lambda s: (ORDER.index(s[0]) if s[0] in ORDER else len(ORDER), s[0]))
    total = sum(len(r) for _, r in sections)
    two = not also
    nav = ''.join('<li><a href="#%s" title="%s"><span class="t">%s</span> <span class="n" data-n="%s">%s</span></a></li>'
                  % (p, p, html.escape(titles.get(p, p)), p, '{:,}'.format(len(r)).replace(',', '\u00a0')) for p, r in sections)
    body = []
    for p, rows in sections:
        cls = 'r two' if two else 'r'
        items = ''.join('<div class="%s">%s%s%s</div>' % (cls, cell('s', lang_of(see), a), cell('d', lang_of(read), b),
                                                          '' if two else cell('a', lang_of(also), c)) for a, b, c in rows)
        body.append('<section id="%s"><h2 title="%s">%s <span class="c">%s</span></h2>%s</section>'
                    % (p, p, html.escape(titles.get(p, p)), '{:,}'.format(len(rows)).replace(',', '\u00a0'), items))
    name = lambda loc: lang_names.get(lang_of(loc), loc)
    heads = '<span>%s</span><span>%s</span>%s' % (html.escape(S['in_client']), html.escape(name(read)),
                                                 '' if two else '<span>%s</span>' % html.escape(name(also)))
    js = JS.replace('__UI__', json.dumps({'found': S['found'], 'all': S['all']}, ensure_ascii=False))
    page = """<!doctype html>
<html lang="%(ui)s">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<style>%(css)s</style>
</head>
<body>
<header>
<h1>%(title)s</h1>
<p class="help">%(help)s</p>
</header>
<div class="bar"><div>
<input id="q" type="search" placeholder="%(placeholder)s" aria-label="%(search)s" autocomplete="off">
<label class="chk"><input id="short" type="checkbox"> %(short)s</label>
<span id="stat" aria-live="polite">%(count)s</span>
</div></div>
<div class="shell">
<nav aria-label="%(navlabel)s"><ul>%(nav)s</ul></nav>
<main>
<div class="heads%(twocls)s" aria-hidden="true">%(heads)s</div>
<p id="none" hidden>%(none)s</p>
%(body)s
</main>
</div>
<script>%(js)s</script>
</body>
</html>
""" % dict(ui=ui, title=html.escape(S['title']), css=CSS, help=html.escape(S['help']), placeholder=html.escape(S['placeholder']),
           search=html.escape(S['search']), short=html.escape(S['short']), count=html.escape(S['all'].replace('{n}', '{:,}'.format(total).replace(',', '\u00a0'))),
           navlabel=html.escape(S['nav']), nav=nav, twocls=' two' if two else '', heads=heads, none=html.escape(S['none']),
           body=''.join(body), js=js)
    return page, total


# ---------------------------------------------------------------------------------------------------------------- CLI
def norm_locale(s):
    s = (s or '').strip().lower().replace('-', '_')
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description='Searchable multi-language glossary of the League of Legends client UI.')
    ap.add_argument('--lol', help='folder that holds Plugins (auto-detected on macOS and Windows)')
    ap.add_argument('--see', default='ko_kr', help='locale of the client you look at (default ko_kr)')
    ap.add_argument('--read', default='cs_cz', help='locale you read (default cs_cz)')
    ap.add_argument('--also', default='en_us', help='optional third locale, "" for none (default en_us)')
    ap.add_argument('--ui', choices=sorted(STRINGS), help='language of the page itself (default: cs when --read is cs_cz, else en)')
    ap.add_argument('-o', '--output', default='lol-client-glossary.html')
    ap.add_argument('--list-locales', action='store_true', help='print the locales your client has translation tables for')
    ap.add_argument('--version', action='version', version=__version__)
    a = ap.parse_args(argv)

    lol = find_lol(a.lol)
    plugins = os.path.join(lol, 'Plugins')
    if a.list_locales:
        wads = plugin_wads(plugins)
        l10n = wads.get('rcp-fe-lol-l10n')
        if not l10n:
            raise SystemExit('rcp-fe-lol-l10n not found in %s' % plugins)
        wad = Wad(l10n)
        print(' '.join(loc for loc in KNOWN_LOCALES if wad.entries.get(trans_hash('rcp-fe-lol-l10n', loc))))
        return 0
    see, read, also = norm_locale(a.see), norm_locale(a.read), norm_locale(a.also)
    ui = a.ui or ('cs' if read.startswith('cs') else 'en')
    sections = collect(plugins, see, read, also)
    if not sections:
        raise SystemExit('No translation tables for %s and %s found in %s (try --list-locales).' % (see, read, plugins))
    page, total = build_page(sections, see, read, also, ui)
    out = os.path.abspath(a.output)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(page)
    print('wrote %s: %d screens, %d texts, %.1f MB (%s)' % (out, len(sections), total, len(page.encode('utf-8')) / 1e6, time.strftime('%Y-%m-%d')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
