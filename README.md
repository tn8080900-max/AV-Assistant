# AV Assistant

AV Assistant is a voice-controlled personal agent for Windows 10 and 11. You speak or type a request, review the recognized words, and the AI can use a small set of tools on your computer. The app shows every tool action. Deleting a file always stops for your approval.

## How the parts work

The browser page records speech and displays the conversation. A small FastAPI service runs on your Windows computer at `127.0.0.1` and performs permitted actions locally. It is not an internet-facing server.

For the first version:

- OpenAI handles the agent's reasoning and structured tool calls.
- ElevenLabs handles speech recognition and spoken replies.
- The API adapters are separate from the agent so they can be replaced.
- Conversation history is held in memory until you stop the local service or clear the session. It is not saved to a permanent memory store.
- Provider credentials stay in your local `.env` file. They are never sent to the browser interface or written to app logs.

The Replit preview is the interface. Computer-control tools only work when the companion is running on the Windows computer you want to control.

## What you need

Install these programs on the Windows computer:

1. Windows 10 or 11.
2. Python 3.11 or newer, with **Add Python to PATH** enabled in the installer.
3. Node.js 22 or newer.
4. pnpm. After Node.js is installed, open a new Command Prompt and run:

   ```bat
   npm install --global pnpm
   ```

5. An OpenAI API key for the agent, and an ElevenLabs API key and voice ID for voice features. Provider usage may be billed by those providers.

## Install and start

1. Download or copy the **whole AV Assistant project**, then extract it into a folder on your computer. Keep the `artifacts`, `backend`, `lib`, and `scripts` folders together.
2. Open that folder in File Explorer.
3. Double-click `start.bat`.
4. The first run creates a Python environment and installs the required packages. It also builds the browser interface.
5. If this is the first run, a local `.env` file is created from `.env.example` and opened in Notepad. Add your own provider settings, save the file, close Notepad, and run `start.bat` again.
6. AV Assistant opens at `http://127.0.0.1:8765`. Keep the Command Prompt window open while using the app.

The setup script requires internet access to install packages the first time. Later runs reuse the installed Python environment and Node packages.

If the Python dependencies change, reopen Command Prompt in the project folder and run:

```bat
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
```

## Configure API keys

Open `.env` in Notepad. Replace the example values:

```text
OPENAI_API_KEY=your-OpenAI-key
OPENAI_MODEL=gpt-5.4-mini

ELEVENLABS_API_KEY=your-ElevenLabs-key
ELEVENLABS_VOICE_ID=your-ElevenLabs-voice-id
ELEVENLABS_STT_MODEL_ID=scribe_v1
ELEVENLABS_TTS_MODEL_ID=eleven_multilingual_v2
```

Save `.env` and restart the app so it reads the new settings. The `.env` file is ignored by Git. Do not share it or paste it into chat.

`OPENAI_MODEL` can be changed to another model available to your OpenAI account. Keep API-key values out of source files and screenshots.

## Microphone and voice

Use an up-to-date version of Microsoft Edge or Google Chrome. The first time you press the microphone button, allow microphone access for `127.0.0.1`. The app shows when it is listening and when it is transcribing.

After transcription, the recognized words appear in an editable field. Correct them if necessary, then send the request. The assistant displays its answer and requests audio from ElevenLabs for playback. If speech recognition or audio playback is not configured, the app reports the problem and text entry still works.

## Tools and permissions

The AI may choose from these registered tools:

| Tool | What it does | Permission |
| --- | --- | --- |
| Current time | Reads the Windows computer's local time | Runs automatically |
| Calculator | Evaluates basic arithmetic without asking the language model to calculate | Runs automatically |
| Open website | Opens an `http` or `https` page in your default browser | Runs automatically |
| Open application | Starts Notepad, Calculator, or Paint from a fixed allowlist | Runs automatically |
| Search files | Searches filenames only inside folders you configured | Runs automatically |
| Delete file | Deletes a single regular file inside a configured folder | Waits for ALLOW or DENY |

