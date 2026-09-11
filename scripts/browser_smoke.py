#!/usr/bin/env python3
"""Optional real-browser QA using an in-memory HTML document.

It does not rely on localhost or file://, so it also catches the exact runtime
errors that previously hid behind blocked local navigation.
"""
from pathlib import Path
import shutil, sys
ROOT=Path(__file__).resolve().parents[1]
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except Exception:
    print('BROWSER SMOKE: SKIP (playwright not installed)');raise SystemExit(0)

import os
exe=shutil.which('chromium') or shutil.which('google-chrome') or shutil.which('google-chrome-stable')
require=os.environ.get('FOH_REQUIRE_BROWSER_QA')=='1'
html=(ROOT/'dist/index.html').read_text(encoding='utf-8')
bundle=(ROOT/'dist/data/offline-data.js').read_text(encoding='utf-8')
html=html.replace('<script src="data/offline-data.js"></script>',f'<script>{bundle}</script>')
checks=[];errors=[]
with sync_playwright() as pw:
    try:
        browser=pw.chromium.launch(headless=True,executable_path=exe if exe else None,args=['--no-sandbox','--disable-gpu'])
    except Exception as e:
        if require:
            print(f'BROWSER SMOKE: FAIL (browser unavailable: {e})',file=sys.stderr);raise SystemExit(1)
        print(f'BROWSER SMOKE: SKIP (browser unavailable: {e})');raise SystemExit(0)
    page=browser.new_page(viewport={'width':1600,'height':1000})
    page.route('**/*',lambda route: route.abort() if route.request.url.startswith('http') else route.continue_())
    page.on('pageerror',lambda e:errors.append(str(e)))
    try:page.set_content(html,wait_until='domcontentloaded',timeout=8000)
    except PlaywrightTimeoutError:pass
    page.wait_for_timeout(200)
    checks.append(('scenario loads','players' in page.locator('#sideMeta').inner_text()))
    # Roster / cap render.
    page.locator('[data-nav="roster"]').first.click();page.wait_for_timeout(20);checks.append(('roster renders',page.locator('table').count()>0))
    page.locator('[data-nav="cap"]').first.click();page.wait_for_timeout(20);checks.append(('cap renders',page.get_by_text('Salary cap',exact=True).count()>0))
    # Completed player-for-player trade with fixture data.
    page.locator('[data-nav="trade"]').first.click();page.wait_for_timeout(50)
    checks.append(('trade banks render',page.locator('[data-out-player]').count()>0 and page.locator('[data-in-player-key]').count()>0))
    if page.locator('.asset-row').filter(has_text='DeShone Kizer').count() and page.locator('.asset-row').filter(has_text='Carson Palmer').count():
        page.locator('.asset-row').filter(has_text='DeShone Kizer').first.locator('button').click();page.wait_for_timeout(10)
        page.locator('.asset-row').filter(has_text='Carson Palmer').first.locator('button').click();page.wait_for_timeout(15)
        checks.append(('trade proposal mutates',page.locator('.trade-item').count()>=2))
        page.locator('#submitTrade').click();page.wait_for_timeout(30)
        page.locator('[data-nav="roster"]').first.click();page.wait_for_timeout(20)
        checks.append(('trade updates roster',page.get_by_text('Carson Palmer',exact=True).count()==1 and page.get_by_text('DeShone Kizer',exact=True).count()==0))
    # Reset to clean scenario for FA/draft.
    page.locator('#resetBtn').click();page.wait_for_timeout(40)
    page.locator('[data-nav="freeagency"]').first.click();page.wait_for_timeout(20)
    checks.append(('free agency renders',page.locator('[data-sign-fa]').count()>0))
    if page.locator('[data-sign-fa]').count():
        page.locator('[data-sign-fa]').first.click();page.wait_for_timeout(30)
        page.locator('[data-nav="roster"]').first.click();page.wait_for_timeout(20)
        checks.append(('signing updates roster',page.get_by_text('Kirk Cousins',exact=True).count()==1))
    page.locator('[data-nav="draft"]').first.click();page.wait_for_timeout(20)
    checks.append(('draft starts at pick 1','#1' in page.locator('.draft-pick').inner_text()))
    if page.locator('[data-draft]').count():page.locator('[data-draft]').first.click();page.wait_for_timeout(30)
    page.locator('[data-nav="timeline"]').first.click();page.wait_for_timeout(20)
    timeline=page.locator('.timeline').inner_text()
    checks.append(('draft updates timeline','Drafted Baker Mayfield' in timeline))
    checks.append(('FA updates timeline','Signed Kirk Cousins' in timeline))
    # Visible Roster-section regression for the multi-starter 2025+ schema.
    page.select_option('#yearSelect','2026');page.wait_for_timeout(20)
    page.select_option('#teamSelect','Dallas Cowboys');page.wait_for_timeout(80)
    page.locator('[data-nav="roster"]').first.click();page.wait_for_timeout(30)
    def visible_rank(name):
        row=page.locator('tr').filter(has_text=name).first
        return row.locator('.roster-rank').inner_text() if row.count() else ''
    checks.append(('Dallas Dak QB1',visible_rank('Dak Prescott')=='1'))
    checks.append(('Dallas CeeDee WR1',visible_rank('CeeDee Lamb')=='1'))
    checks.append(('Dallas Pickens WR2',visible_rank('George Pickens')=='2'))
    checks.append(('Dallas Ferguson TE1',visible_rank('Jake Ferguson')=='1'))
    # Every primary section must render without a runtime exception.
    for nav in ('overview','roster','cap','trade','freeagency','draft','coaches','timeline','sources'):
        page.locator(f'[data-nav="{nav}"]').first.click();page.wait_for_timeout(10)
        checks.append((f'nav {nav}',page.locator('#root').inner_text().strip()!=''))
    browser.close()
failed=[name for name,ok in checks if not ok]
print('BROWSER SMOKE:',', '.join(f'{name}={"PASS" if ok else "FAIL"}' for name,ok in checks))
if errors:print('PAGE ERRORS:',errors,file=sys.stderr)
if failed or errors:raise SystemExit(1)
