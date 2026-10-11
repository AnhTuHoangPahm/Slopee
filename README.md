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
  
Use your favourite browser to access the page.  
 > Enjoy your stay

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
- Money is stored and handled as whole VND (`DECIMAL(15,0)`). For an existing database run `backend/migrations/0001_money_to_vnd.sql` (or recreate it with `init_db.py`).
  
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