The app never turns a model response into a shell command. Application launch uses fixed executable names; file operations check the configured folders again when they run. File search skips hidden files, common credential filenames, Windows/system directories, and symbolic links. It does not open or read file contents.

Use **Permissions & settings** to add or remove search folders and permitted applications. Only existing folders are accepted. The permitted app names are `notepad`, `calculator`, and `paint`. Settings are stored locally in `data/settings.json` and do not contain API keys.

You can also set defaults in `.env` before starting the app:

```text
AV_ALLOWED_DIRECTORIES=C:\Users\YourName\Documents;C:\Users\YourName\Desktop
AV_ALLOWED_APPLICATIONS=notepad,calculator
```

If you change settings in the interface, the saved local settings file takes precedence over the corresponding `.env` values.

## Project map

```text
artifacts/av-assistant/  Browser interface (React and Vite)
backend/                 Local FastAPI server and agent loop
backend/agent/           Tool selection, state, instructions, and session memory
backend/tools/           Registered calculator, time, browser, app, and file tools
backend/permissions/     SAFE vs. confirmation-required permission rules
backend/voice/           Replaceable speech provider interface and ElevenLabs adapter
.env.example             Safe configuration template (no real credentials)
requirements.txt         Python dependencies
start.bat                Windows setup and launcher
```

## Run without the Windows launcher

From the project folder, open Command Prompt:

```bat
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
npm install --global pnpm
pnpm install
set PORT=8765
set BASE_PATH=/
pnpm --filter @workspace/av-assistant run build
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
```

Then open `http://127.0.0.1:8765`. Stop the service with **Ctrl+C** in Command Prompt.

For frontend development, run the API service above in one Command Prompt, then in a second window run:

```bat
set PORT=5173
set BASE_PATH=/
pnpm --filter @workspace/av-assistant run dev
```

Open `http://127.0.0.1:5173`. In development, Vite forwards `/agent-api` requests to the local FastAPI service.

## Add a tool

1. Create a function for the action. Validate every argument inside that function.
2. Register a `Tool` in `backend/tools/registry.py` with a name, description, JSON parameters, handler, and permission level.
3. Choose `SAFE` only when the action cannot make a consequential change. Use `REQUIRES_CONFIRMATION` for deletes, sends, purchases, system changes, or external-device actions.
4. Keep operating-system operations narrow and parameterized. Never add a shell tool or pass AI text to a command prompt.
5. Add a test and update the table above.

The approval manager runs a confirmation-required handler only after the interface sends the user's explicit approval.

## Troubleshooting

- **“Python was not found”**: Reinstall Python 3.11+ with **Add Python to PATH** selected; reopen Command Prompt and run `python --version`.
- **“Node.js was not found”**: Install Node.js 22+, reopen Command Prompt, and check `node --version`.
- **“pnpm was not found”**: Run `npm install --global pnpm`, then reopen Command Prompt.
- **The assistant says a provider is not configured**: Check the key names and values in `.env`, save the file, and restart `start.bat`. Do not include quote marks around the values.
- **Microphone access is blocked**: Use Edge or Chrome, select the site icon beside the address, allow Microphone access for `127.0.0.1`, then reload the page.
- **Speech recognition or playback fails**: Check the ElevenLabs key, voice ID, internet connection, and provider account limits. Text entry can still be used.
- **A tool is unavailable**: Confirm the requested app is in Settings, or configure an existing folder before searching it. Windows application launch does not work on non-Windows computers.
- **Port 8765 is already in use**: Close the other AV Assistant window, or stop the process listening on that port before starting again.

## Privacy and local-only access

The server binds to `127.0.0.1`, not to your network interface. AI requests go to the configured model provider; speech recordings go to ElevenLabs. The service logs request text after masking common key/token patterns, selected tool names, and outcomes. API credentials are not logged. Local `.env` values are not returned by the settings or health endpoints.