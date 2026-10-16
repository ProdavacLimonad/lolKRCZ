"""Tests build a fake League install in a temp folder and run the real code against it. The swap uses APFS clonefile,
so they only run on macOS."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
SCRIPTS = ['krcz_config.py', 'krcz.py', 'krcz_riot.py']

PRODUCT_YAML = """auto_patching_enabled_by_player: false
locale_data:
    available_locales:
    - "cs_CZ"
    - "de_DE"
    - "ko_KR"
    default_locale: "en_GB"
patching_policy: "manual"
settings:
    create_shortcut: true
    locale: "ko_KR"
"""
CLIENT_YAML = """    globals:
        locale: "cs_CZ"
        region: "EUNE"
    patcher:
        locales:
        - "cs_CZ"
        - "de_DE"
"""


def write(path, data, mtime=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    if mtime:
        os.utime(path, ns=(mtime, mtime))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Env:
    """A temp copy of the scripts plus a fake install; `k` is the krcz module loaded from the copy."""

    def __init__(self, config=None, load_krcz=True):
        self.tmp = tempfile.mkdtemp()
        self.code = os.path.join(self.tmp, 'code')
        os.makedirs(self.code)
        for s in SCRIPTS:
            shutil.copy(os.path.join(ROOT, s), self.code)
        self.app = os.path.join(self.tmp, 'League of Legends.app')
        self.lol = os.path.join(self.app, 'Contents', 'LoL') + '/'
        self.final = self.lol + 'Game/DATA/FINAL/'
        self.meta = os.path.join(self.tmp, 'meta')
        cfg = {'lol_app': self.app, 'riot_metadata': self.meta}
        cfg.update(config or {})
        write(os.path.join(self.code, 'config.json'), json.dumps(cfg).encode())
        t = 1_700_000_000_000_000_000
        write(self.final + 'Localized/Global.ko_KR.wad.client', b'korean global' * 10, t + 1)
        write(self.final + 'UI.ko_KR.wad.client', b'korean ui' * 7, t + 2)
        write(self.final + 'Localized/Global.cs_CZ.wad.client', b'czech global text' * 13, t + 3)
        write(self.final + 'UI.cs_CZ.wad.client', b'czech ui' * 5, t + 4)
        write(self.lol + 'Game.manifest', b'manifest-1')
        write(self.lol + 'Config/LeagueClientSettings.yaml', CLIENT_YAML.encode())
        write(os.path.join(self.meta, 'league_of_legends.live', 'league_of_legends.live.product_settings.yaml'),
              PRODUCT_YAML.encode())
        self.k = None
        if load_krcz:
            self.k = load(os.path.join(self.code, 'krcz.py'), 'krcz_under_test')
            self.k.game_running = lambda: False       # a real LoL on this machine must not matter

    def read(self, rel):
        with open(self.final + rel, 'rb') as f:
            return f.read()

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


@unittest.skipUnless(sys.platform == 'darwin', 'the swap needs APFS clonefile (macOS)')
class SwapTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.addCleanup(self.env.close)
        self.k = self.env.k

    def prepared(self):
        self.k.stash_text()
        self.k.snapshot()

    def test_full_cycle_restores_exact_size_and_mtime(self):
        before = {r: self.k.sig(self.env.final + r) for r in self.k.C.text_wads('ko_KR')}
        self.prepared()
        self.assertEqual(self.k.classify(), {'swapped': 0, 'original': 2, 'other': 0})
        self.k.on()
        self.assertEqual(self.k.classify(), {'swapped': 2, 'original': 0, 'other': 0})
        self.assertEqual(self.env.read('UI.ko_KR.wad.client'), b'czech ui' * 5)
        self.assertEqual(self.env.read('Localized/Global.ko_KR.wad.client'), b'czech global text' * 13)
        self.k.off()
        self.assertEqual(self.k.classify(), {'swapped': 0, 'original': 2, 'other': 0})
        self.assertEqual(self.env.read('UI.ko_KR.wad.client'), b'korean ui' * 7)
        after = {r: self.k.sig(self.env.final + r) for r in self.k.C.text_wads('ko_KR')}
        self.assertEqual(before, after)                            # Riot sees exactly the files it installed

    def test_text_locale_files_are_never_touched(self):
        self.prepared()
        self.k.on()
        self.k.off()
        self.assertEqual(self.env.read('UI.cs_CZ.wad.client'), b'czech ui' * 5)
        self.assertEqual(self.env.read('Localized/Global.cs_CZ.wad.client'), b'czech global text' * 13)

    def test_patch_makes_on_refuse_and_off_a_noop(self):
        self.prepared()
        self.assertFalse(self.k.is_stale())
        write(self.env.lol + 'Game.manifest', b'manifest-2')       # LoL patched
        self.assertTrue(self.k.is_stale())
        with self.assertRaises(SystemExit):
            self.k.on()
        live = self.k.sig(self.env.final + 'UI.ko_KR.wad.client')
        self.k.off()                                               # must not put the old originals over new files
        self.assertEqual(self.k.sig(self.env.final + 'UI.ko_KR.wad.client'), live)

    def test_snapshot_needs_the_host_locale_installed(self):
        self.k.stash_text()
        yaml = os.path.join(self.env.meta, 'league_of_legends.live', 'league_of_legends.live.product_settings.yaml')
        write(yaml, PRODUCT_YAML.replace('locale: "ko_KR"', 'locale: "cs_CZ"').encode())
        with self.assertRaises(SystemExit):
            self.k.snapshot()

    def test_snapshot_refuses_when_already_swapped(self):
        self.prepared()
        self.k.on()
        with self.assertRaises(SystemExit):
            self.k.snapshot()

    def test_missing_stash_is_explained(self):
        with self.assertRaises(SystemExit) as cm:
            self.k.classify()
        self.assertIn('stash-text', str(cm.exception))

    def test_stash_text_needs_the_text_locale_installed(self):
        os.remove(self.env.final + 'UI.cs_CZ.wad.client')
        with self.assertRaises(SystemExit):
            self.k.stash_text()


class RiotSettingsTests(unittest.TestCase):
    def setUp(self):
        self.env = Env(load_krcz=False)
        self.addCleanup(self.env.close)
        self.r = load(os.path.join(self.env.code, 'krcz_riot.py'), 'krcz_riot_under_test')
        self.c = self.r.C

    def test_yaml_helpers(self):
        self.assertEqual(self.c.yaml_locale(), 'ko_KR')
        self.assertEqual(self.c.yaml_available(), ['cs_CZ', 'de_DE', 'ko_KR'])

    def test_client_locale_is_pinned_without_touching_the_patcher_list(self):
        self.r.set_client_locale('ko_KR')
        path = self.c.CLIENT_SETTINGS
        with open(path) as f:
            text = f.read()
        self.assertIn('        locale: "ko_KR"', text)
        self.assertIn('        - "cs_CZ"', text)                    # patcher.locales entry stays
        self.assertTrue(os.path.exists(path + '.bak-krcz'))
        with open(path + '.bak-krcz') as f:
            self.assertIn('locale: "cs_CZ"', f.read())

    def test_product_locale_switch(self):
        self.r.set_product_locale('cs_CZ')
        self.assertEqual(self.c.yaml_locale(), 'cs_CZ')
        self.assertEqual(self.c.yaml_available(), ['cs_CZ', 'de_DE', 'ko_KR'])   # the list is not rewritten


class ConfigTests(unittest.TestCase):
    def test_host_and_text_must_differ(self):
        env = Env({'host_locale': 'cs_CZ', 'text_locale': 'cs_CZ'}, load_krcz=False)
        self.addCleanup(env.close)
        with self.assertRaises(SystemExit):
            load(os.path.join(env.code, 'krcz_config.py'), 'cfg_same')

    def test_unknown_key_and_bad_locale_are_rejected(self):
        for bad in ({'text_local': 'cs_CZ'}, {'host_locale': 'korean'}):
            env = Env(bad, load_krcz=False)
            self.addCleanup(env.close)
            with self.assertRaises(SystemExit):
                load(os.path.join(env.code, 'krcz_config.py'), 'cfg_bad')


if __name__ == '__main__':
    unittest.main()
