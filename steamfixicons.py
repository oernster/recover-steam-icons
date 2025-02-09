import os
import re
import win32com.client
from fuzzywuzzy import process
from PIL import Image
import pywintypes
import win32gui, win32api, win32con

# 🔹 Required Dependencies:
# pip install pillow pywin32 fuzzywuzzy python-Levenshtein

# 🔹 Steam Config Path
STEAM_CONFIG = r"C:\\Program Files (x86)\\Steam\\config\\libraryfolders.vdf"
STEAM_APPS = "steamapps"

# 🔹 Desktop Path for Shortcuts
DESKTOP_PATH = os.path.join(os.getenv("USERPROFILE"), "Desktop")

# 🔹 Function to get Steam libraries
def get_steam_libraries():
    libraries = []
    try:
        with open(STEAM_CONFIG, "r", encoding="utf-8") as file:
            content = file.read()
            matches = re.findall(r'"\d+"\s*\{\s*"path"\s*"([^"]+)"', content)
            for path in matches:
                path = path.replace("\\\\", "\\")  # Fix double slashes
                library_path = os.path.join(path, STEAM_APPS)
                if os.path.exists(library_path):
                    libraries.append(library_path)
                else:
                    print(f"⚠️ Skipping invalid library path: {library_path}")
    except FileNotFoundError:
        print("❌ Steam configuration file not found.")
    return libraries

# 🔹 Function to get installed games
def get_installed_games():
    installed_games = {}
    libraries = get_steam_libraries()

    print("🔄 Checking installed games...")
    
    for library in libraries:
        print(f"📂 Scanning library: {library}")
        try:
            acf_files = [
                os.path.join(library, file)
                for file in os.listdir(library)
                if file.startswith("appmanifest_") and file.endswith(".acf")
            ]
            for acf_file in acf_files:
                with open(acf_file, "r", encoding="utf-8") as file:
                    data = file.read()
                    game_name_match = re.search(r'"name"\s+"(.+?)"', data)
                    install_dir_match = re.search(r'"installdir"\s+"(.+?)"', data)
                    if game_name_match and install_dir_match:
                        game_name = game_name_match.group(1)
                        install_dir = install_dir_match.group(1)
                        library_path = os.path.dirname(acf_file)
                        game_path = os.path.join(library_path, "common", install_dir)
                        installed_games[game_name] = game_path
                        print(f"✅ Found game: {game_name} at {game_path}")
        except Exception as e:
            print(f"⚠️ Error processing library: {library}, {e}")
    return installed_games

# 🔹 Create Steam URL Shortcut
def create_steam_url_shortcuts():
    installed_games = get_installed_games()
    shell = win32com.client.Dispatch("WScript.Shell")
    existing_files = set(f.lower() for f in os.listdir(DESKTOP_PATH))
    
    for game_name, game_path in installed_games.items():
        if "Steamworks Common Redistributables" in game_name or "soundtrack" in game_name.lower():
            continue
        
        shortcut_filename = f"{game_name}.url".lower()
        if shortcut_filename in existing_files or any(fuzzy_match(game_name, existing_files)):
            print(f"⚠️ Shortcut already exists: {game_name}. Skipping.")
            continue
        
        exe_path = find_executable(game_path)
        if not exe_path:
            print(f"❌ Could not determine executable for: {game_name}. Skipping.")
            continue
        
        try:
            with open(os.path.join(DESKTOP_PATH, shortcut_filename), "w") as url_file:
                url_file.write(f"[InternetShortcut]\nURL=steam://rungameid/{game_name}\nIconFile={exe_path}\nIconIndex=0\n")
            print(f"✅ Created shortcut for: {game_name}")
        except Exception as e:
            print(f"❌ Error creating shortcut for {game_name}: {e}")

# 🔹 Find Executable File
def find_executable(game_path):
    try:
        all_executables = [f for f in os.listdir(game_path) if f.endswith(".exe")]
        if not all_executables:
            return None
        return os.path.join(game_path, all_executables[0])
    except Exception:
        return None

# 🔹 Fuzzy Match Game Names to Avoid Duplication
def fuzzy_match(name, existing_names):
    if not existing_names:
        return []
    match = process.extractOne(name, list(existing_names), score_cutoff=90)
    return match if match else []

# 🔹 Run the Fix
def main():
    print("🔄 Scanning Steam libraries and creating missing shortcuts...")
    create_steam_url_shortcuts()
    print("✅ Shortcut creation complete!")

if __name__ == "__main__":
    main()
