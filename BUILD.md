# Building a portable Windows distribution

End users do **not** need Python and do **not** need to type commands. They only double-click the program.

## For you (who builds the installer folder)

1. Install **Python 3.10+** (64-bit) from [python.org](https://www.python.org/downloads/) if you do not already have it.
2. In File Explorer, open the project folder (`QC Software`).
3. **Double-click `Build portable app.bat`.**  
   Wait until the window says the build finished. It opens the output folder when successful.

**Corporate proxy / firewall:** copy `proxy_local.bat.example` to `proxy_local.bat`, edit it with your proxy URLs (do not commit `proxy_local.bat`). The build script runs it automatically if that file exists.

Output:

- `dist\AI_QC_Document_Reviewer\` — **zip this entire folder** and share it (or copy it to a USB drive).

## For end users (no terminal, no Python)

1. Unzip the folder anywhere.
2. Double-click **`AI_QC_Document_Reviewer.exe`**  
   **or** double-click **`Start AI QC Reviewer.bat`** (same folder — optional shortcut-style launcher).
3. On first run the app creates a `data` folder **next to the executable** for settings and saved data.

## Optional: command-line build (same result as the .bat)

If you prefer PowerShell:

```powershell
cd "path\to\QC Software"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-build.txt
pyinstaller ai_qc_reviewer.spec --clean
```

## Run from source (developers)

Double-click **`Run QC Reviewer.bat`** (uses `.venv` if present, otherwise your system Python).

## Notes

- **API keys:** copy `data\config.json.example` to `data\config.json` and fill in your API settings locally. `data\config.json` is gitignored so secrets are not committed.
- **Size:** the `dist` folder is often tens to low hundreds of MB uncompressed.
- **Antivirus:** PyInstaller executables are occasionally flagged; code signing (Authenticode) is optional.
- **Network:** the app needs outbound HTTPS to your configured API.
- **Updating dependencies:** edit `requirements.txt`, then double-click **`Build portable app.bat`** again.
