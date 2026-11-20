# Assistant proxy (Cloudflare Worker)

Connects the GIS website's **Ask the data** chatbot to Claude for every visitor, without putting the Anthropic API key in
the website. The key is stored only as a secret in Cloudflare. Without the proxy, the chatbot still answers with its
built-in engine (totals, counts, averages, shares, rankings, comparisons, filters).

## One-time setup (about 15 minutes)

1. **API key.** At [console.anthropic.com](https://console.anthropic.com) (IOM account): *API keys → Create key*.
   Then *Settings → Limits*: set a monthly spend limit.
2. **Cloudflare account.** Sign up free at [dash.cloudflare.com](https://dash.cloudflare.com/sign-up).
3. **Create the worker.** *Workers & Pages → Create application → Start with Hello World*, name it
   `dtm-gis-assistant`, press **Deploy**.
4. **Paste the code.** Open the worker, press **Edit code**, replace everything with the contents of `worker.js`
   (this folder), press **Deploy**.
5. **Settings.** Worker → *Settings → Variables and Secrets → Add*:

   | Type | Name | Value |
   | --- | --- | --- |
   | Secret | `ANTHROPIC_API_KEY` | the key from step 1 |
   | Secret | `ACCESS_TOKEN` | a long random phrase you make up (e.g. 6 random words) |
   | Text | `ALLOWED_ORIGINS` | `https://cjanuare-ship-it.github.io` |

   Optional: `MODELS` (default `claude-sonnet-5-5,claude-haiku-5-5`), `MAX_TOKENS` (default 2000),
   `DAILY_LIMIT` (questions per visitor per day, default 300). Press **Deploy**.
6. **Copy the address** shown on the worker page, e.g. `https://dtm-gis-assistant.<your-account>.workers.dev`.
7. **Connect the site.** Open the GIS site → *Technician* → **Ask the data** → ⚙ (settings) → paste the address and
   the access token → **Test connection** → **Save** → **Publish**. Viewers now get Claude answers automatically.

## What it protects

- The API key never reaches browsers.
- Only the website's address may call the proxy, and only with the access token (stored inside the
  password-protected site).
- Model and answer length are capped; each visitor has a daily limit; set the spend limit in the Anthropic console.

To stop the connection: remove the address in the site settings and publish, or delete/rotate the key or token.
`node test_worker.mjs` runs the proxy's checks locally with a fake Anthropic API.
