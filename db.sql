--Users
DROP TABLE IF EXISTS User;
CREATE TABLE User (
    uid INTEGER PRIMARY KEY AUTOINCREMENT,
    fname VARCHAR(50) NOT NULL,
    lname VARCHAR(50) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL
);

--Entire Reciept
DROP TABLE IF EXISTS receipt;
CREATE TABLE receipt (
    rid INTEGER PRIMARY KEY AUTOINCREMENT,
    uid INTEGER NOT NULL,
    total_spend DECIMAL(10, 2),
    date_uploaded TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    image_path TEXT,
    FOREIGN KEY (uid) REFERENCES User(uid)
); 

--Each Individual Reciept List
DROP TABLE IF EXISTS receiptData;
CREATE TABLE receiptData (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rid INTEGER NOT NULL,
    itemName VARCHAR(100) NOT NULL,
    itemPrice DECIMAL(10, 2) NOT NULL,
    category VARCHAR(100),
    subcategory VARCHAR(100),
    FOREIGN KEY (rid) REFERENCES receipt(rid)
); 

DROP TABLE IF EXISTS savedRecipe;
CREATE TABLE savedRecipe (
    recipe_id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid       INTEGER NOT NULL,
    name      VARCHAR(150) NOT NULL,
    ingredients TEXT     NOT NULL,
    instructions TEXT     NOT NULL,
    date_saved   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (uid) REFERENCES User(uid)
);