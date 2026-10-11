# HADAL

HADAL is a Windows desktop assistant for web research and local file organization. It uses TinyFish Research for cited answers. Local file actions work on folders you select and do not send their filenames or contents to TinyFish.

## Configure TinyFish on Windows

Create an API key at [agent.tinyfish.ai/api-keys](https://agent.tinyfish.ai/api-keys). Keep it private and never commit it. Create a `.env` file beside `file_assistant.py` and add:

```env
TINYFISH_API_KEY=your_tinyfish_key_here
```

Start HADAL:

```powershell
py .\file_assistant.py
```

HADAL uses TinyFish's Research API in instant mode. Research questions are sent to TinyFish; service availability and account limits may apply. Install `python-dotenv` so HADAL can load the `.env` file. Alternatively, set `TINYFISH_API_KEY` in the process environment. If HADAL is packaged as a one-file executable, place `.env` beside the executable.

Research replies are prompted to start with the direct answer or a short summary, followed by a brief explanation. The assistant identifies itself as HADAL and hides the source list unless asked. HADAL uses TinyFish instant mode and displays streamed answer text as it arrives; the total research time still depends on TinyFish.

```powershell
py -m pip install python-dotenv
```

## Local file actions

Use the quick-action buttons or enter one of these commands:

- `List files in folder 1`
- `Search filenames for report`
- `Preview organization for folder 1`
- `Apply the previewed organization`

File actions run locally. HADAL does not read file contents. Organizing files requires a separate confirmation, never overwrites files, and only considers files directly inside the selected folder.

## Run tests

```powershell
py -m unittest discover -s tests -v
```
