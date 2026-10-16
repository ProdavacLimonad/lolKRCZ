"""Helpers that drive Riot Client: make it install a locale, wait for the download, quit it, pin the client locale."""
import glob, importlib.util, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)) + '/'


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE + name + '.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = _load('krcz_config')
FINAL, YAML, RIOT_APP, LOGDIR = C.FINAL, C.YAML, C.RIOT_APP, C.LOGDIR
PATCHLINE = C.CFG['patchline']
launch_t = 0.0


def say(msg):
    line = time.strftime('%H:%M:%S ') + msg
    print(line, flush=True)
    with open(HERE + 'krcz.log', 'a') as f:
        f.write(line + '\n')


def notify(msg):
    subprocess.run(['/usr/bin/osascript', '-e',
                    'display notification "%s" with title "lolKRCZ"' % msg.replace('"', "'")], check=False)


def anything_running():
    out = subprocess.run(['/bin/ps', '-axo', 'comm'], capture_output=True, text=True).stdout
    return bool(re.search(r'RiotClientServices|/Riot Client\.app/|LeagueClient|/LoL/Game/LeagueofLegends', out))


def free_gb():
    return shutil.disk_usage(FINAL).free / 1e9


def base_champions():
    return len([p for p in glob.glob(FINAL + 'Champions/*.wad.client')
                if re.fullmatch(r'[^.]+\.wad\.client', os.path.basename(p))])


def count_wads(loc):
    return len(glob.glob(FINAL + '**/*.%s.wad.client' % loc, recursive=True))


def count_champions(loc):
    return len(glob.glob(FINAL + 'Champions/*.%s.wad.client' % loc))


def _sub_locale(path, pattern, loc):
    with open(path) as f:
        text = f.read()
    new, n = re.subn(pattern, r'\1"%s"' % loc, text, count=1)
    if n != 1:
        raise RuntimeError('could not find the locale setting in ' + path)
    with open(path, 'w') as f:
        f.write(new)


def set_product_locale(loc):
    """Riot's product_settings.yaml: the locale Riot installs."""
    _sub_locale(YAML, r'(?m)^(    locale: )"%s"' % C.LOCALE_RE.pattern, loc)
    say('product_settings.yaml locale -> ' + loc)


def set_client_locale(loc):
    """LeagueClientSettings.yaml globals.locale. LeagueClient passes it to Riot Client as --locale at every start, so it
    must be the host locale; otherwise a normal launch makes Riot reinstall the old locale and delete the host one."""
    p = C.CLIENT_SETTINGS
    if not os.path.exists(p + '.bak-krcz'):
        shutil.copyfile(p, p + '.bak-krcz')
    _sub_locale(p, r'(?m)^(        locale: )"%s"' % C.LOCALE_RE.pattern, loc)
    say('LeagueClientSettings.yaml globals.locale -> %s (backup %s.bak-krcz)' % (loc, p))


def riot_status():
    logs = [p for p in glob.glob(LOGDIR + '*Riot Client.log') if os.path.getmtime(p) >= launch_t]
    if not logs:
        return None
    with open(max(logs, key=os.path.getmtime), errors='replace') as f:
        text = f.read()
    m = re.findall(r'productId: league_of_legends, patchlineId: %s, status: (\w+), progress: ([0-9.]+)' % re.escape(PATCHLINE), text)
    return m[-1] if m else None


def launch(loc):
    global launch_t
    launch_t = time.time() - 2
    subprocess.run(['/usr/bin/open', RIOT_APP, '--args', '--launch-product=league_of_legends',
                    '--launch-patchline=' + PATCHLINE, '--locale=' + loc], check=True)
    say('Riot Client started with locale ' + loc)


def wait_for(loc, other, timeout=3 * 3600):
    """Wait until every champion wad of `loc` is there, the `other` locale's wads are gone and Riot says UpToDate."""
    t0 = time.time()
    want = base_champions()
    ok_polls, last_print, hinted = 0, 0, False
    while time.time() - t0 < timeout:
        n, o, st = count_champions(loc), count_wads(other), riot_status()
        if time.time() - last_print > 30:
            say('%s: %d/%d champion wads, %d %s wads left, Riot status %s' % (loc, n, want, o, other, st))
            last_print = time.time()
        if not hinted and time.time() - t0 > 180 and n == 0 and (st is None or st[0] not in ('Updating', 'Repairing')):
            hinted = True
            say('Nothing is downloading: click Update/Play in the Riot Client window.')
            notify('Riot Client is waiting: click Update or Play')
        done = n >= want and o == 0 and st is not None and st[0] == 'UpToDate'
        ok_polls = ok_polls + 1 if done else 0
        if ok_polls >= 3:
            say('%s installed (%d champion wads)' % (loc, n))
            return
        time.sleep(5)
    raise TimeoutError('timed out waiting for ' + loc)


def quit_all():
    for app in ('League of Legends', 'Riot Client'):
        subprocess.run(['/usr/bin/osascript', '-e', 'tell application "%s" to quit' % app],
                       capture_output=True, timeout=30, check=False)
    deadline = time.time() + 30
    while time.time() < deadline and anything_running():
        time.sleep(2)
    if anything_running():
        subprocess.run(['/usr/bin/pkill', '-TERM', '-f', r'RiotClientServices|Riot Client|LeagueClient|LoL/Game/LeagueofLegends'], check=False)
        deadline = time.time() + 20
        while time.time() < deadline and anything_running():
            time.sleep(2)
    if anything_running():
        raise RuntimeError('could not quit Riot Client / LoL; quit them manually and run it again')
    say('Riot Client / LoL quit')


def install_locale(loc):
    """Make Riot install `loc` and wait for it. On failure the yaml locale is put back."""
    cur = C.yaml_locale()
    if cur == loc and count_champions(loc) >= base_champions():
        say('%s is already installed' % loc)
        return
    if loc not in C.yaml_available():
        raise RuntimeError('%s is not in available_locales of %s' % (loc, YAML))
    backup = HERE + 'product_settings.yaml.bak-' + time.strftime('%Y%m%d-%H%M%S')
    shutil.copyfile(YAML, backup)
    say('yaml backup: ' + backup)
    ok = False
    try:
        set_product_locale(loc)
        launch(loc)
        wait_for(loc, cur)
        quit_all()
        ok = True
        say('%s installed (%d locale wads)' % (loc, count_wads(loc)))
    finally:
        if not ok and cur:
            try:
                set_product_locale(cur)
            except Exception as e:
                say('could not restore locale %s: %r' % (cur, e))
