import requests
from ddgs import DDGS
from seleniumbase import SB
from bs4 import BeautifulSoup
import urllib.parse
import os
import shutil
from configparser import ConfigParser
import tkinter as tk
from tkinter import filedialog
import time
import sys

global configFile
global config

config = ConfigParser()
configFile = "settings.ini"


def extractTrackMetadata(inUrl, type):
    try:
        page = requests.get(inUrl)
        if page.status_code != 200:
            print('\nInvalid URL or Check Internet Connection.')
            return
    except Exception as e:
        print('Invalid URL')
        return
    page.encoding = 'utf-8'
    soup = BeautifulSoup(page.content, 'html.parser')
    title = soup.title.string
    match type:
        case 1:
            songName = title.replace(" - song and lyrics ", " ")
        case 2:
            songName = title.split(" – ")
            songName = songName[0] + songName[1].replace("Song by ", " by ")
            bad_quotes = "'\"‘’“”\u200e"
            songName = songName.strip(bad_quotes)
    return songName

def songling(inUrl):
    time.sleep(0.5)
    print('\nTrying direct search...')
    api_url = f"https://api.song.link/v1-alpha.1/links?url={inUrl}"
    headers = {
        "User-Agent": "MusicDownloaderCLI/1.0"
    }
    time.sleep(0.5)
    print('\nSending Search request...')
    response = requests.get(api_url, headers=headers)
    if response.status_code != 200:
        print(f"Error fetching data: {response.status_code}, Falling for manual web search...")
        scraping(inUrl)
    else:
        data = response.json()
        try:
            ASIN = data.get('linksByPlatform', {}).get('amazonMusic', {}).get('entityUniqueId', {}).split('::')[-1]
            print('\nSong Found for the corresponding URL.')
            time.sleep(2)
            downloadViaLucida(ASIN)
        except Exception as e:
            print("\nSong Not found, Falling for Scraping")
            scraping(inUrl)

def scraping(inUrl):

    def initiateScrapping(songName):
        print("\x1b[2J\x1b[H", end="")
        print(f"Initiating Manual Search for song: {songName}")
        ASIN, statusCode = ddgsScrapper(songName)
        if statusCode == 404:
            print('Validation Over - Incorrect Link...')
            time.sleep(0.5)
            print('Initiating stage 2 of Manual Search - Direct Browser Search, a browser instance will be launched')
            ASIN = scrapper2(songName)
        elif statusCode == 200:
            time.sleep(0.5)
            print('Validation Over - Correct Link...Initiating Download')
            downloadViaLucida(ASIN)

    if "spotify.com" in inUrl:
        songName = extractTrackMetadata(inUrl, 1)
        if songName == None:
            return
        initiateScrapping(songName)
    elif "apple.com" in inUrl:
        songName = extractTrackMetadata(inUrl, 2)
        initiateScrapping(songName)
    else:
        print("Unsupported URL")

def ddgsScrapper(songName):
    try:
        print("\x1b[2J\x1b[H", end="")
        print('Initiating Stage 1 of Manual Search - DuckDuckGo Search\n')
        results = DDGS().text("site:music.amazon.com " + songName + "/track/", max_results=1)
        ftHref = results[0]['href']
        print(f"\nFound Link: {ftHref}")
        print('Validating Link...')
        if "/tracks/" in ftHref:
            return ftHref.split('/')[-1][:10], 200
        else:
            return None, 404 
    except Exception as e:
        return None, 404

def scrapper2(songName):
    encoded_query = urllib.parse.quote_plus(songName)
    searchUrl = f"https://music.amazon.in/search/{encoded_query}"
    active_browser = config['parameters']['Browser']
    active_location = config['parameters']['location']
    with SB(browser=active_browser, binary_location=active_location, uc=True, headless=True) as sb:
        sb.activate_cdp_mode()
        sb.goto(searchUrl)
        try:
            if sb.wait_for_element_visible("music-horizontal-item", timeout=15):
                html_content = sb.get_page_source()
                locator = html_content.find('href="<music-horizontal-item') + len('music-horizontal-item')
                start = html_content.find('primary-href="', locator)
                end = html_content.find('"', start + 14)
                found_href = html_content[start + 14:end]
                print(f"Found href: {found_href}")
                if "/albums/" and "trackAsin" in found_href:
                    ASIN = found_href.split('trackAsin=')[-1][:10]
                    downloadViaLucida(ASIN)
                elif "/tracks/" in found_href:
                    ASIN = found_href.split('/tracks/')[-1][:10]
                    downloadViaLucida(ASIN)
                else:
                    print("\nASIN Not found, Couldn't find the music...")
                    return
            else:
                print("\nNo search results found.")
                print("\nASIN Not found, Couldn't find the music.")
                return
        except Exception as e:
            print(f"\nError occurred during scraping: {e}")
            print("\nASIN Not found, Couldn't connect to internet or find the music.")
            return


