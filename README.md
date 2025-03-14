# A single unified Python script to perform the operation of recovering your lost Steam icons using the SteamCMD tool (command line Steam API).
# If icons already exist as shortcuts or steam urls on your desktop then they will not be duplicated.
## Soundtrack icons are avoided.

# First clone this repository:

## Install git from here: https://git-scm.com/downloads/win

## You need to install SteamCMD from here and locate it in c:\SteamCMD: https://developer.valvesoftware.com/wiki/SteamCMD

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

## Install dependencies:

```pip install -r requirements.txt```

## Run Python script to perform a best effort attempt to recover your icons.

```python steamfixicons.py```


# NOTE

## Some icons _may_ not be created if the game titles have unusual exe names or strange subdirectory paths; the script should do a solid job of 99% of your game titles though.

