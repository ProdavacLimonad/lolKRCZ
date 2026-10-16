"""Background watcher: swap the text in when the LoL client is up, put Riot's files back after LoL has quit.

Run it as a LaunchAgent (install_agent.py). It polls the process list every few seconds.
  LeagueClientUx appears            -> wait settle_seconds (Riot's own Play-time check is done by then) -> krcz.on()
  client and game gone for quit_seconds -> krcz.off()
At start-up, if no LoL is running but the swapped wads are still in place (crash, reboot), it runs off().
While krcz_refresh.py / krcz_install.py run (krcz.lock) it leaves the files alone. If LoL was patched it does not swap and
sends one notification. Log: krcz_watch.log next to this script. `python3 -I krcz_watch.py --status` shows what it sees.
"""
import importlib.util, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)) + '/'
LOCK = HERE + 'krcz.lock'
POLL = 2


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE + name + '.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


K = _load('krcz')
CFG = K.C.CFG
SETTLE, QUIT = CFG['settle_seconds'], CFG['quit_seconds']


def log(msg):
    path = HERE + 'krcz_watch.log'
    with open(path, 'a') as f:
        f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + msg + '\n')
    try:   # keep the log small
        if os.path.getsize(path) > 200_000:
            with open(path) as f:
                lines = f.read().splitlines()[-200:]
            with open(path, 'w') as f:
                f.write('\n'.join(lines) + '\n')
    except OSError:
        pass


def procs():
    out = subprocess.run(['/bin/ps', '-axo', 'comm'], capture_output=True, text=True).stdout.splitlines()
    ux = any(l.endswith('/Contents/MacOS/LeagueClientUx') for l in out)
    game = any(l.endswith('/LoL/Game/LeagueofLegends.app/Contents/MacOS/LeagueofLegends') for l in out)
    return ux, game


def notify(msg):
    subprocess.run(['/usr/bin/osascript', '-e', 'display notification "%s" with title "lolKRCZ"' % msg.replace('"', "'")], check=False)


def run(fn, name):
    try:
        fn()
        log(name + ' ok')
        return True
    except SystemExit as e:
        log('%s refused: %s' % (name, e))
    except Exception as e:   # keep the watcher alive
        log('%s failed: %r' % (name, e))
    return False


def main():
    ux, game = procs()
    if not (ux or game) and not os.path.exists(LOCK):
        try:
            c = K.classify()
        except SystemExit as e:
            c = {'swapped': 0}
            log('start-up check skipped: %s' % e)
        if c['swapped']:
            log('start-up: %d wads still swapped with no LoL running -> off' % c['swapped'])
            run(K.off, 'off')
    applied, up_since, gone_since, stale_notified = False, None, None, False
    log('watcher started (client=%s game=%s)' % (ux, game))
    while True:
        if os.path.exists(LOCK):   # a setup/refresh is working on the files
            applied, up_since, gone_since = False, None, None
            time.sleep(POLL)
            continue
        ux, game = procs()
        if ux or game:
            gone_since = None
            if up_since is None:
                up_since = time.time()
                log('LoL client detected')
            if not applied and ux and time.time() - up_since >= SETTLE:
                if os.path.exists(K.STATE) and K.is_stale():
                    if not stale_notified:
                        stale_notified = True
                        log('LoL was patched: the stash is outdated, not swapping. Run krcz_refresh.py')
                        notify('LoL was patched. Run krcz_refresh.py to rebuild the text swap.')
                    up_since = time.time() + 3600   # no retry in this session
                else:
                    applied = run(K.on, 'on')
                    if not applied:
                        up_since = time.time() + 30
        else:
            up_since, stale_notified = None, False
            if gone_since is None:
                gone_since = time.time()
            if applied and time.time() - gone_since >= QUIT:
                if run(K.off, 'off'):
                    applied = False
        time.sleep(POLL)


if __name__ == '__main__':
    if '--status' in sys.argv:
        print('client/game running:', procs(), ' wads:', K.classify())
    else:
        main()
