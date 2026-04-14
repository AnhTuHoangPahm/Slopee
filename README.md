# Slopee

A (vibe-coded) Shopee clone.

## What is Shopee?
[Shopee](https://shopee.com/) is an e-commerce online shopping platform.

## Why call this Slopee?
The name is the combination of **Slop** and **Shopee** (Shout out to the word **Microslop** for inspiration):
- The entire code production is AI, so I call it Slop.
- It is a cheap(?) clone of Shopee. (I used up my tokens, so calling it 'cheap' is kinda unfair)

## Tech stack
- Frontend: Node.js React, Vite, Vanilla CSS
- Backend: Flask (Python)
- Database: MySQL
- Google Antigravity(?)

## How to run
I don't think I should (I'm just stup-d), but just in case:  
First, **install dependencies**:
- `npm install` (./frontend)
- `pip install -r requirements.txt`  

> [!NOTE]
> Additional modules:  
> **Node**: react-router-dom  

**Set up**:
- Edit environment variables of your computer, add a global entry:
  - DB_PASSWORD: your_databse_password
- Database creation:  
  - `python init_db.py`

**Then**:
- `npm run dev` (frontend)
- `python app.py` (backend)
> Enjoy your stay

## Features
- Basic e-commerce features: **Product Listing, Cart, Checkout, Order Management, User Authentication**, etc.
- Basic management features: **Product Management, Order Management, User Account Management**, etc.
- Other features: **Product Reviews, Product Ratings, Product Search**, etc.
> admin account: username=admin, password=admin

> That's it for now
