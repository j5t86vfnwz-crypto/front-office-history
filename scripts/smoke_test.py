#!/usr/bin/env python3
from pathlib import Path
import re, shutil, subprocess, sys, tempfile
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'dist/index.html').read_text(encoding='utf-8')
errors=[]
for needle in ['data/offline-data.js','loadBundledScenario','loadBundledTradeTarget','Trade center','Free agency','League draft order','Roster']:
    if needle not in html:errors.append(f'missing {needle}')
if 'window.FOH_OFFLINE_BUNDLE' not in (ROOT/'dist/data/offline-data.js').read_text(encoding='utf-8'):
    errors.append('offline data JS is invalid')
# Syntax-check every inline app script (external script tag is skipped).
scripts=re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',html,re.S)
node=shutil.which('node')
if node:
    for i,script in enumerate(scripts):
        if not script.strip():continue
        p=ROOT/'dist'/f'.smoke-{i}.js';p.write_text(script,encoding='utf-8')
        r=subprocess.run([node,'--check',str(p)],capture_output=True,text=True)
        p.unlink(missing_ok=True)
        if r.returncode:errors.append(f'inline JS {i}: {r.stderr.strip()}')
# Chromium is optional locally but present in GitHub runner only if installed separately; do not make build depend on it.
if errors:
    print('\n'.join('ERROR '+e for e in errors),file=sys.stderr);raise SystemExit(1)
print(f'SMOKE: PASS ({len(scripts)} inline script block(s), offline bundle linked)')
