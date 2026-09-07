"""Install the built APK, navigate real Compose screens, capture reviewable screenshots."""
import re, subprocess, time
from pathlib import Path
import xml.etree.ElementTree as ET

def adb(*args): return subprocess.check_output(['adb',*args], timeout=30)
def tap_text(text):
    for attempt in range(10):
        adb('shell','uiautomator','dump','/sdcard/window.xml')
        root=ET.fromstring(adb('exec-out','cat','/sdcard/window.xml'))
        for n in root.iter('node'):
            if n.get('text')==text:
                x1,y1,x2,y2=map(int,re.findall(r'\d+',n.attrib['bounds']))
                adb('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2)); time.sleep(3); return
        time.sleep(2)
    raise RuntimeError('UI text not found: '+text)
def screenshot(name):
    Path('dist').mkdir(exist_ok=True); Path('dist/'+name+'.png').write_bytes(adb('exec-out','screencap','-p'))
adb('install','-r','app/build/outputs/apk/debug/app-debug.apk')
adb('shell','am','start','-n','com.rui.astockstrategy.selection/com.rui.astockstrategy.v6.V6Activity')
time.sleep(12)
tap_text('组合'); time.sleep(8); screenshot('android-holdings')
tap_text('报表'); time.sleep(5); screenshot('android-daily-returns')
tap_text('累计收益率'); screenshot('android-cumulative-returns')
Path('dist/android-ui-smoke.txt').write_text('PASS: APK installed and portfolio/daily/cumulative screens navigated; screenshots saved.\n')