def downloadViaLucida(ASIN):
    print("\x1b[2J\x1b[H", end="")
    download_dir = "downloaded_files"
    encoded_query = urllib.parse.quote_plus(f"{ASIN}&country=auto")
    lucidaUrl = f"https://lucida.to/?url=https%3A%2F%2Fmusic.amazon.in%2Ftracks%2F{encoded_query}"
    active_browser = config['parameters']['Browser']
    active_location = config['parameters']['location']
    with SB(browser=active_browser, binary_location=active_location, uc=True, headless=True) as sb:
        def captchaCheck():
            try:
                if sb.get_page_title() == "Just a moment...":
                    print("Cloudflare challenge detected! Initiating automated bypass...")
                    sb.solve_captcha()
                    sb.sleep(2)
                    sys.stdout.write("\033[F\033[K")
                    captchaCheck()
                else:
                    return
            except Exception as e:
                print("\nFailed during captcha Bypass. Try again.")
                return
            
        def downloadCheck(download_dir):
            stall_counter = 0
            refresh_retries = 0
            while True:
                files = os.listdir(download_dir)
                is_downloading = any(f.endswith(".crdownload") for f in files)
                finished_file = next((f for f in files if f.endswith(".flac")), None)
                if is_downloading:
                    print("Downloading.....")
                    sb.sleep(2)
                    sys.stdout.write("\033[F\033[K")
                    continue
                elif not is_downloading and finished_file is not None:
                    print("Download Finished!!!")
                    print("Cleaning & Saving File...")
                    folderName = config['parameters']['saveLocation']
                    source_path = os.path.join(download_dir, finished_file)
                    destination_path  = os.path.join(folderName, finished_file)
                    if not os.path.exists(folderName):
                        os.makedirs(folderName)
                    shutil.move(source_path, destination_path)
                    break
                else:
                    print("Waiting for File download...")
                    sb.sleep(2)
                    sys.stdout.write("\033[F\033[K")
                    stall_counter += 1
                    
                    # If it waits more than 20 seconds (10 loops * 2s) without initializing a file
                    if stall_counter > 20:
                        refresh_retries += 1
                        if refresh_retries > 3:
                            print("\n[Error] Backend is completely unresponsive after 3 attempts. Your internet can be slow. Aborting")
                            break
                            
                        print(f"\n[Warning] Initial download stalled (Attempt {refresh_retries}/3). Refreshing page...")
                        sb.refresh()
                        sb.sleep(3)
                        captchaCheck()
                        sb.wait_for_element_visible("button.download-button", timeout=30)
                        sb.click("button.download-button")
                        
                        # Reset stall loop tracker for the fresh page instance iteration
                        stall_counter = 0 
                        continue
                    continue

        print('Browser Launched.')
        sb.activate_cdp_mode()
        sb.goto(lucidaUrl)
        captchaCheck()
        sb.wait_for_element_visible("button.download-button", timeout=30)
        sb.sleep(2)
        sb.click("button.download-button")
        sb.sleep(2)
        downloadCheck(download_dir)
        sb.sleep(2)
        
def createConfig():
    config['parameters'] = {
            'launchNumber' : 0,
            'Browser':'chrome',
            'location': r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            'saveLocation': 'Complete_Download'
        }
    with open(configFile, 'w') as configfile:
        config.write(configfile)

def configMode():
    def iniconfig():
        config.read(configFile)
        print("\x1b[2J\x1b[H", end="")
        print('Current Settings')
        print(f'''Browser = {config['parameters']['Browser']}
Location = {config['parameters']['location']}
Save Location = {config['parameters']['saveLocation']}''')
        while True:
            time.sleep(0.5)
            change = input("\nEnter '1' to change or '0' to leave as it is: ").strip()
            if change in ["1", "0"]:
                break
            print('\nInvalid Input. Please enter 1 or 0.')
        while True:
            if change == "1":
                time.sleep(0.5)
                print('Select the browser executable exe')
                root = tk.Tk()
                root.withdraw()
                file_path = filedialog.askopenfilename(
                    title="Select a File",
                    filetypes=[("executable files", "*.exe")]
                )
                while True:
                    time.sleep(0.5)
                    saveLChange = input('\nDo you want to change the default save location(y/n): ')
                    if saveLChange.lower() == 'y':
                        while True:
                            save_path = filedialog.askdirectory(title="Select a Folder")
                            if save_path:
                                config['parameters']['saveLocation'] = save_path
                                break
                            else:
                                print('Invalid File type')
                                continue
                    elif saveLChange.lower() == 'n':
                        pass
                    else:
                        print('Invalid Input')
                        continue
                    break
                if file_path:
                    print(f"Selected file: {file_path}")
                    browser = file_path.split('/')[-1].split('.')[0]
                    config['parameters']['location'] = file_path
                    config["parameters"]["Browser"] = browser
                    with open(configFile, 'w') as configfile:
                        config.write(configfile)
                    break
                else:
                    print("No file was selected.")
                    continue
            elif change == "0":
                downloadMode()
                return
        downloadMode()
    print('Welcome to Config Mode')
    if os.path.exists(configFile):
        iniconfig()
    else:
        createConfig()
        iniconfig()
    
def downloadMode():
    launch_count = int(config['parameters'].get('launchNumber', '0'))
    config['parameters']['launchNumber'] = str(launch_count + 1)
    with open(configFile, 'w') as configfile: 
        config.write(configfile)
    time.sleep(0.5)
    inUrl = input("Enter the URL(Spotify & Apple Music Only): ")
    time.sleep(0.5)
    print('Url accepted, seaching for the song...')
    ASIN = songling(inUrl)

def main():
    print('Welcome to MusicDownloaderCLI\n')
    time.sleep(0.5)
    iniConfig = input("Hit 'Enter' to continue or Type 1 and hit 'Enter' for Config Mode: ")
    if iniConfig == "1":
        configMode()
    else:
        if os.path.exists(configFile) == False:
            createConfig()
        config.read(configFile)
        launch_count = int(config['parameters'].get('launchNumber', '0'))
        if launch_count == 0:
            print('\nThis is your first launch, So launching into config mode\n')
            time.sleep(2)
            configMode()
        else:
            downloadMode()



if __name__ == "__main__":
    main()
