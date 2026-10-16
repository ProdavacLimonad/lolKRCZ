"""The complete setup of lolKRCZ, and the rebuild after a LoL patch.

    python3 -I krcz_refresh.py --dry-run   # checks only, changes nothing
    python3 -I krcz_refresh.py --force     # first setup (or rebuild any time)
    python3 -I krcz_refresh.py             # rebuild, only when LoL was patched since the last run

With host locale H (default ko_KR) and text locale T (default cs_CZ), about 7 GB of downloads, takes a few minutes:
  1. checks (Riot Client / LoL not running, disk, both locales offered), takes krcz.lock so the watcher leaves the files alone
  2. makes T the installed locale (skipped when it already is) and keeps its genuine text wads in text/
  3. makes H the installed locale again
  4. pins LeagueClientSettings.yaml to H, so every normal LoL start asks Riot for H instead of reinstalling the old locale
  5. takes the snapshot of H's own wads
Progress goes to the terminal and to krcz.log. If Riot Client waits for a click (Update/Play) you get a notification.
"""
import importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)) + '/'
LOCK = HERE + 'krcz.lock'


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE + name + '.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = _load('krcz_riot')
K = _load('krcz')
C = R.C
say = R.say


def main():
    dry, force = '--dry-run' in sys.argv, '--force' in sys.argv
    stale = K.is_stale() if os.path.exists(C.STATE) else True      # no snapshot yet counts as "needs a setup"
    say('host %s, text %s, installed %s, stale/new: %s' % (C.HOST, C.TEXT, C.yaml_locale(), stale))
    problems = []
    if R.anything_running():
        problems.append('Riot Client / LoL is running - quit it first')
    for loc in (C.HOST, C.TEXT):
        if loc not in C.yaml_available():
            problems.append('%s is not offered for your region (available_locales of %s)' % (loc, C.YAML))
    if R.free_gb() < C.CFG['min_free_gb']:
        problems.append('only %.1f GB free, need %.1f GB' % (R.free_gb(), C.CFG['min_free_gb']))
    if not stale and not force:
        problems.append('nothing to do: LoL was not patched since the last run (use --force to rebuild anyway)')
    say('free disk %.1f GB' % R.free_gb())
    if problems:
        for p in problems:
            say('! ' + p)
        sys.exit(0 if dry else 1)
    if dry:
        say('dry run OK: the setup would run now')
        return
    open(LOCK, 'w').write(str(os.getpid()))
    ok = False
    try:
        if C.yaml_locale() != C.TEXT:
            R.install_locale(C.TEXT)
        K.stash_text()
        R.install_locale(C.HOST)
        R.set_client_locale(C.HOST)
        K.snapshot()
        ok = True
        say('DONE: from now on the watcher (krcz_watch.py) swaps %s text in under the %s font while LoL runs' % (C.TEXT, C.HOST))
        R.notify('lolKRCZ is set up')
    except BaseException as e:
        say('FAILED: %r' % (e,))
        R.notify('lolKRCZ setup failed, see krcz.log')
        raise
    finally:
        if os.path.exists(LOCK):
            os.remove(LOCK)
        if not ok:
            say('Riot may have to re-download a locale on the next start; run this script again.')


if __name__ == '__main__':
    main()
