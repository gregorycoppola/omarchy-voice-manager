# Website routing and browser resolution

This is the policy for a request such as “open GitHub.” It separates choosing a
browser from choosing a tab. A browser must never be selected silently when
there is a meaningful choice.

## Terms

- A **supported browser** has a local Skipper adapter that can safely enumerate
  and activate its normal tabs.
- A **normal window** is not private/incognito and is not an extension-control
  or standalone web-app window.
- The **default browser** is the browser configured for new website requests.
  The current implementation's default is Chromium.

## Selection order

1. An explicitly named browser wins. “Open GitHub in Firefox” targets Firefox;
   it does not reuse a GitHub tab in Chromium.
2. Without a named browser, look for the requested registered website in all
   supported normal browsers. If exactly one browser has a matching tab, use
   that browser and activate its best matching tab.
3. If the website is already open in more than one supported browser, ask
   **“Which browser do you want to use for GitHub?”** Show the browser name and
   a short window/tab label for each choice.
4. If the website is not already open, use the one supported normal browser
   window when exactly one exists.
5. If several supported normal browsers/windows exist and no browser was named,
   ask **“Which browser?”** Do not choose based only on recency or focus.
6. If none is open, launch the configured default browser and open the site in
   a normal tab.

Once a browser has been selected, reuse a matching HTTPS tab without reloading.
When that browser has duplicate matching tabs, prefer the focused browser
window, then its most recently accessed matching tab. If it has no matching
tab, create a new tab in the selected normal window.

Opening or activating a website is navigation only. It must preserve the chosen
browser window's workspace, size, fullscreen state, and tiling. If no browser
exists, launch the selected/default browser without imposing a layout; the
compositor decides whether the new window joins the current tile layout or
opens independently. Fullscreen and tiling are explicit, separate commands.

## Spoken forms

- `open GitHub` follows the selection order above.
- `open another GitHub tab` and `open a new GitHub tab` skip matching-tab reuse
  and create a new tab in the selected browser.
- `open GitHub in Chromium` / `open GitHub in Firefox` chooses that browser
  explicitly.
- A clarification is part of the command flow, not a failure. The selected
  browser is frozen with the recording context and checked again before a tab
  is opened or activated.

## Current implementation boundary

Skipper currently has a **Chromium-only** Playwright-extension adapter. It
already reuses an existing registered-site tab, otherwise opens a new tab in an
existing normal Chromium window, otherwise opens Chromium. It cannot yet
enumerate or control Firefox, Brave, or another browser's tabs, and it has no
`open <site> in <browser>` grammar or browser-choice UI for website requests.

The policy above is therefore the implementation target, not a claim that every
browser works today. Adding another browser requires its own local adapter and
the same privacy rules; it must not fall back to scraping tabs from an
unsupported browser.


## Explicit website picker destinations

The root picker now offers new-browser and existing-browser commands. The latter
selects the captured focused Chrome/Chromium window, the sole supported browser,
or asks which supported window to use. It opens arbitrary validated HTTP(S) URLs
as new tabs through the extension, with native identity and extension-window
checks. This is separate from the older fixed-site reuse rules above; other
browser families remain unsupported for existing-window targeting.
