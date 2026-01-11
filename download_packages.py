import os
import json
import tarfile
import zipfile
from pathlib import Path
from urllib.parse import quote
import requests
from tqdm import tqdm

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


# ==============================
# Helper: download file
# ==============================

def download_file(url: str, dest_path: Path):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading: {url}")

    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            with open(dest_path, "wb") as f, tqdm(
                total=total, unit="B", unit_scale=True, desc=dest_path.name
            ) as bar:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        bar.update(len(chunk))
    except Exception as e:
        print(f"Failed: {e}")


# ==============================
# Helper: extract archives
# ==============================

def extract_archive(archive: Path, output_dir: Path):
    print(f"Extracting → {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        if archive.suffix in [".zip"]:
            with zipfile.ZipFile(archive, "r") as z:
                z.extractall(output_dir)
        else:
            with tarfile.open(archive, "r:*") as t:
                t.extractall(output_dir)
    except Exception as e:
        print(f"Extraction failed: {e}")


# =================================
# 1. Download PyPI packages
# =================================
def download_pypi(pkg):
    print(f"\n[PyPI] {pkg}")
    pkg_dir = DATA_DIR / "pypi" / pkg
    if pkg_dir.exists():
        print("Already exists — skipping.")
        return

    # Get metadata
    meta_url = f"https://pypi.org/pypi/{pkg}/json"
    r = requests.get(meta_url, timeout=30)
    if r.status_code != 200:
        print("Failed to fetch metadata.")
        return

    data = r.json()
    releases = data.get("releases", {})
    versions = sorted(releases.keys(), reverse=True)

    tarball = None
    for v in versions:
        for f in releases[v]:
            if f["packagetype"] == "sdist":
                tarball = f["url"]
                break
        if tarball:
            break

    if not tarball:
        print("No source distribution found.")
        return

    archive = DATA_DIR / "pypi" / f"{pkg}.tar.gz"
    download_file(tarball, archive)
    extract_archive(archive, pkg_dir)


# =================================
# 2. Download npm packages
# =================================
def download_npm(pkg):
    print(f"\n[npm] {pkg}")
    pkg_dir = DATA_DIR / "npm" / pkg.replace("/", "__")
    if pkg_dir.exists():
        print("Already exists — skipping.")
        return

    encoded = quote(pkg, safe="@/")
    meta_url = f"https://registry.npmjs.org/{encoded}/latest"

    try:
        meta = requests.get(meta_url, timeout=30).json()
        tarball = meta["dist"]["tarball"]
    except:
        print("Failed to get npm metadata.")
        return

    archive = DATA_DIR / "npm" / f"{pkg.replace('/', '__')}.tgz"
    download_file(tarball, archive)
    extract_archive(archive, pkg_dir)


# =================================
# 3. C/C++ + High-Risk: GitHub repos
# =================================

CPP_GITHUB = {
    "openssl": "https://github.com/openssl/openssl",
    "curl": "https://github.com/curl/curl",
    "zlib": "https://github.com/madler/zlib",
    "ffmpeg": "https://github.com/FFmpeg/FFmpeg",
    "libpng": "https://github.com/glennrp/libpng",
    "opencv": "https://github.com/opencv/opencv"
}

HIGH_RISK_GITHUB = {
    "busybox": "https://github.com/mirror/busybox",
    "ffmpeg-gpl": "https://github.com/FFmpeg/FFmpeg",
    "samba": "https://github.com/samba-team/samba",
    "glibc": "https://github.com/bminor/glibc",
    "libav": "https://github.com/libav/libav",
    "spidermonkey": "https://github.com/mozilla/spidermonkey",
    "mozilla-central": "https://github.com/mozilla/gecko-dev"
}


def github_zip_url(repo_url: str):
    repo_url = repo_url.rstrip("/")
    return f"{repo_url}/archive/refs/heads/master.zip"


def download_github_repo(name, repo_url, ecosystem):
    print(f"\n[{ecosystem}] {name}")
    pkg_dir = DATA_DIR / ecosystem / name
    if pkg_dir.exists():
        print("Already exists — skipping.")
        return

    zip_url = github_zip_url(repo_url)
    archive = DATA_DIR / ecosystem / f"{name}.zip"
    download_file(zip_url, archive)
    extract_archive(archive, pkg_dir)


# =================================
# MAIN SCRIPT
# =================================

def main():
    config = json.loads(Path("oss_packages_medium.json").read_text())

    # PyPI
    for pkg in config["pypi"]:
        download_pypi(pkg)

    # npm
    for pkg in config["npm"]:
        download_npm(pkg)

    # C/C++
    for pkg in config["cpp"]:
        if pkg in CPP_GITHUB:
            download_github_repo(pkg, CPP_GITHUB[pkg], "cpp")
        else:
            print(f"Missing C++ repo mapping: {pkg}")

    # High-risk
    for category in ["gpl", "lgpl", "mpl"]:
        for pkg in config["high_risk_copyleft"][category]:
            if pkg in HIGH_RISK_GITHUB:
                download_github_repo(pkg, HIGH_RISK_GITHUB[pkg], "high_risk")
            else:
                print(f"Missing high-risk repo mapping: {pkg}")


if __name__ == "__main__":
    main()
