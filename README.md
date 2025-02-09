# A single unified Python script to perform the operation of recovering your lost Steam icons using the SteamCMD tool (command line Steam API).

You need to install SteamCMD from here and locate it in c:\SteamCMD: https://developer.valvesoftware.com/wiki/SteamCMD

First, install Python latest (3 of some variety) from https://www.python.org

Then you need to install virtualenv, 

```pip install virtualenv```

## Open a terminal...

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

## This is not perfect and some icons will still not be created potentially if the game titles have unusual exe names or strange subdirectory paths but it the script will do it's best.

