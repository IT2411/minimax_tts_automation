import os
import csv
import glob
import time
import shutil
import subprocess
import yaml
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

class SeleniumWebController:
    # Map string names from YAML to Selenium By classes
    BY_MAP = {
        "ID": By.ID,
        "XPATH": By.XPATH,
        "CSS_SELECTOR": By.CSS_SELECTOR,
        "NAME": By.NAME,
        "CLASS_NAME": By.CLASS_NAME,
        "LINK_TEXT": By.LINK_TEXT
    }

    # Standard model list extracted from the HTML dropdown options
    MODELS = [
        "speech-2.8-hd",
        "speech-2.8-turbo",
        "speech-2.6-hd",
        "speech-2.6-turbo",
        "speech-2.5-hd",
        "speech-2.5-turbo",
        "speech-02-hd",
        "speech-02-turbo",
        "speech-01-hd",
        "speech-01-turbo"
    ]

    def __init__(self, config_path="selectors.yaml", profile_dir="./chrome_profile"):
        """Initializes paths, loads the YAML configuration, and prepares directories."""
        self.config_path = config_path
        self.profile_dir = os.path.abspath(profile_dir)
        self.driver = None
        self.wait = None
        self.config = {}
        self.available_voices = []  # List to store collected voices
        self.current_voice = None   # Tracks the currently active voice in browser
        
        self._load_config()
        
        # Retrieve directories and configuration parameters from YAML config
        self.download_dir = os.path.abspath(self.config.get("download_dir", "tts_outputs"))
        self.upload_dir = os.path.abspath(self.config.get("upload_dir", "tts_inputs"))
        self.csv_dir = os.path.abspath(self.config.get("csv_dir", "csv_data"))
        self.change_account = self.config.get("change_account", False)
        
        # Define tracking CSV path for pause/resume functionality
        self.completed_csv_path = os.path.join(self.csv_dir, "completed_runs.csv")
        
        # Ensure version is cast strictly to an integer
        try:
            self.chrome_version = int(self.config.get("chrome_version", 148))
        except (ValueError, TypeError):
            self.chrome_version = 148
        
        self._prepare_local_folders()
        self.completed_set = self._load_completed_set()

    def _load_config(self):
        """Loads configuration from the YAML file."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Configuration file not found at: {self.config_path}")
        
        with open(self.config_path, "r") as file:
            self.config = yaml.safe_load(file)

    def _prepare_local_folders(self):
        """Creates required directories."""
        for directory in [self.download_dir, self.upload_dir, self.csv_dir, self.profile_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)

    def _load_completed_set(self):
        """Loads completed filenames from completed_runs.csv into a memory set for fast lookup."""
        completed = set()
        if os.path.exists(self.completed_csv_path):
            try:
                with open(self.completed_csv_path, mode="r", encoding="utf-8") as file:
                    reader = csv.DictReader(file)
                    for row in reader:
                        filename = row.get("filename")
                        if filename:
                            completed.add(filename)
                print(f"Loaded {len(completed)} completed generations from log file.")
            except Exception as e:
                print(f"Notice: Failed to load completed tracking file: {e}")
        return completed

    def _log_completed_generation(self, filename, transcription, model):
        """Appends a successfully generated audio run to the tracking CSV file."""
        file_exists = os.path.exists(self.completed_csv_path)
        try:
            with open(self.completed_csv_path, mode="a", encoding="utf-8", newline="") as file:
                fieldnames = ["filename", "transcription", "model_used", "timestamp"]
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow({
                    "filename": filename,
                    "transcription": transcription,
                    "model_used": model,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })
            self.completed_set.add(filename)
            print(f"Successfully logged completion of {filename} inside tracking log.")
        except Exception as e:
            print(f"Warning: Failed to write to tracking file: {e}")

    def _kill_background_processes(self):
        """Terminates lingering background Chrome and Chromedriver processes on Windows."""
        if os.name == 'nt':
            print("Cleaning up background Chrome tasks...")
            try:
                subprocess.run("taskkill /f /im chrome.exe", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
                subprocess.run("taskkill /f /im chromedriver.exe", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
                time.sleep(1)
            except Exception as e:
                print(f"Notice: Background task cleanup bypassed: {e}")

    def _clear_uc_cache(self):
        """Purges old or mismatched chromedriver binaries cached in AppData."""
        cache_paths = []
        
        local_appdata = os.getenv("LOCALAPPDATA")
        if local_appdata:
            cache_paths.append(os.path.join(local_appdata, "undetected_chromedriver"))
            
        appdata = os.getenv("APPDATA")
        if appdata:
            cache_paths.append(os.path.join(appdata, "undetected_chromedriver"))
            
        for path in cache_paths:
            if os.path.exists(path):
                try:
                    shutil.rmtree(path)
                    print(f"Cleared cached binary directory at: {path}")
                except Exception as e:
                    print(f"Notice: Could not automatically clear cache directory: {e}")

    def _clear_profile_locks(self):
        """Removes potential Chrome lock files inside the profile directory to prevent hanging."""
        lock_files = ["SingletonLock", "SingletonCookie", "lock"]
        for lock in lock_files:
            file_path = os.path.join(self.profile_dir, lock)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"Removed profile lock file: {lock}")
                except Exception as e:
                    print(f"Notice: Could not remove lock file '{lock}': {e}")

    def _get_locator(self, element_name):
        """Retrieves and maps the selector from the element format: ['type', 'value']."""
        try:
            locator_data = self.config[element_name]
            by_strategy = self.BY_MAP[locator_data[0].upper()]
            selector_value = locator_data[1]
            return (by_strategy, selector_value)
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"Invalid or missing configuration format for '{element_name}': {e}")

    def start_browser(self):
        """Configures options, cleans background processes, clears cache, and launches undetected Chrome."""
        self._kill_background_processes()
        self._clear_profile_locks()
        self._clear_uc_cache()
        
        print("Starting undetected Chrome browser...")
        chrome_options = uc.ChromeOptions()
        
        # Enable persistent user profile
        chrome_options.add_argument(f"--user-data-dir={self.profile_dir}")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-notifications")
        
        # Configure automatic downloads in Chrome options
        prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": False,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        self.driver = uc.Chrome(
            options=chrome_options, 
            use_subprocess=True, 
            version_main=self.chrome_version
        )
        self.wait = WebDriverWait(self.driver, 20)
        
        # Configure CDP for global browser file downloads
        try:
            self.driver.execute_cdp_cmd("Browser.setDownloadBehavior", {
                "behavior": "allow", 
                "downloadPath": self.download_dir,
                "eventsEnabled": True
            })
            print("Configured global Browser download behavior targeting custom output folder.")
        except Exception as e:
            # Fallback to page level command
            try:
                self.driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                    "behavior": "allow", 
                    "downloadPath": self.download_dir
                })
            except Exception:
                print(f"Warning: CDP setDownloadBehavior configuration bypassed: {e}")

    def open_website(self, url):
        """Navigates to the specified URL."""
        if not self.driver:
            raise RuntimeError("Browser is not started.")
        print(f"Navigating to: {url}")
        self.driver.get(url)

    def check_and_request_manual_login(self, check_locator):
        """
        Manages verification of the login session. 
        If change_account is enabled in YAML, forces execution pause to allow switching profiles.
        """
        if self.change_account:
            print("\n" + "="*60)
            print("Notice: 'change_account' flag is active.")
            print("Please take this time to manually log out and switch profiles in the browser window.")
            print("Once you are logged into your targeted account, return here and press ENTER.")
            print("="*60 + "\n")
            input("Press [Enter] here once account transition is complete...")
            return

        try:
            self.driver.find_element(*check_locator)
            print("Active session detected. Proceeding...")
        except Exception:
            print("\n" + "="*60)
            print("Action Required: Please log in manually in the browser window.")
            print("Once you are logged in, return to this terminal and press ENTER.")
            print("="*60 + "\n")
            input("Press [Enter] here once you have finished logging in...")

    def select_model(self, model_name):
        """Clicks the model dropdown and selects the specified target model."""
        if not self.driver:
            raise RuntimeError("Browser is not started.")
        
        print(f"Selecting model: {model_name}")
        
        # Open dropdown utilizing the specified locator: //p[normalize-space()='Model']
        dropdown_trigger = self.wait.until(EC.element_to_be_clickable(self._get_locator("model_dropdown_button")))
        self._safe_click(dropdown_trigger)
        time.sleep(1.5) # Wait for options to render
        
        # Locate the specific model within the ant-select role="option" menu matching the text element
        target_option_locator = (By.XPATH, f"//div[@role='option']//p[normalize-space()='{model_name}']")
        
        try:
            model_element = self.wait.until(EC.visibility_of_element_located(target_option_locator))
            self._safe_click(model_element)
            print(f"Successfully switched to model: {model_name}")
            time.sleep(2.0) # Allow system configuration loading wait
        except Exception as e:
            raise RuntimeError(f"Failed to find or select the model option '{model_name}': {e}")

    def collect_my_voices(self):
        """Opens voice selection popup, collects all custom voices names inside h4 elements, and closes it."""
        if not self.driver:
            raise RuntimeError("Browser is not started.")
        
        print("Opening voice modal to collect available voices...")
        trigger = self.wait.until(EC.element_to_be_clickable(self._get_locator("voice_modal_trigger")))
        self._safe_click(trigger)
        time.sleep(1.5)
        
        # Click "My Voices" Tab
        my_voices_tab = self.wait.until(EC.element_to_be_clickable(self._get_locator("my_voices_tab")))
        self._safe_click(my_voices_tab)
        time.sleep(1.5)
        
        # Target voice names located inside h4 tags within the modal container
        voice_name_locator = (By.XPATH, "//div[contains(@class, 'ant-modal')]//h4")
        
        try:
            elements = self.driver.find_elements(*voice_name_locator)
            self.available_voices = [el.text.strip() for el in elements if el.text.strip()]
            
            if not self.available_voices:
                raise RuntimeError("No custom voices were found under the 'My Voices' tab.")
                
            print(f"Collected {len(self.available_voices)} custom voices: {self.available_voices}")
            
            # Close the modal to return to main editor view
            close_btn = self.wait.until(EC.element_to_be_clickable(self._get_locator("modal_close_button")))
            self._safe_click(close_btn)
            time.sleep(1.0)
            
        except Exception as e:
            raise RuntimeError(f"Failed to collect available voices: {e}")

    def select_voice(self, voice_name):
        """Opens voice modal, clicks 'Use' on specified voice. Bypasses if already active."""
        if not self.driver:
            raise RuntimeError("Browser is not started.")
            
        print(f"Switching voice to: {voice_name}")
        
        # Open voice modal trigger
        trigger = self.wait.until(EC.element_to_be_clickable(self._get_locator("voice_modal_trigger")))
        self._safe_click(trigger)
        time.sleep(1.5)
        
        # Click "My Voices" tab
        my_voices_tab = self.wait.until(EC.element_to_be_clickable(self._get_locator("my_voices_tab")))
        self._safe_click(my_voices_tab)
        time.sleep(1.5)
        
        # Target the parent container matching the voice name h4
        row_xpath = f"//div[contains(@class, 'ant-modal')]//div[contains(@class, 'cursor-pointer') and .//h4[text()='{voice_name}']]"
        
        try:
            # Check if this voice is already active / Selected
            selected_indicator_xpath = f"{row_xpath}//*[text()='Selected']"
            is_selected = len(self.driver.find_elements(By.XPATH, selected_indicator_xpath)) > 0
            
            if is_selected:
                print(f"Voice '{voice_name}' is already active. Closing modal.")
                close_btn = self.wait.until(EC.element_to_be_clickable(self._get_locator("modal_close_button")))
                self._safe_click(close_btn)
                time.sleep(1.0)
                return
                
            # If not selected, locate and click 'Use' on the matching row (corrected tuple evaluation)
            use_button_locator = (By.XPATH, f"{row_xpath}//button[contains(., 'Use')] | {row_xpath}//*[contains(text(), 'Use')]")
            use_button = self.wait.until(EC.element_to_be_clickable(use_button_locator))
            self._safe_click(use_button)
            print(f"Voice switch complete. Now using: {voice_name}")
            time.sleep(1.5) # Allow the modal close animation to finish
            
        except Exception as e:
            raise RuntimeError(f"Failed to switch voice to '{voice_name}': {e}")

    def type_text(self, input_locator, text):
        """Clears target input field and types the provided text."""
        if not self.driver:
            raise RuntimeError("Browser is not started.")
        
        print(f"Typing text: {text[:60]}...")
        text_area = self.wait.until(EC.element_to_be_clickable(input_locator))
        text_area.click()
        time.sleep(0.3)
        
        text_area.send_keys(Keys.CONTROL + 'a')
        time.sleep(0.2)
        text_area.send_keys(Keys.DELETE)
        time.sleep(0.3)
        
        text_area.send_keys(text)
        time.sleep(0.5)
        print("Text inserted successfully.")

    def click_generate(self, button_locator):
        """Clicks the generation button."""
        if not self.driver:
            raise RuntimeError("Browser is not started.")
        
        print("Clicking generation button...")
        generate_btn = self.wait.until(EC.element_to_be_clickable(button_locator))
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", generate_btn)
        time.sleep(0.15)
        self.driver.execute_script("arguments[0].click();", generate_btn)
        print("Generation initiated.")

    def _safe_click(self, element):
        """Attempts to click using native Selenium interactions to fire React state changes properly."""
        try:
            element.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", element)

    def _wait_for_download_completion(self, initial_files, timeout_seconds=30):
        """Monitors the download directory until a new, completed file is found."""
        print("Monitoring download directory for the output file...")
        start_time = time.time()
        
        while time.time() - start_time < timeout_seconds:
            current_files = set(os.listdir(self.download_dir))
            new_files = current_files - initial_files
            
            # Filter out files with active temporary download extensions
            completed_files = [
                f for f in new_files 
                if not f.endswith((".crdownload", ".tmp", ".part"))
            ]
            
            if completed_files:
                file_name = completed_files[0]
                full_path = os.path.join(self.download_dir, file_name)
                print(f"Download complete: {file_name} saved at {full_path}")
                return file_name
                
            time.sleep(1)
            
        raise TimeoutError("Download tracking timed out. The file was not saved.")

    def download_file(self, download_locator, format_locator, wait_seconds=30):
        """Clicks download, handles format selection, and tracks the resulting download to completion."""
        if not self.driver:
            raise RuntimeError("Browser is not started.")
            
        # Snapshot the download directory's state prior to trigger
        initial_directory_snapshot = set(os.listdir(self.download_dir))
        
        print("Locating and clicking download button...")
        download_btn = self.wait.until(EC.element_to_be_clickable(download_locator))
        self._safe_click(download_btn)
        
        print("Waiting for format selection menu to appear...")
        time.sleep(1.5)
        
        try:
            print("Searching for WAV selection option...")
            wav_option = self.wait.until(EC.visibility_of_element_located(format_locator))
            self._safe_click(wav_option)
            print("WAV option clicked.")
        except Exception as e:
            raise RuntimeError(f"Failed to locate or select the WAV option: {e}")
            
        # Dynamically monitor the local folder for download completion and return filename
        return self._wait_for_download_completion(initial_directory_snapshot, timeout_seconds=wait_seconds)

    def rename_file(self, temp_filename, target_filename):
        """Renames a freshly downloaded file to the CSV specified filename."""
        old_path = os.path.join(self.download_dir, temp_filename)
        new_path = os.path.join(self.download_dir, target_filename)
        
        if os.path.exists(new_path):
            os.remove(new_path)
            
        os.rename(old_path, new_path)
        print(f"Renamed output file to: {target_filename}")

    def process_csv_files(self):
        """Finds all CSV files in the input directory and executes the tts loop per row, split by model."""
        csv_pattern = os.path.join(self.csv_dir, "*.csv")
        csv_files = glob.glob(csv_pattern)
        
        # Exclude the tracking log file from target inputs if present in the same directory
        csv_files = [f for f in csv_files if os.path.basename(f) != "completed_runs.csv"]
        
        if not csv_files:
            print(f"No CSV files found in directory: {self.csv_dir}")
            return

        # Dynamically capture custom voices on system startup
        self.collect_my_voices()

        for csv_file in csv_files:
            print(f"\nProcessing CSV file: {csv_file}")
            
            # Read all rows of the current CSV
            rows = []
            with open(csv_file, mode="r", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                rows = [row for row in reader if row.get("filename") and row.get("transcription")]

            total_rows = len(rows)
            if total_rows == 0:
                print(f"Warning: CSV file {csv_file} is empty or lacks required headers.")
                continue

            num_models = len(self.MODELS)
            print(f"Total rows parsed: {total_rows}. Dividing across {num_models} models.")
            
            # Partitioning calculations (e.g., 250 rows per model for a 2500 row CSV)
            chunk_size = total_rows // num_models
            remainder = total_rows % num_models
            
            # Map each model to its specific chunk of rows
            model_to_rows = {}
            start_index = 0
            for i, model in enumerate(self.MODELS):
                current_chunk_size = chunk_size + (1 if i < remainder else 0)
                end_index = start_index + current_chunk_size
                model_to_rows[model] = rows[start_index:end_index]
                start_index = end_index

            # Run execution loops for each partitioned model
            for model_name, model_rows in model_to_rows.items():
                if not model_rows:
                    continue  # Skip model if no rows were allocated to it
                
                # Check if all rows in this model slice are completed before switching models.
                valid_rows = []
                for row in model_rows:
                    fn = row.get("filename")
                    if not fn.lower().endswith(".wav"):
                        fn += ".wav"
                    if fn not in self.completed_set and not os.path.exists(os.path.join(self.download_dir, fn)):
                        valid_rows.append(row)
                
                if not valid_rows:
                    print(f"All partition rows for model {model_name} are already completed. Skipping model selection.")
                    continue
                
                # Switch to the corresponding model before processing its rows
                self.select_model(model_name)
                
                for idx, row in enumerate(model_rows):
                    target_filename = row.get("filename")
                    transcription_text = row.get("transcription")
                    
                    # Sanitize target filename extension
                    if not target_filename.lower().endswith(".wav"):
                        target_filename += ".wav"
                    
                    target_filepath = os.path.join(self.download_dir, target_filename)
                    
                    # Pause/resume skip check
                    if target_filename in self.completed_set or os.path.exists(target_filepath):
                        print(f"Skipping ({target_filename}): File already exists or marked completed.")
                        continue
                    
                    # Voice Selection Rotation Calculation
                    # Rotates voice every 5 entries based on the index inside the partition
                    voice_index = (idx // 5) % len(self.available_voices)
                    target_voice = self.available_voices[voice_index]
                    
                    # Check and execute voice switch if it differs from current session voice
                    if self.current_voice != target_voice:
                        self.select_voice(target_voice)
                        self.current_voice = target_voice
                    
                    print(f"\n--- Model: {model_name} | Voice: {target_voice} | Processing Row {idx+1}/{len(model_rows)} ---")
                    print(f"Output File Name  : {target_filename}")
                    print(f"Transcription Text: {transcription_text[:60]}...")
                    
                    # Run Web Workflow
                    self.type_text(
                        input_locator=self._get_locator("text_input"),
                        text=transcription_text
                    )
                    
                    self.click_generate(button_locator=self._get_locator("generate_button"))
                    
                    print("Waiting for generation processing buffer...")
                    time.sleep(10)
                    
                    # Trigger download and receive temporary name
                    temp_downloaded_name = self.download_file(
                        download_locator=self._get_locator("download_button"),
                        format_locator=self._get_locator("wav_format_option"),
                        wait_seconds=30
                    )
                    
                    # Rename downloaded output to correct CSV filename
                    self.rename_file(temp_downloaded_name, target_filename)
                    
                    # Log successfully completed run to track state for pause/resume
                    self._log_completed_generation(target_filename, transcription_text, model_name)
                    
                    # Small throttle delay between browser generations
                    time.sleep(2)

    def close_browser(self):
        """Closes the browser session."""
        if self.driver:
            self.driver.quit()
            print("Browser closed.")


# Execution block
if __name__ == "__main__":
    controller = SeleniumWebController(config_path="selectors.yaml")

    try:
        controller.start_browser()

        # Retrieve target URL from YAML config
        target_page_url = controller.config["page_url"]

        # Step 1: Open the page first
        controller.open_website(target_page_url)

        # Step 2: Manage Session/Login
        logout_indicator = controller._get_locator("logout_indicator")
        controller.check_and_request_manual_login(check_locator=logout_indicator)

        # Step 3: Run through all rows in found CSV files partitioned equally across models
        controller.process_csv_files()

    except Exception as error:
        print(f"\nExecution halted due to error: {error}")

    finally:
        controller.close_browser()