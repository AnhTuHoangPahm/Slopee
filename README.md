# Slopee

A (vibe-coded) **Shopee** clone.

## What is Shopee?
[Shopee](https://shopee.com/) is an e-commerce online shopping platform.

## Why call this Slopee?
The name is the combination of **Slop** and **Shopee** (Shout out to the word **Microslop** for inspiration):
- The entire code production is AI, so I call it **Slop**.
- It is a cheap(?) clone of **Shopee**. (I used up my tokens, so calling it _'cheap'_ is kind of ... unfair?)

## Tech stack
- Frontend: Node.js React, Vite, Vanilla CSS
- Backend: Flask (Python)
- Database: MySQL
- Google Antigravity(?)

## Set up
I don't think I should tell (I'm just stup-d), but just in case:  
**First**, install dependencies:
```shell
cd frontend
npm install
cd ../backend
pip install -r requirements.txt  
```
**Set up**:
- Edit environment variables of your computer, add a global entry:  
```
DB_PASSWORD: your_databse_password
```
- Backend env: copy `backend/.env.example` to `backend/.env` and set a random `SECRET_KEY`
  (the app refuses to start without it unless `SLOPEE_ENV=development`).
- Database creation:  
```shell
python init_db.py
```
- **Existing database** (created before the migration runner existed): apply pending schema changes with  
```shell
cd backend
python migrate.py          # or: flask --app app migrate   (use `status` to list)
```
  This is required: login and checkout need the `authAttempts` table. There is no HTTP migration endpoint anymore.
- Create the admin account (there is no default admin anymore):  
```shell
cd backend
flask --app app seed-admin
```

**Then** (each line run in separate shells):
```shell
cd frontend && npm run dev
cd backend && python app.py
```
`debug` mode (and the dev `SECRET_KEY` fallback) is only enabled when `SLOPEE_ENV=development`; leave it unset in production.
Wrong password / PIN is limited to `AUTH_MAX_ATTEMPTS` (default 5) tries, then locked for `AUTH_LOCK_SECONDS` (default 900).
  
Use your favourite browser to access the page.  
 > Enjoy your stay

## Web3 (escrow demo, local only)

Requires [Foundry](https://book.getfoundry.sh/getting-started/installation) (`foundryup`), Python 3.12 and Node 22. Everything runs on a local Anvil chain (chainId 31337) with test keys; there is no real money.

```bash
./scripts/bootstrap.sh        # Anvil (--block-time 2) + deploy MockUSD/SlopeeEscrowMaster + deployments/local.json + backend/.env.web3
./scripts/smoke_week1.sh      # optional: Python-signed quote -> deposit -> deliver -> release on the real chain
(cd contracts && forge test)  # contract tests (incl. cross-language EIP-712 vectors)
```

- `scripts/bootstrap.sh --fresh` restarts Anvil from a clean chain; `--no-anvil` uses a node that is already running. Contract libraries are installed by `scripts/install_contract_deps.sh` (pinned tags, `contracts/lib/` is git-ignored).
- Frontend reads the chain info from `deployments/local.json` (bootstrap copies it to `frontend/public/deployments/`). Optional env: `VITE_API_BASE` (default `http://localhost:5000`), `VITE_RPC_URL` (default `http://127.0.0.1:8545`).
- EIP-712 types live in `shared/eip712/types.json`; `python scripts/gen_eip712_vectors.py` regenerates `vectors.json` (`--check` verifies it).
- Web3 database migrations (later weeks) are numbered after the legacy ones, starting at `0006`.

## Orders, refunds and payments (legacy flow)

- Cancelling a `paid` order restores stock and refunds the buyer, and takes the same amount back from the seller who was credited. If the seller no longer has enough balance the cancel is rejected (`409 refund_unavailable`) and nothing changes.
- Cash on delivery and `cash` payment methods never credit the seller's balance (only a real charge to the buyer does).
- Users that already have orders cannot be deleted (`409 user_has_orders`); orders are kept for accounting.

## Features
- Basic e-commerce features: **Product Listing, Cart, Checkout, Order Management, User Authentication**, etc.
- Basic management features: **Product Management, Order Management, User Account Management**, etc.
- Other features: **Product Reviews, Product Ratings, Product Search**, **Game**, etc.
> Admin accounts are created with `flask --app app seed-admin` (password ≥ 12 chars).

## Testing
See [test](test/) folder for some basic tests, written by our beloved AG  
- To run test, simply run:
```shell
pytest test/ -v
```  
(-v stands for 'more verbose', is optional)
- Integration/race-condition tests run against a **real MySQL** (`DB_HOST`/`DB_USER`/`DB_PASSWORD`); they create and drop a throw-away `slopee_test_<pid>` database and are skipped when MySQL is unreachable. CI uses a MySQL service (`.github/workflows/tests.yml`).
- Money is stored and handled as whole VND (`DECIMAL(15,0)`). For an existing database run `python migrate.py` in `backend/` (or recreate it with `init_db.py`).
  
There are [Playwright](https://playwright.dev/) (UI: Firefox only) tests to run as well  
**First**, install Playwright (no browsers, we install later):  
```shell
npm install -D @playwright/test
```  
**Then** install Firefox:  
```shell
npx playwright install firefox
```  
> [!NOTE]
> If you want to use other browswers (chromium, safari, etc...), install them instead  
> Edit [playwright.config.js](frontend/playwright.config.js), do note that you can [run test on multiple browsers](https://playwright.dev/docs/browsers#configure-browsers).

**Final** touch: to be able to clean up database after test, install this package:
```shell
npm install -D mysql2
```
After setting up the web, inside /frontend, run:
```shell
npm run test:e2e:ui
```  
_See the magic yourself_  
> That's it for now
