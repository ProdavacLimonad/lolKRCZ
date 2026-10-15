import contextlib
import gzip
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import lol_glossary as g


def read_text(path):
    with open(path, encoding='utf-8') as f:     # closed right away: Windows cannot delete a temp dir with open files
        return f.read()


def build_wad(path, entries):
    """Write a minimal WAD v3. entries: [(path_hash, compression_type, stored_bytes, uncompressed_size)]"""
    entries = sorted(entries, key=lambda e: e[0])
    pos = g.HEADER + 4 + 32 * len(entries)
    toc, data = b'', b''
    for h, typ, blob, size in entries:
        toc += struct.pack('<QIIIBBHQ', h, pos + len(data), len(blob), size, typ, 0, 0, 0)
        data += blob
    with open(path, 'wb') as f:
        f.write(b'RW' + bytes([3, 4]) + bytes(256 + 8) + struct.pack('<I', len(entries)) + toc + data)


def trans_entry(plugin, locale, table, typ=0):
    """typ 0: raw, 1: gzip, 2: raw with a UTF-8 BOM (some of Riot's tables have one)"""
    raw = json.dumps(table, ensure_ascii=False).encode('utf-8')
    h = g.trans_hash(plugin, locale)
    if typ == 1:
        return (h, 1, gzip.compress(raw), len(raw))
    if typ == 2:
        raw = b'\xef\xbb\xbf' + raw
    return (h, 0, raw, len(raw))


def make_install(root, macos_layout=False):
    lol = os.path.join(root, 'Contents', 'LoL') if macos_layout else root
    nav = os.path.join(lol, 'Plugins', 'rcp-fe-lol-navigation')
    other = os.path.join(lol, 'Plugins', 'rcp-fe-lol-settings')
    l10n = os.path.join(lol, 'Plugins', 'rcp-fe-lol-l10n')
    for d in (nav, other, l10n):
        os.makedirs(d)
    build_wad(os.path.join(nav, 'assets.wad'), [
        trans_entry('rcp-fe-lol-navigation', 'ko_kr', {'a': '설정', 'b': '{{count}} 개', 'c': 'Lorem ipsum', 'd': '<b>&</b>'}, typ=2),
        trans_entry('rcp-fe-lol-navigation', 'cs_cz', {'a': 'Nastaven\xed', 'b': '{{count}} ks', 'c': 'Lorem ipsum', 'd': '<b>&</b>'}, typ=1),
        trans_entry('rcp-fe-lol-navigation', 'en_us', {'a': 'Settings', 'b': '{{count}} pcs', 'c': 'Lorem ipsum', 'd': '<b>&</b>'}),
    ])
    build_wad(os.path.join(other, 'assets.wad'), [trans_entry('rcp-fe-lol-settings', 'ko_kr', {'x': '확인'})])  # no cs_cz table
    build_wad(os.path.join(l10n, 'assets.wad'), [
        trans_entry('rcp-fe-lol-l10n', 'ko_kr', {'k': 'v'}), trans_entry('rcp-fe-lol-l10n', 'cs_cz', {'k': 'v'})])
    return lol


class HashTests(unittest.TestCase):
    def test_xxh64_reference_values(self):
        self.assertEqual(g.xxh64(b''), 0xEF46DB3751D8E999)
        self.assertEqual(g.xxh64(b'a'), 0xD24EC4F1A98C6E5B)

    def test_path_hash_matches_real_wad_entries(self):
        self.assertEqual(g.path_hash('ux/fonts'), 0x957ccb5182db61f8)
        self.assertEqual(g.path_hash('Assets/Sounds/Wwise/VO/ja_JP/characters/ahri/skins/base/ahri_base_vo_audio.wpk'),
                         0xdb23f963a5dce7b3)


