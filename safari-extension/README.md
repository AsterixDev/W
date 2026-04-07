# Safari Enhancer — Extension

Three features, one toolbar button:

- **Dark Mode** — flips any website dark. Sites that already support dark mode use their own colours (no distortion). Sites that don't get an invert+hue-rotate treatment with images/videos kept natural.
- **Toolbar Colour** — pick a colour from the swatches or enter any hex value. Safari's address bar area changes to match.
- **Volume Boost** — amplify audio above 100%, up to 1000%. Works on YouTube, Spotify, podcasts — anything playing audio or video on the page.

---

## Build & install (one-time, ~5 minutes)

**You need:** macOS 12+, Xcode 14+, Safari 15+

### Step 1 — Generate the Xcode project

Open Terminal, `cd` to the repo root, then run:

```bash
xcrun safari-web-extension-converter safari-extension/ \
  --app-name "Safari Enhancer" \
  --bundle-identifier "com.$(whoami).safari-enhancer" \
  --swift \
  --force
```

This creates a folder called `Safari Enhancer/` containing an Xcode project. You only need to do this once (or after editing source files).

### Step 2 — Build in Xcode

```
open "Safari Enhancer/Safari Enhancer.xcodeproj"
```

1. In the scheme selector (top bar), pick **Safari Enhancer (macOS)** as the target
2. Press **Cmd + R** to build and run
3. A tiny helper app opens — you can quit it immediately

### Step 3 — Enable in Safari

1. **Safari → Settings → Extensions** (or Cmd + ,  then Extensions tab)
2. Tick **Safari Enhancer**
3. In the permissions sheet, choose **Allow on All Websites**

> **First time only:** Safari may ask you to allow unsigned extensions.
> Go to **Develop → Allow Unsigned Extensions** (enable the Develop menu first via
> Safari → Settings → Advanced → "Show Develop menu").
> You'll need to re-tick this after each Mac restart until you sign the extension.

The toolbar button (purple square) now appears next to the address bar. Click it.

---

## Updating source files

After editing any `.js`, `.html`, or `.css` file in `safari-extension/`:

```bash
# Re-run the converter to sync changes into the Xcode project
xcrun safari-web-extension-converter safari-extension/ \
  --app-name "Safari Enhancer" \
  --bundle-identifier "com.$(whoami).safari-enhancer" \
  --swift \
  --force

# Then rebuild in Xcode (Cmd+R) and reload Safari's extension
```

---

## How each feature works

### Dark Mode
- Checks if the page has a light background (luminance > 50%)
- If the site already supports `prefers-color-scheme: dark`, sets `colorScheme = 'dark'` — uses the site's own dark palette, zero visual glitches
- Otherwise injects CSS: page gets `filter: invert(0.9) hue-rotate(180deg)`, then images/video get counter-inverted so they look natural

### Toolbar Colour
- Injects or updates `<meta name="theme-color">` on the active page
- Safari reads this tag and colours its chrome (address bar, tab bar) accordingly
- Setting stored per-session; cleared with the ×  swatch

### Volume Boost
- Creates a Web Audio API `GainNode` in the page's own JS context (via an injected script) — this is required to intercept media created by the page's scripts (e.g. YouTube's player)
- A `MutationObserver` hooks any `<audio>` or `<video>` element added after page load
- Gain value: `1.0` = 100%, `10.0` = 1000%
- Above 500% a warning is shown in the popup — distortion is expected at extreme values

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Toolbar button doesn't appear | Rebuild in Xcode (Cmd+R), then disable/re-enable the extension in Safari Settings |
| Dark mode flashes white briefly | Normal on very slow pages — content script runs at `document_start` but painting can still happen before CSS applies |
| Volume boost has no effect | Some sites (e.g. Twitch) use Web Workers or custom audio pipelines that bypass the standard `<video>` element. Boost won't work there. |
| Toolbar colour doesn't change | Some sites set their own `theme-color` after page load and override ours. Reload the page with the extension active. |
| "Allow Unsigned Extensions" resets after restart | Expected behaviour until the extension is signed with an Apple Developer account. Just re-tick it in Develop menu. |
