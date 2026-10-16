"""Korean font and Czech text in League of Legends (macOS), using only genuine Riot files.

League picks the in-game font from the locale Riot has installed (host_locale, default ko_KR = the Korean client's
font) and reads its text from that locale's wads. This tool keeps the genuine Czech text wads of text_locale
(Localized/Global.cs_CZ, UI.cs_CZ) in `text/` and, only while LoL runs, swaps them in under the ko_KR names, so you play
with the Korean font and Czech text. Wads are signed by Riot, so nothing is edited: files are only cloned over each other.
Riot Client checks those files when it starts and on every Play click, so the swap is undone when LoL has quit.

    python3 -I krcz.py stash-text   # keep the genuine text wads (the text locale must be installed right now)
    python3 -I krcz.py snapshot     # keep the host locale's own wads (the host locale installed, Riot idle, clean state)
    python3 -I krcz.py on           # LoL client is up (menu showing): swap the text in
    python3 -I krcz.py off          # after you quit LoL and Riot Client: put Riot's own files back
    python3 -I krcz.py status

krcz_refresh.py does the whole setup and the rebuild after a LoL patch, krcz_watch.py does on/off by itself.
Files are swapped with APFS clonefile, which keeps size and mtime, so after `off` Riot sees exactly what it installed.
"""
import ctypes, hashlib, importlib.util, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__)) + '/'


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE + name + '.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = _load('krcz_config')
FINAL, ORIG, STATE, TEXTDIR, TEXT_STATE = C.FINAL, C.ORIG, C.STATE, C.TEXTDIR, C.TEXT_STATE
libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
libc.clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]


def manifest_sha():
    """Fingerprint of the installed LoL version (Riot rewrites Game.manifest on every patch)."""
    h = hashlib.sha256()
    with open(C.MANIFEST, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


def _json(path):
    with open(path) as f:
        return json.load(f)


def sig(p):
    st = os.stat(p)
    return [st.st_size, st.st_mtime_ns]


def is_stale():
    """True when LoL was patched after the snapshot or the text stash were made (they no longer match the game)."""
    cur = manifest_sha()
    for p in (STATE, TEXT_STATE):
        if os.path.exists(p) and _json(p).get('_manifest') != cur:
            return True
    return False


def pairs():
    """[(wad of the host locale, relative to FINAL, genuine wad of the text locale that is swapped in for it)]"""
    out = []
    for rel_src, rel_live in zip(C.text_wads(C.TEXT), C.text_wads(C.HOST)):
        if not os.path.exists(TEXTDIR + rel_src):
            sys.exit('text stash missing: %s. Run: python3 -I %skrcz.py stash-text' % (TEXTDIR + rel_src, HERE))
        out.append((rel_live, TEXTDIR + rel_src))
    return out


def clone_over(src, dst):
    tmp = dst + '.tmp-krcz'
    if os.path.exists(tmp):
        os.remove(tmp)
    if libc.clonefile(src.encode(), tmp.encode(), 0) != 0:
        sys.exit('clonefile failed (%s): %s -> %s' % (os.strerror(ctypes.get_errno()), src, tmp))
    os.replace(tmp, dst)


def game_running():
    return subprocess.run(['/usr/bin/pgrep', '-qf', '/LoL/Game/|LeagueClientUx'], check=False).returncode == 0


def classify():
    st = _json(STATE) if os.path.exists(STATE) else {}
    res = {'swapped': 0, 'original': 0, 'other': 0}
    for rel, src in pairs():
        cur = sig(FINAL + rel)
        if cur == sig(src):
            res['swapped'] += 1
        elif cur == st.get(rel):
            res['original'] += 1
        else:
            res['other'] += 1
    return res


def stash_text():
    """Keep the genuine text wads of text_locale. They must be installed now and LoL must not run."""
    if game_running():
        sys.exit('LoL client/game is running; quit it first.')
    os.makedirs(TEXTDIR, exist_ok=True)
    st = {}
    for rel in C.text_wads(C.TEXT):
        live = FINAL + rel
        if not os.path.exists(live):
            sys.exit('%s is not installed (Riot has %s installed). Install it first: python3 -I krcz_install.py %s'
                     % (C.TEXT, C.yaml_locale(), C.TEXT))
        dst = TEXTDIR + rel
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            os.remove(dst)
        if libc.clonefile(live.encode(), dst.encode(), 0) != 0:
            sys.exit('clonefile failed for ' + live)
        st[rel] = sig(live)
        assert sig(dst) == st[rel], 'clone changed size/mtime: ' + rel
    st['_locale'] = C.TEXT
    st['_manifest'] = manifest_sha()
    with open(TEXT_STATE, 'w') as f:
        json.dump(st, f)
    print('text stash for %s saved in %s' % (C.TEXT, TEXTDIR))


def snapshot():
    """Keep the host locale's own wads so `off` can put them back with the exact size and mtime Riot expects."""
    if C.yaml_locale() != C.HOST:
        sys.exit('Riot has %s installed, not %s. Run: python3 -I krcz_install.py %s' % (C.yaml_locale(), C.HOST, C.HOST))
    c = classify()
    if c['swapped']:
        sys.exit('%d live wads are already the swapped-in ones; run `off` (or let Riot repair) first.' % c['swapped'])
    st = {}
    os.makedirs(ORIG, exist_ok=True)
    for rel, _src in pairs():
        dst = ORIG + rel
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            os.remove(dst)
        if libc.clonefile((FINAL + rel).encode(), dst.encode(), 0) != 0:
            sys.exit('clonefile failed for ' + rel)
        st[rel] = sig(FINAL + rel)
        assert sig(dst) == st[rel], 'clone changed size/mtime: ' + rel
    st['_manifest'] = manifest_sha()
    st['_host_locale'] = C.HOST
    with open(STATE, 'w') as f:
        json.dump(st, f)
    print('snapshot of the %s wads saved in %s' % (C.HOST, ORIG))


def on():
    if not os.path.exists(STATE):
        sys.exit('no snapshot yet: run `snapshot` first.')
    if is_stale():
        sys.exit('LoL was patched since the snapshot/stash (Game.manifest changed). Run: python3 -I %skrcz_refresh.py' % HERE)
    for rel, src in pairs():
        clone_over(src, FINAL + rel)
    print('%s text on (%s font).' % (C.TEXT, C.HOST))


def off():
    if not os.path.exists(STATE):
        sys.exit('no snapshot: cannot restore.')
    if game_running():
        sys.exit('LoL client/game is running; quit it first.')
    if is_stale():
        print('LoL was patched since the snapshot: the live wads are new originals, nothing to restore.')
        return
    st = _json(STATE)
    for rel, _src in pairs():
        clone_over(ORIG + rel, FINAL + rel)
        if sig(FINAL + rel) != st[rel]:
            sys.exit('restored file does not match the snapshot (size/mtime): ' + rel)
    print('Riot\'s own %s wads restored, safe to start Riot Client.' % C.HOST)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if cmd == 'stash-text':
        stash_text()
    elif cmd == 'snapshot':
        snapshot()
    elif cmd == 'on':
        on()
    elif cmd == 'off':
        off()
    elif cmd == 'status':
        print(classify())
    else:
        sys.exit(__doc__)
