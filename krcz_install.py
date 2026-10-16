"""Make Riot Client install a locale and wait for the download.

    python3 -I krcz_install.py ko_KR [--dry-run]

Riot replaces the files of the previously installed locale with the new one (about 3.5 GB). The yaml is backed up in this
folder first. Quit Riot Client and LoL before you run it. If Riot Client waits for a click (Update/Play) a notification
says so. `krcz_refresh.py` uses this for the complete setup, you rarely need it directly.
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
C = R.C


def main():
    if len(sys.argv) < 2 or not C.LOCALE_RE.fullmatch(sys.argv[1]):
        sys.exit(__doc__)
    loc, dry = sys.argv[1], '--dry-run' in sys.argv
    problems = []
    if R.anything_running():
        problems.append('Riot Client / LoL is running - quit it first')
    if loc not in C.yaml_available():
        problems.append('%s is not offered for your region (available_locales)' % loc)
    if R.free_gb() < C.CFG['min_free_gb']:
        problems.append('only %.1f GB free, need %.1f GB' % (R.free_gb(), C.CFG['min_free_gb']))
    R.say('installed locale %s, requested %s, %.1f GB free' % (C.yaml_locale(), loc, R.free_gb()))
    if problems:
        for p in problems:
            R.say('! ' + p)
        sys.exit(0 if dry else 1)
    if dry:
        R.say('dry run OK: would install %s' % loc)
        return
    open(LOCK, 'w').write(str(os.getpid()))     # the watcher leaves the files alone while this exists
    try:
        R.install_locale(loc)
        R.notify('Locale %s is installed' % loc)
    finally:
        if os.path.exists(LOCK):
            os.remove(LOCK)


if __name__ == '__main__':
    main()