class WadTests(unittest.TestCase):
    def test_raw_and_gzip_entries(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'a.wad')
            build_wad(p, [(5, 0, b'hello', 5), (9, 1, gzip.compress(b'world'), 5)])
            w = g.Wad(p)
            self.assertEqual(w.read(5), b'hello')
            self.assertEqual(w.read(9), b'world')
            self.assertIsNone(w.read(1))

    def test_rejects_other_files(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'x.wad')
            with open(p, 'wb') as f:
                f.write(b'not a wad' * 100)
            with self.assertRaises(ValueError):
                g.Wad(p)

    def test_zstd_entry_when_a_decoder_exists(self):
        payload = b'zstd payload ' * 50
        blob = None
        try:
            import zstandard
            blob = zstandard.ZstdCompressor().compress(payload)
        except ImportError:
            exe = shutil.which('zstd')
            if exe:
                blob = subprocess.run([exe, '-c'], input=payload, capture_output=True, check=True).stdout
        if blob is None:
            self.skipTest('no zstd encoder available')
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'z.wad')
            build_wad(p, [(7, 3, blob, len(payload))])
            self.assertEqual(g.Wad(p).read(7), payload)


class InstallTests(unittest.TestCase):
    def test_find_lol_windows_and_macos_layouts(self):
        with tempfile.TemporaryDirectory() as d:
            win = make_install(os.path.join(d, 'win'))
            self.assertEqual(g.find_lol(win), win)
        with tempfile.TemporaryDirectory() as d:
            mac = make_install(os.path.join(d, 'mac.app'), macos_layout=True)
            self.assertEqual(g.find_lol(os.path.join(d, 'mac.app')), mac)
        with self.assertRaises(SystemExit):
            g.find_lol(os.path.join(tempfile.gettempdir(), 'definitely-not-lol'))


class BuildTests(unittest.TestCase):
    def run_cli(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = g.main(list(args))
        return rc, buf.getvalue()

    def test_page_for_czech_reader(self):
        with tempfile.TemporaryDirectory() as d:
            lol = make_install(os.path.join(d, 'LoL'))
            out = os.path.join(d, 'out', 'g.html')
            rc, msg = self.run_cli('--lol', lol, '-o', out)
            self.assertEqual(rc, 0)
            page = read_text(out)
            self.assertIn('lang="cs"', page)
            self.assertIn('설정', page)
            self.assertIn('Nastaven\xed', page)
            self.assertIn('Settings', page)
            self.assertIn('Hlavn\xed lišta a navigace', page)
            self.assertNotIn('{{', page)
            self.assertIn('<span class="ph">count</span>', page)
            self.assertNotIn('Lorem', page)                       # developer filler is skipped
            self.assertIn('&lt;b&gt;&amp;&lt;/b&gt;', page)       # markup in strings is escaped
            self.assertNotIn('확인', page)                # plugin without a cs_cz table is skipped
            self.assertIn('2 screens, 4 texts', msg)              # keys a, b, d of one plugin plus the l10n one

    def test_english_page_and_two_columns(self):
        with tempfile.TemporaryDirectory() as d:
            lol = make_install(os.path.join(d, 'LoL'))
            out = os.path.join(d, 'g.html')
            self.run_cli('--lol', lol, '--ui', 'en', '--also', '', '-o', out)
            page = read_text(out)
            self.assertIn('lang="en"', page)
            self.assertIn('Main bar and navigation', page)
            self.assertIn('class="r two"', page)
            self.assertNotIn('Settings</span>', page)             # no third column

    def test_list_locales(self):
        with tempfile.TemporaryDirectory() as d:
            lol = make_install(os.path.join(d, 'LoL'))
            rc, out = self.run_cli('--lol', lol, '--list-locales')
            self.assertEqual(out.split(), ['cs_cz', 'ko_kr'])

    def test_missing_pair_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            lol = make_install(os.path.join(d, 'LoL'))
            with self.assertRaises(SystemExit):
                self.run_cli('--lol', lol, '--read', 'de_de', '-o', os.path.join(d, 'g.html'))


if __name__ == '__main__':
    unittest.main()
