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
- `npm install` (/frontend)  
- `pip install -r requirements.txt`  

**Set up**:
- Edit environment variables of your computer, add a global entry:
  - DB_PASSWORD: your_databse_password
- Database creation:  
  - `python init_db.py`

**Then**:
- `npm run dev` (/frontend)
- `python app.py` (/backend)
  
Use your favourite browser to access the page.
> Enjoy your stay

## Features
- Basic e-commerce features: **Product Listing, Cart, Checkout, Order Management, User Authentication**, etc.
- Basic management features: **Product Management, Order Management, User Account Management**, etc.
- Other features: **Product Reviews, Product Ratings, Product Search**, **Game**, etc.
> admin account: username: admin, password: admin

## Testing
See [test](https://github.com/AnhTuHoangPahm/Slopee/tree/main/test) folder for some basic tests, written by our beloved AG  
- To run test, simply run: `pytest test/ -v`  
(-v stands for 'more verbose', is optional)
  
There are [Playwright](https://playwright.dev/) (UI: Firefox only) tests to run as well  
**First**, install Playwright (no browsers, we install later):  
- `npm install -D @playwright/test`  

**Then** install Firefox:  
- `npx playwright install firefox`  

**Final** touch: to be able to clean up database after test, install this package:
- `npm install -D mysql2`

After setting up the web, inside /frontend, run:  
- `npm run test:e2e:ui`  
  
_See the magic yourself_

> That's it for now
