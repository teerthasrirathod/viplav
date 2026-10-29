# Using VIPLAV on your phone or tablet

Your phone or tablet is only the screen and the microphone. The thinking happens on your computer, so the computer has to be on and running VIPLAV. It costs nothing: Tailscale's free plan is enough.

## Why a plain Wi-Fi address doesn't work

If you open `http://192.168.x.x:8765` on your phone, the page loads but the microphone is blocked. Browsers only allow the mic on `localhost` or on a secure (`https://`) address. [Tailscale](https://tailscale.com) gives your computer a secure address that only your own devices can open.

## One-time setup (about 15 minutes)

1. **On your computer.** Install Tailscale from https://tailscale.com/download and sign in. Make a free account if you don't have one.
2. **Turn on HTTPS.** Open the [DNS page](https://login.tailscale.com/admin/dns) of the Tailscale admin console. Make sure **MagicDNS** is on, then click **Enable HTTPS** under HTTPS Certificates.
   - This publishes your devices' names (for example your computer's name) in a public certificate log. If your computer's name has your real name in it, rename the computer first.
3. **On your phone and tablet.** Install the Tailscale app (Google Play or the App Store) and sign in with the **same account**.
4. **On your computer, share VIPLAV.** In PowerShell (Mac and Linux: Terminal):
   ```bash
   tailscale serve --bg --https=443 127.0.0.1:8765
   tailscale serve status
   ```
   The second command prints your address, which looks like `https://my-computer.my-tailnet.ts.net`.

## Every time

1. Start VIPLAV on your computer (`run.bat`, or `./run.sh`).
2. On your phone or tablet, make sure the Tailscale app is on, and open your address in **Chrome** (Android) or **Safari** (iPhone and iPad).
3. Allow the microphone, pick your language, and tap **Tap to talk**.

In the browser menu, **Add to Home Screen** puts VIPLAV on your phone like an app.

## Keeping it private

- `tailscale serve` shares VIPLAV only with devices signed in to your Tailscale account. Never use `tailscale funnel` for VIPLAV: that puts it on the public internet.
- For one more lock, set `VIPLAV_ACCESS_TOKEN=<a secret>` in `.env`, restart VIPLAV, and open your address with `?token=<a secret>` on the end.
- To stop sharing: `tailscale serve --https=443 off`.

## If something goes wrong

| What you see | What to do |
|---|---|
| The page won't load | Is your computer awake, VIPLAV running, and the Tailscale app on, on your phone? |
| A certificate warning | HTTPS isn't enabled yet (step 2), or you're using a different address from the one `tailscale serve status` printed |
| "Microphone access was blocked" | In the browser's site settings, allow the microphone for your address, then reload |
| "Access token missing or wrong" | Add `?token=<your secret>` to the address |
| Speech recognition doesn't work | Use Chrome on Android or Safari on iPhone and iPad. Firefox can't do it |
| It hears itself | Use headphones |
