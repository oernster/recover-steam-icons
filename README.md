# Recover missing Steam desktop icons (without duplicates)

This repository contains a single Python script that scans your Steam libraries
and ensures each installed game has a **Desktop shortcut**.

Key behavior:

- Creates **Windows `.lnk` shortcuts** (reliable launching + icons).
- Launches games via **Steam appid** using `steam.exe -applaunch <appid>`.
- Avoids duplicates by detecting existing Desktop shortcuts by **appid**.
- Skips common noise entries like *soundtracks* and *Steamworks Common Redistributables*.

# First clone this repository:

## Install git from here: https://git-scm.com/downloads/win

## SteamCMD is not required

Older versions of this project referenced SteamCMD; the current script does **not** use SteamCMD.

## Install Python latest (3 of some variety) from https://www.python.org

## Open a terminal...

Enter the command...

```git clone https://github.com/oernster/recover-steam-icons.git```

Then you need to install virtualenv, 

```pip install virtualenv```

## Now create a directory to work in:

```mkdir c:\fixsteamicons```

## Change directory to the created directory:

```cd c:\fixsteamicons```

## Create the virtualenv:

```python -m venv venv```

## Activate the virtualenv:

```venv\scripts\activate```

## Install dependencies (ALWAYS in a venv)

From the repo root:

```powershell
python -m venv venv
```

Activate it:

```powershell
venv\Scripts\Activate.ps1
```

Then install:

```powershell
python -m pip install -r requirements.txt
```

## Run

```powershell
python .\steamfixicons.py
```

### Useful options

- Preview what would be created (does not write files):

```powershell
python .\steamfixicons.py --dry-run --verbose
```

- If Steam is installed in a non-standard location:

```powershell
python .\steamfixicons.py --steam-path "D:\Steam"
```

- If you want to write shortcuts to a different folder:

```powershell
python .\steamfixicons.py --desktop "C:\Users\Oliver\Desktop"
```

- Fix icons for shortcuts that already exist (without creating/removing any shortcuts):

```powershell
python .\steamfixicons.py --repair-icons
```

- Fix a single game (example: Noita appid 881100):

```powershell
python .\steamfixicons.py --repair-icons --only-appid 881100
```


# NOTE

## Notes / troubleshooting

- If you see `ModuleNotFoundError: No module named 'win32com'`, your **venv** is missing `pywin32`.
  Make sure the venv is activated (your prompt should show `(venv)`), then re-run:

```powershell
python -m pip install -r requirements.txt
```

- Icons are chosen in this order:
  1) Steam cached `.ico` files (if available)
  2) Convert Steam cached artwork to an `.ico` (requires Pillow)
  3) A “best guess” main game `.exe`
  4) Steam's icon as a fallback

