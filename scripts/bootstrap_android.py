"""Download isolated Android build tools into out/android-tools."""
from pathlib import Path
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]/'out/android-tools'
URLS = {
    'sdk': 'https://dl.google.com/android/repository/commandlinetools-win-15859902_latest.zip',
    'gradle': 'https://services.gradle.org/distributions/gradle-8.13-bin.zip',
    'jdk': 'https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.20.1%2B1/OpenJDK17U-jdk_x64_windows_hotspot_17.0.20.1_1.zip',
}

def download(item):
    name,url=item
    archive=ROOT/(name+'.zip')
    if not archive.exists():
        print('Downloading '+name,flush=True)
        temporary=archive.with_suffix('.part')
        with urllib.request.urlopen(url,timeout=60) as response, temporary.open('wb') as stream:
            while block:=response.read(1024*1024):stream.write(block)
        temporary.replace(archive)
    destination=ROOT/name
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        for member in zipped.namelist():
            assert (destination/member).resolve().is_relative_to(destination.resolve())
        zipped.extractall(destination)
    print('Ready '+name,flush=True)

if __name__=='__main__':
    ROOT.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(download,URLS.items()))
