# MiniMax TTS Automation Controller

An automated, object-oriented script built with Python and Selenium (`undetected-chromedriver`) to process batch Text-to-Speech (TTS) generations on MiniMax. It divides input entries across multiple models, rotates through custom voice profiles, handles secure downloads, and logs completed jobs to support seamless pause and resume operations.

---

## Features

- **Undetected Browser Automation**: Uses `undetected-chromedriver` to safely bypass typical automation challenges and bot-detection walls.
- **YAML Configuration**: Externalizes site locators, paths, and options in a clean, easily modified configuration file (`selectors.yaml`).
- **Dynamic Model Partitioning**: Automatically divides total rows from any CSV file in the inputs directory equally across 10 separate synthesis models (such as `speech-2.8-hd`, `speech-2.8-turbo`, etc.).
- **Sequential Voice Rotation**: Scans the "My Voices" tab upon launch, captures all custom voices, and rotates through them sequentially, switching the active voice after every 5 generations.
- **WAV Download & Rename**: Triggers the download dropdown interface, clicks the WAV format option, waits for file system verification, and renames the resulting file to your target filename specified in the CSV.
- **Pause & Resume Logging**: Tracks successfully generated runs inside a `completed_runs.csv` file, allowing you to stop and restart execution without duplicate generation or wasted credits.
- **Account Transition Mode**: Includes a `change_account` configuration flag to pause browser initialization when manual logout/login or profile switching is necessary.

---

## File Structure

Your project directory should look like this:

```text
minimax_tts_automation/
│
├── csv_data/                # Input directory containing target CSV files
│   ├── english.csv          # Sample input
│   └── completed_runs.csv   # Automatically generated state tracking file
│
├── tts_outputs/             # Destination directory where downloaded .wav files are saved
│
├── chrome_profile/          # Persistent local browser session profile folder
│
├── selectors.yaml           # Configuration file for selectors and paths
├── main.py                  # Core Python script
├── requirements.txt         # List of Python dependencies
└── README.md                # Project documentation
```

---

## Installation

1. Clone or copy the project files to your local working directory.
2. Install the required Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Ensure you have Google Chrome installed on your machine.

---

## Configuration (`selectors.yaml`)

The `selectors.yaml` file controls paths and UI selectors:

- `chrome_version`: Set this to your local Chrome browser's major version number (e.g., `148`, `149`).
- `change_account`: Set to `true` if you need the program to wait so you can manually log out and log in to a different account. Set to `false` for normal, unattended automated execution.

---

## CSV Input Format

Place your input `.csv` files inside the `csv_data` directory. The CSV file must use the following headers:

```csv
filename,transcription,speaker_id
LJ001-0014.wav,"This is a sample text for generation.",speaker_01
LJ001-0066.wav,"This is another text line.",speaker_01
```

---

## How to Use

### 1. First-Time Setup & Authentication
Because the controller utilizes a persistent user data profile, you only need to sign in once.

1. Ensure `change_account: false` is configured in `selectors.yaml`.
2. Run the script:
   ```bash
   python main.py
   ```
3. A browser window will open. If no active session is detected, the terminal will pause and prompt you:
   ```text
   Action Required: Please log in manually in the browser window.
   Once you are logged in, return to this terminal and press ENTER.
   ```
4. Log into your Google / MiniMax account in the Chrome window. Once completed, press `Enter` in the terminal.
5. The script will automatically save your login cookies inside the local `./chrome_profile` directory for future runs.

### 2. Switching Accounts
If you need to change your active account:
1. Open `selectors.yaml` and set `change_account: true`.
2. Run `main.py`. The script will open and wait.
3. In the browser, log out of your current account, log in to your new target account, and then press `Enter` in your terminal to start generation.
4. Set `change_account: false` back in the YAML for future runs.

### 3. Pause & Resume Capability
If your internet drops, the script crashes, or you manually interrupt it (`Ctrl+C`):
- All successfully completed audio files are saved inside the `tts_outputs` folder.
- Completed progress is logged in `csv_data/completed_runs.csv`.
- Upon restarting (`python main.py`), the script automatically reads the log, skips all completed filenames, and resumes processing where it was halted.

---

**Note**: Will be adding support to use pre-existing or functionality to clone voice. Or headless if needed.