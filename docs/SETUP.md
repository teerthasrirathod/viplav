# Setting up VIPLAV

About 15 minutes the first time, and one command after that. Nothing here costs money beyond your Claude plan.

## What you need

- **A computer:** Mac (macOS 13 or newer), Windows 10/11, or Linux. Any ordinary laptop works with the default settings.
- **A Claude Pro or Max plan.** Claude Code isn't included in the free plan.
- **Google Chrome** (or Edge or Safari). Firefox can't do speech recognition.
- **Headphones**, recommended, so VIPLAV doesn't hear itself.

## 1. Get the files

Download `viplav.zip` and unzip it somewhere easy, for example into your Documents folder. You'll get a folder called `viplav`. (Once it's on GitHub: `git clone https://github.com/<you>/viplav`.)

## 2. Install Python (3.10 or newer)

- **Mac:** download the macOS installer from https://www.python.org/downloads/ and run it. To check, open **Terminal** (press Cmd+Space, type "Terminal") and run `python3 --version`. It should say 3.10 or higher.
- **Windows:** download the installer from https://www.python.org/downloads/. On its first screen, tick **"Add python.exe to PATH"**. To check, open **PowerShell** and run `py --version`.

## 3. Install Claude Code and sign in

This is what lets VIPLAV use your Claude plan instead of a paid API key.

- **Mac or Linux.** In Terminal, run:
  ```bash
  curl -fsSL https://claude.ai/install.sh | bash
  ```
- **Windows.** In PowerShell, run:
  ```powershell
  irm https://claude.ai/install.ps1 | iex
  ```

Then **open a new** Terminal or PowerShell window, so it can find the new program, and run:

```bash
claude
```

A browser window opens. Sign in with the Claude account that has your plan. Back in the terminal, type `/exit`. You only do this once.

If `claude` says "command not found", see https://code.claude.com/docs/en/troubleshoot-install.

## 4. Start VIPLAV

- **Mac or Linux.** In Terminal:
  ```bash
  cd ~/Documents/viplav      # or wherever you unzipped it
  bash run.sh
  ```
- **Windows.** Open the `viplav` folder and double-click **`run.bat`**.

The first start installs VIPLAV, which takes a few minutes. When you see `Open http://127.0.0.1:8765`, it's ready. Leave that window open while you use VIPLAV.

## 5. Talk

1. Open **Chrome** and go to **http://127.0.0.1:8765**.
2. Pick the language you'll speak (bottom of the page).
3. Click **Tap to talk** (or press Space), allow the microphone, and start talking.
4. Click **Board** to see your threads, and **Transcript** to read along.

To stop VIPLAV, press **Ctrl+C** in the Terminal window, or close the `run.bat` window. Next time, steps 4 and 5 are all you need.

## Talk to it from your tablet or phone (with Tailscale)

VIPLAV runs on your computer, and you can talk to it from a tablet or phone anywhere, privately, over [Tailscale](https://tailscale.com) (free for personal use). Only your own devices can reach it.

1. Install Tailscale on the computer and the tablet, signed in to the same account. Both should show as connected.
2. Turn on HTTPS for your Tailscale network, once: in the Tailscale admin console (https://login.tailscale.com/admin/dns), enable **MagicDNS** and **HTTPS Certificates**. Browsers only allow the microphone on HTTPS pages.
3. Start VIPLAV on the computer as usual (`run.bat` or `bash run.sh`).
4. On the computer, open a second PowerShell or Terminal window and run:
   ```
   tailscale serve --bg 8765
   ```
   It prints an address like `https://your-pc.your-tailnet.ts.net`.
5. On the tablet, open that address in Chrome. Allow the microphone, and talk.

This keeps VIPLAV listening only on the computer itself (`127.0.0.1`). Tailscale passes your devices' connections through, so nothing is exposed to the internet. To stop sharing, run `tailscale serve --https=443 off`.

## Make it yours (optional)

Open the `.env` file in the `viplav` folder with any text editor:

- `VIPLAV_USER_NAME=Teertha`: what VIPLAV calls you
- `VIPLAV_LANGUAGES=en,hi,te,lmn`: your languages
- `VIPLAV_EFFORT=low`: snappier answers, and your plan's limits last longer

Copy `data/profile.example.md` to `data/profile.md` and write a few lines about yourself. VIPLAV reads it at the start of every conversation.

## If something goes wrong

| What you see | What to do |
|---|---|
| "Claude Code isn't signed in" | Run `claude` once in a terminal and sign in (step 3) |
| "Claude Code … isn't installed" | Do step 3, then open a **new** terminal window |
| "usage limit is reached" | Your plan's limit for now. It resets after a while; nothing is charged |
| "Microphone access was blocked" | Click the camera/mic icon in Chrome's address bar → Allow, then reload |
| It keeps interrupting itself | Use headphones, or turn off **Interrupt by voice** |
| It mishears you | Pick the right language at the bottom. Speak a little slower |
| `permission denied: ./run.sh` | Run `bash run.sh` instead |
| `python3: command not found` | Install Python (step 2) |

## Later: better free voices (when you have a Mac or a stronger computer)

In `.env`, set `VIPLAV_TTS=kokoro,mms` (natural local voices for English, Hindi and Telugu) and `VIPLAV_STT=whisper` (local listening that works out the language). `run.sh` installs them on the next start, and they download once, about 2 GB in total. See the README for details.
