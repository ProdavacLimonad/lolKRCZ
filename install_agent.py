"""Write the LaunchAgent plist that runs krcz_watch.py at login (it does not load it).

    python3 -I install_agent.py [--label com.example.lolkrcz] [--show]      # --show only prints the plist

Default label: com.lolkrcz.watch. The plist goes to ~/Library/LaunchAgents/<label>.plist and uses this folder's
krcz_watch.py and the Python that runs this script. Then load it yourself:
    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/<label>.plist
    launchctl kickstart -k gui/$(id -u)/<label>      # restart after changing the scripts or config.json
    launchctl bootout gui/$(id -u)/<label>           # stop and unload
"""
import os, plistlib, sys

HERE = os.path.dirname(os.path.abspath(__file__)) + '/'
label = sys.argv[sys.argv.index('--label') + 1] if '--label' in sys.argv else 'com.lolkrcz.watch'
plist = {
    'Label': label,
    'ProgramArguments': [sys.executable, '-I', HERE + 'krcz_watch.py'],
    'RunAtLoad': True,
    'KeepAlive': True,
    'ProcessType': 'Background',
    'StandardErrorPath': HERE + 'krcz_watch.err',
}
if '--show' in sys.argv:
    print(plistlib.dumps(plist).decode())
    sys.exit(0)
path = os.path.expanduser('~/Library/LaunchAgents/%s.plist' % label)
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'wb') as f:
    plistlib.dump(plist, f)
print('wrote', path)
print('load it with:  launchctl bootstrap gui/$(id -u) "%s"' % path)
