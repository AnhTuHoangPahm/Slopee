# Slopee

A Shopee's clone.

## What is Shopee?
Shopee is an e-commerce online shopping platform.

## Why call this Slopee?
The name is the combination of **Slop** and **Shopee** (Shout out to the word **Microslop** for inspiration):
- The entire code production is AI, so I call it Slop.
- It is a cheap(?) clone of Shopee. (used up AI Pro-tier account credits, so calling it 'cheap' is unfair)

## Tech stack
- Frontend: Node.js React, Vite, Vanilla CSS
- Backend: Python Flask
- Database: MySQL
- Google Antigravity(?)

## How to run
I don't think I should, but just in case:  
First install dependencies:
- `npm install` (frontend)
- `pip install -r requirements.txt`  

> [!NOTE]
> Additional modules:  
> **Python**: mysql-connector-python  
> **Node.js**: react-router-dom  

**Set up**:
- Edit environment variables of your computer, add a global entry:
  - DB_PASSWORD: your_databse_password
- Database creation:  
  - `python init_db.py`
- Scaffold front-end framework:  
  - `npm create vite@latest frontend -- --template react`

**Then**:
- `npm run dev` (frontend)
- `python app.py` (backend)
> Enjoy your stay

## Features
- Basic e-commerce features: **Product Listing, Cart, Checkout, Order Management, User Authentication**, etc.
- Basic management features: **Product Management, Order Management, User Account Management**, etc.
- Other features: **Product Reviews, Product Ratings, Product Search**, etc.
  
> That's it for now