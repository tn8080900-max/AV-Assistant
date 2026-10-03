# AV Assistant

A Windows-first, voice-controlled personal agent with a loopback-only local companion, allowlisted computer tools, and explicit approval for consequential actions.

## Run & Operate

- `pnpm --filter @workspace/api-server run dev` — run the API server (port 5000)
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- `pnpm --filter @workspace/av-assistant run typecheck` — check the AV Assistant UI
- `python -m unittest discover -s tests -v` — run the local tool safety tests
- Windows launch: run `start.bat`; it installs dependencies, builds the UI, then starts the companion at `127.0.0.1:8765`
- Local settings: copy `.env.example` to `.env`; never commit `.env`

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- Windows companion: Python 3.11+, FastAPI, OpenAI SDK, ElevenLabs HTTP adapter
- API: Express 5
- DB: PostgreSQL + Drizzle ORM
- Validation: Zod (`zod/v4`), `drizzle-zod`
- API codegen: Orval (from OpenAPI spec)
- Build: esbuild (CJS bundle)

## Where things live

- `artifacts/av-assistant/` — React/Vite interface and local API client
- `backend/agent/` — function-calling loop, explicit states, prompt, and session-only memory
- `backend/tools/` — allowlisted Windows tools, calculator, time, browser, and filename search
- `backend/permissions/` — safe automatic execution vs. approval-required actions
- `backend/voice/` — replaceable speech-provider interfaces and ElevenLabs adapter
- `backend/main.py` — local-only FastAPI endpoints and static UI host
- `.env.example`, `requirements.txt`, `start.bat`, `README.md` — local setup and operation
- `tests/test_tools.py` — calculator, file-boundary, URL, and permission tests

## Architecture decisions

- Windows actions run only in the local FastAPI companion bound to `127.0.0.1`; do not route computer-control requests through the hosted Express service.
- Every action must use a registered tool with validated parameters; never turn model text into a shell command.
- File tools operate only inside user-configured directories, search filenames only, and exclude hidden/system/credential-like paths.
- Destructive file deletion is registered but cannot execute until the user approves the exact pending request.
- Session chat memory is in RAM and clears when the session is cleared or the companion stops. Provider keys stay in the local `.env`.

## Product

Voice and text requests, editable speech transcription, structured AI tool use, Windows-local tools, confirmation prompts, speech playback, and local permissions settings.

## User preferences

- Target Windows 10/11 and keep the Python agent modular so voice and AI providers can be replaced.
- Do not add unrestricted computer access or permanent personal memory.

## Gotchas

- The Replit browser preview has no access to the user's Windows machine. A disconnected preview must say that the local companion is offline.
- After UI edits, rebuild with `PORT=8765 BASE_PATH=/ pnpm --filter @workspace/av-assistant run build` before checking the local FastAPI static host.
- Keep the Windows server bound to loopback; do not change its host to `0.0.0.0`.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
