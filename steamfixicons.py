"""Recover missing Steam desktop icons without creating duplicates.

This script scans installed Steam apps across all configured Steam libraries and
creates Windows .lnk shortcuts on the user's Desktop that launch the game via
Steam (steam.exe -applaunch <appid>).

Design goals:
- Correct launching: use numeric appid (not the game name).
- No duplicates: detect existing shortcuts by appid, not fuzzy filename match.
- Robust paths: resolve Steam install path from the registry and Desktop path
  via Windows Known Folders.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


def _preflight_or_exit() -> None:
    """Fail fast with a helpful message if Windows-only deps are missing."""

    try:
        import win32com.client  # noqa: F401
    except ModuleNotFoundError:
        print(
            "Missing dependency: pywin32 (win32com).\n\n"
            "Fix:\n"
            "  1) Activate your venv\n"
            "  2) Run:  pip install -r requirements.txt\n\n"
            "If pip errors, try:  python -m pip install --upgrade pip\n",
            file=sys.stderr,
        )
        raise SystemExit(2)


@dataclass(frozen=True)
class SteamApp:
    appid: int
    name: str
    install_dir_name: str
    library_steamapps: Path

    @property
    def install_path(self) -> Path:
        return self.library_steamapps / "common" / self.install_dir_name


def _read_text_best_effort(path: Path) -> str:
    # ACF/VDF files are typically UTF-8, but can contain odd bytes.
    return path.read_text(encoding="utf-8", errors="replace")


def _get_steam_install_path_from_registry() -> Optional[Path]:
    """Return Steam install path if present (works for default & custom installs)."""

    try:
        import winreg
    except Exception:
        return None

    reg_paths = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam"),
    ]
    for hive, subkey in reg_paths:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                value, _ = winreg.QueryValueEx(key, "SteamPath")
                if value:
                    p = Path(str(value)).expanduser()
                    if (p / "steam.exe").exists():
                        return p
        except FileNotFoundError:
            continue
        except OSError:
            continue

    return None


def _get_desktop_path() -> Path:
    """Resolve Desktop via Known Folders (handles OneDrive redirection)."""

    # FOLDERID_Desktop: {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
    folderid_desktop = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_uint32),
            ("Data2", ctypes.c_uint16),
            ("Data3", ctypes.c_uint16),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    def _guid_from_string(guid_str: str) -> GUID:
        ole32 = ctypes.windll.ole32
        iid = GUID()
        if ole32.IIDFromString(ctypes.c_wchar_p(guid_str), ctypes.byref(iid)) != 0:
            raise OSError("IIDFromString failed")
        return iid

    try:
        shell32 = ctypes.windll.shell32
        desktop_guid = _guid_from_string(folderid_desktop)
        ppath = ctypes.c_wchar_p()
        # SHGetKnownFolderPath(FOLDERID, flags, token, outPath)
        if shell32.SHGetKnownFolderPath(ctypes.byref(desktop_guid), 0, 0, ctypes.byref(ppath)) != 0:
            raise OSError("SHGetKnownFolderPath failed")
        try:
            if not ppath.value:
                raise OSError("SHGetKnownFolderPath returned empty path")
            desktop = Path(ppath.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(ppath)
        if desktop.exists():
            return desktop
    except Exception:
        pass

    # Fallback: typical profile Desktop
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        return Path(userprofile) / "Desktop"
    return Path.cwd()


def _libraryfolders_vdf_path(steam_install_path: Path) -> Path:
    return steam_install_path / "steamapps" / "libraryfolders.vdf"


def _parse_libraryfolders_paths(vdf_text: str) -> list[Path]:
    """Extract library root paths from libraryfolders.vdf.

    Steam uses a key/value VDF format. We do a tolerant regex parse for lines like:
      "path"    "D:\\SteamLibrary"
    """

    paths: list[Path] = []
    for match in re.finditer(r'"path"\s+"(?P<path>[^"]+)"', vdf_text, flags=re.IGNORECASE):
        raw = match.group("path")
        raw = raw.replace("\\\\", "\\")
        p = Path(raw)
        if p.exists():
            paths.append(p)
    return paths


def get_steam_library_steamapps_paths(steam_install_path: Path) -> list[Path]:
    """Return steamapps directories across all Steam libraries."""

    libraries: list[Path] = []

    # Always include the main Steam library
    main_steamapps = steam_install_path / "steamapps"
    if main_steamapps.exists():
        libraries.append(main_steamapps)

    vdf_path = _libraryfolders_vdf_path(steam_install_path)
    if not vdf_path.exists():
        return libraries

    vdf_text = _read_text_best_effort(vdf_path)
    for library_root in _parse_libraryfolders_paths(vdf_text):
        steamapps = library_root / "steamapps"
        if steamapps.exists():
            libraries.append(steamapps)

    # De-dupe while preserving order
    unique: list[Path] = []
    seen: set[str] = set()
    for p in libraries:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def _parse_acf_value(acf_text: str, key: str) -> Optional[str]:
    # Simple tolerant matcher:  "key"  "value"
    m = re.search(rf'"{re.escape(key)}"\s+"(?P<value>.*?)"', acf_text, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group("value")


def get_installed_steam_apps(steamapps_dirs: Iterable[Path]) -> list[SteamApp]:
    apps: list[SteamApp] = []
    for steamapps_dir in steamapps_dirs:
        for manifest in steamapps_dir.glob("appmanifest_*.acf"):
            m = re.match(r"appmanifest_(?P<appid>\d+)\.acf$", manifest.name)
            if not m:
                continue
            appid = int(m.group("appid"))
            text = _read_text_best_effort(manifest)
            name = _parse_acf_value(text, "name") or f"Steam App {appid}"
            installdir = _parse_acf_value(text, "installdir")
            if not installdir:
                continue
            apps.append(
                SteamApp(
                    appid=appid,
                    name=name,
                    install_dir_name=installdir,
                    library_steamapps=steamapps_dir,
                )
            )
    return apps


def _is_ignored_app(app: SteamApp) -> bool:
    name = app.name.strip()
    if name.lower().endswith("soundtrack") or "soundtrack" in name.lower():
        return True
    if name == "Steamworks Common Redistributables":
        return True
    return False


def _steam_icon_candidates(steam_install_path: Path, appid: int) -> list[Path]:
    # Common Steam icon cache location for desktop shortcuts.
    # Typically: <Steam>\steam\games\<appid>.ico (and variants)
    games_dir = steam_install_path / "steam" / "games"
    if not games_dir.exists():
        return []
    return sorted(games_dir.glob(f"{appid}*.ico"))


def _ensure_ico_from_librarycache(
    steam_install_path: Path,
    appid: int,
) -> Optional[Path]:
    r"""Create a Steam-style .ico in steam\games from appcache images if needed.

    Some games do not ship an embedded icon in their .exe. Steam often still
    has cached artwork under appcache\librarycache\<appid>. We can convert the
    best available image into an .ico that Windows shortcuts can use.
    """

    existing = _steam_icon_candidates(steam_install_path, appid)
    if existing:
        return existing[0]

    cache_dir = steam_install_path / "appcache" / "librarycache" / str(appid)
    if not cache_dir.exists():
        return None

    # Prefer logo.png if present (often transparent), else fall back to header.
    candidates = [
        cache_dir / "logo.png",
        cache_dir / "header.jpg",
        cache_dir / "library_600x900.jpg",
        cache_dir / "library_hero.jpg",
    ]
    source = next((p for p in candidates if p.exists()), None)
    if not source:
        return None

    try:
        from PIL import Image
    except Exception:
        return None

    out_dir = steam_install_path / "steam" / "games"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{appid}.ico"

    try:
        with Image.open(source) as im:
            im = im.convert("RGBA")
            sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
            im.save(out_path, format="ICO", sizes=sizes)
        return out_path if out_path.exists() else None
    except Exception:
        return None


def _guess_main_exe(install_path: Path) -> Optional[Path]:
    if not install_path.exists():
        return None

    deny_substrings = {
        "crashhandler",
        "unins",
        "uninstall",
        "dxsetup",
        "vcredist",
        "redist",
        "installer",
        "setup",
        "unitycrashhandler",
        "easyanticheat",
        "eos",
        "battleye",
    }

    def score(exe: Path) -> int:
        name = exe.name.lower()
        s = 0
        if exe.parent == install_path:
            s += 50
        # prefer exe named like folder
        if exe.stem.lower() == install_path.name.lower():
            s += 40
        # smaller penalty for long nested paths
        depth = len(exe.relative_to(install_path).parts)
        s -= depth * 2
        # denylist
        if any(sub in name for sub in deny_substrings):
            s -= 100
        return s

    # Limit traversal to keep it fast.
    exes: list[Path] = []
    for root, dirs, files in os.walk(install_path):
        rel_depth = len(Path(root).relative_to(install_path).parts)
        if rel_depth > 3:
            dirs[:] = []
            continue
        for f in files:
            if f.lower().endswith(".exe"):
                exes.append(Path(root) / f)

    if not exes:
        return None

    exes.sort(key=score, reverse=True)
    best = exes[0]
    if score(best) < -50:
        return None
    return best


def _sanitize_filename_component(s: str) -> str:
    # Windows forbidden: <>:"/\\|?* and trailing spaces/dots.
    s = re.sub(r'[<>:"/\\|?*]', "_", s)
    s = s.strip().rstrip(".")
    return s


def _existing_appids_on_desktop(desktop: Path) -> set[int]:
    """Detect existing Steam shortcuts by reading .lnk/.url and extracting appid."""

    appids: set[int] = set()

    # .url
    for url in desktop.glob("*.url"):
        try:
            text = _read_text_best_effort(url)
        except OSError:
            continue
        m = re.search(r"steam://rungameid/(?P<appid>\d+)", text, flags=re.IGNORECASE)
        if m:
            appids.add(int(m.group("appid")))

    # .lnk
    try:
        import win32com.client
    except Exception:
        return appids

    shell = win32com.client.Dispatch("WScript.Shell")
    for lnk in desktop.glob("*.lnk"):
        try:
            shortcut = shell.CreateShortcut(str(lnk))
            target = (shortcut.TargetPath or "").lower()
            args = shortcut.Arguments or ""
        except Exception:
            continue

        # steam.exe -applaunch <appid>
        if target.endswith("steam.exe"):
            m = re.search(r"-applaunch\s+(?P<appid>\d+)", args)
            if m:
                appids.add(int(m.group("appid")))

        # occasionally a shortcut targets the URL directly
        m = re.search(r"steam://rungameid/(?P<appid>\d+)", args, flags=re.IGNORECASE)
        if m:
            appids.add(int(m.group("appid")))

    return appids


def _iter_steam_applaunch_shortcuts(desktop: Path) -> list[tuple[Path, int]]:
    """Return a list of (shortcut_path, appid) for Steam .lnk shortcuts."""

    try:
        import win32com.client
    except Exception:
        return []

    shell = win32com.client.Dispatch("WScript.Shell")
    results: list[tuple[Path, int]] = []

    for lnk in desktop.glob("*.lnk"):
        try:
            shortcut = shell.CreateShortcut(str(lnk))
            target = (shortcut.TargetPath or "").lower()
            args = shortcut.Arguments or ""
        except Exception:
            continue

        if not target.endswith("steam.exe"):
            continue

        m = re.search(r"-applaunch\s+(?P<appid>\d+)", args)
        if not m:
            continue

        results.append((lnk, int(m.group("appid"))))

    return results


def _best_icon_for_app(steam_install_path: Path, app: SteamApp) -> Path:
    """Resolve best icon path for an app (may generate a new .ico)."""

    candidates = _steam_icon_candidates(steam_install_path, app.appid)
    if candidates:
        return candidates[0]

    generated = _ensure_ico_from_librarycache(steam_install_path, app.appid)
    if generated:
        return generated

    guessed = _guess_main_exe(app.install_path)
    if guessed and guessed.exists():
        return guessed

    return steam_install_path / "steam.exe"


def create_desktop_shortcuts(
    steam_install_path: Path,
    desktop: Path,
    *,
    dry_run: bool,
    repair_icons: bool,
    only_appid: Optional[int],
    verbose: bool,
) -> int:
    """Create missing Steam shortcuts. Returns count created."""

    steamapps_dirs = get_steam_library_steamapps_paths(steam_install_path)
    apps = get_installed_steam_apps(steamapps_dirs)

    existing_appids = _existing_appids_on_desktop(desktop)
    if verbose:
        print(f"Desktop: {desktop}")
        print(f"Steam:   {steam_install_path}")
        print(f"Found {len(existing_appids)} existing Steam shortcuts on Desktop (appid-based).")

    import win32com.client

    shell = win32com.client.Dispatch("WScript.Shell")

    created = 0
    repaired = 0
    skipped_existing = 0
    skipped_ignored = 0
    skipped_noicon = 0

    existing_shortcuts_by_appid: dict[int, list[Path]] = {}
    for lnk_path, appid in _iter_steam_applaunch_shortcuts(desktop):
        existing_shortcuts_by_appid.setdefault(appid, []).append(lnk_path)

    for app in sorted(apps, key=lambda a: a.name.lower()):
        if only_appid is not None and app.appid != only_appid:
            continue

        if _is_ignored_app(app):
            skipped_ignored += 1
            continue

        if app.appid in existing_appids:
            skipped_existing += 1

            if repair_icons:
                best_icon = _best_icon_for_app(steam_install_path, app)
                for lnk_path in existing_shortcuts_by_appid.get(app.appid, []):
                    if verbose:
                        print(f"~ Repair icon: {lnk_path.name} -> {best_icon}")
                    if not dry_run:
                        try:
                            sc = shell.CreateShortcut(str(lnk_path))
                            sc.IconLocation = f"{best_icon},0"
                            sc.Save()
                            repaired += 1
                        except Exception:
                            pass

            continue

        steam_exe = steam_install_path / "steam.exe"
        if not steam_exe.exists():
            raise FileNotFoundError(f"steam.exe not found at: {steam_exe}")

        shortcut_name = _sanitize_filename_component(app.name)
        shortcut_path = desktop / f"{shortcut_name}.lnk"

        # icon selection:
        #   1) Steam cached .ico (steam\games\<appid>*.ico)
        #   2) Create .ico from appcache\librarycache images (logo/header)
        #   3) best-guess main game .exe
        #   4) steam.exe
        icon_path = _best_icon_for_app(steam_install_path, app)
        if icon_path.name.lower() == "steam.exe":
            skipped_noicon += 1

        if verbose:
            install_path_display = str(app.install_path) if app.install_path.exists() else "<missing>"
            print(f"+ {app.name} [{app.appid}]  install={install_path_display}")

        if dry_run:
            created += 1
            continue

        sc = shell.CreateShortcut(str(shortcut_path))
        sc.TargetPath = str(steam_exe)
        sc.Arguments = f"-applaunch {app.appid}"
        sc.WorkingDirectory = str(steam_install_path)
        sc.IconLocation = f"{icon_path},0"
        sc.Save()

        created += 1
        existing_appids.add(app.appid)

    print(
        "Summary:\n"
        f"  Created:          {created}{' (dry-run)' if dry_run else ''}\n"
        f"  Repaired icons:   {repaired}{' (dry-run)' if dry_run else ''}\n"
        f"  Skipped existing: {skipped_existing}\n"
        f"  Skipped ignored:  {skipped_ignored}\n"
        f"  No cached icon:   {skipped_noicon} (fell back to exe/steam icon)"
    )
    return created


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Do not write shortcuts; only print actions.")
    p.add_argument("--verbose", action="store_true", help="Print details for each app.")
    p.add_argument(
        "--repair-icons",
        action="store_true",
        help="Update icons for already-existing Steam .lnk shortcuts on the Desktop.",
    )
    p.add_argument(
        "--only-appid",
        type=int,
        default=None,
        help="Operate only on a single appid (useful for fixing one game).",
    )
    p.add_argument(
        "--steam-path",
        default=None,
        help="Override Steam install path (folder containing steam.exe).",
    )
    p.add_argument(
        "--desktop",
        default=None,
        help="Override Desktop path (folder to write shortcuts into).",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    _preflight_or_exit()
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))

    steam_install_path = Path(args.steam_path) if args.steam_path else _get_steam_install_path_from_registry()
    if not steam_install_path:
        # last resort: common default
        steam_install_path = Path(r"C:\Program Files (x86)\Steam")

    desktop = Path(args.desktop) if args.desktop else _get_desktop_path()

    try:
        create_desktop_shortcuts(
            steam_install_path=steam_install_path,
            desktop=desktop,
            dry_run=bool(args.dry_run),
            repair_icons=bool(args.repair_icons),
            only_appid=args.only_appid,
            verbose=bool(args.verbose),
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
