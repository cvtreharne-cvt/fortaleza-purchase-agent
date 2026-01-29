# Node Playwright Worker Service

Implemented the Node browser worker and wired Python to use it when configured.

# Background

Running the agent on Google Cloud Run didn’t work. It was getting blocked somehow by Bitters & Bottles (B\&B) website. The working theory is the site must have some kind of bot detection that thwarts the purchase agent from being able to navigate, etc.. To work around this limitation and to ensure an “always on” server, I searched for an alternative leveraging a Raspberry Pi option. The hurdle with that option is, unfortunately, a version of Playwright for Bookworm OS (OS for Raspberry Pi 5 \- 64 bit, ARM64 architecture \- beefy enough to run the agent) is not available. However, a Node version of Playwright **\*is\*** available.  The following is a description of the implementation strategy.

# High Level Approach

Keep your Python agent/orchestration as-is, but move the Playwright/browser work into a small Node HTTP “browser worker” that runs on the Pi and uses system Chromium. The Python tools call the worker over localhost HTTP instead of using the Python Playwright library (which isn’t  available on Pi). 

## Steps

1. On the Pi, create browser-worker/ (inside your feat/js-playwright-worker branch).  
2. Install system Chromium via apt (chromium-browser or chromium).  
3. Add a minimal Node app (server.js) that:  
   1. Launches Playwright’s chromium with executablePath pointing at system Chromium (/usr/bin/chromium-browser), headless=true, and \--no-sandbox.  
   2. Exposes HTTP endpoints: /health, /reset, /navigate, /verify-age, /login, /add-to-cart, /checkout (mirroring your Python tool behaviors).  
   3. Each returns a JSON {status, message?, current\_url?}.  
4. browser-worker/package.json depends on express and playwright. Install with PLAYWRIGHT\_SKIP\_BROWSER\_DOWNLOAD=1 npm install (to skip bundled browser).  
5. Start the worker: HEADLESS=true CHROME\_PATH=/usr/bin/chromium-browser npm start (or supervise via systemd). It listens on PORT (default 3001).  
6. In Python, add a shim (src/core/browser\_service.py) that does simple requests GET/POST to BROWSER\_WORKER\_URL (default http://localhost:3001).  
7. Replace your direct Playwright calls in navigate/login/add\_to\_cart/checkout/verify\_age with HTTP calls to the worker endpoints, preserving the same return shapes so your agent flow stays intact.

**Net**: the Pi runs a local Node Playwright service driving system Chromium; Python calls it over localhost, avoiding the unsupported Python Playwright on arm64.

**Notes**  
You still keep your FastAPI/uvicorn server for the webhook and agent orchestration. The Express server is an additional local “browser worker” sidecar that only handles Playwright actions. Your Python code calls that worker over localhost; everything else (FastAPI routes, ADK agent, notifications) stays in Python. So you’ll run both: FastAPI \+ the small Express worker.

What is a sidecar?

A sidecar is just a companion process that runs alongside your main service to handle a specific concern. It isn’t user-facing; your main app calls it locally. In this case, the Express browser worker is a sidecar to your FastAPI app: FastAPI handles webhooks/agent logic, and it calls the local worker to drive the browser.

# What changed

* Added **browser-worker/server.js**: Express/Playwright service with endpoints   
  * /health  
  *  /reset  
  * /navigate (direct-link with search fallback)  
  * /verify-age  
  * /login  
  * /add-to-cart  
  * /checkout   
  * using system Chromium (CHROME\_PATH, headless by default)  
* Updated browser-worker/package.json: **express \+ playwright deps**, start script, private package, main server.js.  
* New **Python shim src/core/browser\_service.py** to call the worker over HTTP and map worker errors to existing exceptions.  
* **Config**: added browser\_worker\_url and browser\_worker\_timeout.  
* Browser lifecycle: managed\_browser no-ops when a worker URL is set.  
* Tool refactors: navigate, verify\_age, login, cart, checkout now delegate to the worker when enabled; existing Playwright flows remain for local mode.  
* **Agent wiring: tools detect worker mode** and route calls appropriately without dropping search fallback.

# Node Playwright Browser Service Mode

The switch is driven by config: if BROWSER\_WORKER\_URL (maps to settings.browser\_worker\_url) is set, browser\_service.is\_enabled() returns true. In that case:

* managed\_browser becomes a no-op (no Python Playwright start/stop).  
* Each tool (navigate, verify\_age, login, add\_to\_cart, checkout) routes calls over HTTP to the Node worker and doesn’t touch Python Playwright.  
* Agent tool wrappers check use\_worker from browser\_service.is\_enabled() and call the worker-backed tool paths.

If BROWSER\_WORKER\_URL is unset/empty, the agent uses the existing Python Playwright path as before. So: set BROWSER\_WORKER\_URL=http://localhost:3001 to force Node worker mode; leave it unset to use Python Playwright.

The check is centralized in browser\_service.is\_enabled(), which returns true when settings.browser\_worker\_url is set.

Key spots:

* Config reads browser\_worker\_url from env: src/core/config.py:48 (env var BROWSER\_WORKER\_URL via pydantic settings).  
* Worker detection: src/core/browser\_service.py:21-25 (return bool(settings.browser\_worker\_url)).  
* Lifecycle skip: src/core/browser.py:159-163 — managed\_browser no-ops if settings.browser\_worker\_url is set.  
* Tool routing: each tool checks browser\_service.is\_enabled() and calls the worker endpoints instead of Python Playwright.  Examples:   
  * navigation src/tools/[navigate.py:52](http://navigate.py:52)\-67  
  * verify age src/tools/verify\_age.py:18-25  
  * login src/tools/[login.py:20](http://login.py:20)\-29  
  * cart src/tools/cart.py:18-26, checkout src/tools/checkout.py:23-34  
* Agent wrappers also branch on use\_worker \= browser\_service.is\_enabled() (e.g., agents/fortaleza\_agent/agent.py:103-214)

# How to use

1. On the Pi (with system Chromium):  
   1. cd browser-worker  
   2. PLAYWRIGHT\_SKIP\_BROWSER\_DOWNLOAD=1 npm install  
   3. CHROME\_PATH=/usr/bin/chromium-browser HEADLESS=true PORT=3001 npm start  
2. In Python env, set BROWSER\_WORKER\_URL=http://localhost:3001 (or your host:port).  
   1. Other env stays the same; tools will auto-switch to worker mode.

# Next steps

* Run the worker on the Pi and test curl against /health and /navigate.  
* In Python, run a dryrun (MODE=dryrun) to validate end-to-end with the worker.  
* If needed, tighten selectors/flows in server.js based on real site behavior.

Start the Node Browser Worker sidecar:  
% export CHROME\_PATH=”/Users/mceciliatreharne/Library/Caches/ms-playwright/chromium-1200/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing”

\<project-root.//browser-worker % npm start

\# Setting BROWSER\_WORKER tells the agent to use the Node browser worker sidecar service to execute all the browser actions using Playwright as the automation platform

export BROWSER\_WORKER\_URL=[http://localhost:3001](http://localhost:3001)

\# Copy & paste the following in a terminal window after setting above env vars and starting the Node Playwright browser sidecar service

PYTHONPATH=. python \- \<\<'PY'  
import asyncio  
from src.core import browser\_service

async def main():  
    result \= await browser\_service.navigate(  
        direct\_link="https://www.bittersandbottles.com/products/fortaleza-blanco-tequila",  
        product\_name="Fortaleza",  
        dob=None,  
    )  
    print(result)

asyncio.run(main())  
PY

