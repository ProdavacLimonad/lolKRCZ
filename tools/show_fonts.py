"""Print which font file League uses for every locale. Read only.

    python3 tools/show_fonts.py [--lol "/Applications/League of Legends.app/Contents/LoL"]

The game keeps its font assignment in `ux/fonts` (a Riot PROP file) inside UI.wad.client: every FontType has a default
font file plus per-locale overrides, so the font is chosen by the locale the game runs as. A locale without an override
gets the default (Beaufort/Spiegel). The ko_kr row is the Korean client's font. Needs `zstd` (pip install zstandard or the
command line tool) because the entry is compressed.
"""
import argparse, collections, importlib.util, os, shutil, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__)) + '/'
FONTS_ENTRY = 0x957ccb5182db61f8          # XXH64 of "ux/fonts"
CLS_FONT_TYPE, F_LOCALE_TYPES = 0x2db35d98, 0x8c9d92f4
F_LOCALE_NAME, F_FONT, F_FONT_BOLD = 0x1a9f4554, 0x8764b624, 0x10c450de


def load_propbin():
    spec = importlib.util.spec_from_file_location('propbin', HERE + 'propbin.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def unzstd(blob):
    try:
        import zstandard
        return zstandard.ZstdDecompressor().decompressobj().decompress(blob)
    except ImportError:
        pass
    exe = shutil.which('zstd') or '/opt/homebrew/bin/zstd'
    if not os.path.exists(exe):
        sys.exit('install a zstd decoder: pip install zstandard')
    return subprocess.run([exe, '-d', '-c'], input=blob, capture_output=True, check=True).stdout


def read_entry(wad, h):
    with open(wad, 'rb') as f:
        f.seek(268)
        n, = struct.unpack('<I', f.read(4))
        for _ in range(n):
            hh, off, csz, sz, typ, _d, _s, _sha = struct.unpack('<QIIIBBHQ', f.read(32))
            if hh == h:
                f.seek(off)
                blob = f.read(csz)
                return blob if typ == 0 else unzstd(blob)
    sys.exit('ux/fonts not found in %s (the game layout may have changed)' % wad)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--lol', default='/Applications/League of Legends.app/Contents/LoL')
    a = ap.parse_args()
    wad = os.path.join(a.lol, 'Game', 'DATA', 'FINAL', 'UI.wad.client')
    pb = load_propbin()
    ver, linked, entries = pb.parse(read_entry(wad, FONTS_ENTRY))
    by_locale = collections.defaultdict(set)
    types = 0
    for cls, _ph, fields in entries:
        if cls != CLS_FONT_TYPE:
            continue
        types += 1
        for nh, _t, v in fields:
            if nh != F_LOCALE_TYPES:
                continue
            for item in v[2]:
                d = {fh: fv for fh, _ft, fv in item[2]}
                name = d.get(F_LOCALE_NAME, 'default')
                for key in (F_FONT, F_FONT_BOLD):
                    if key in d:
                        by_locale[name].add(os.path.basename(d[key].replace('\\', '/')))
    print('%d font types; font files per locale (a locale that is not listed uses "default"):\n' % types)
    for loc in sorted(by_locale, key=lambda k: (k != 'default', k)):
        print('  %-8s %s' % (loc, ', '.join(sorted(by_locale[loc]))))


if __name__ == '__main__':
    main()
