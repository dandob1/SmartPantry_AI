from flask import Flask, render_template, request
import os
from receipt_analysis import analyze_receipt
import magic # type: ignore
import sqlite3
from flask import Flask, session, render_template, redirect, url_for, request

app = Flask(__name__)
app.secret_key = "poop fart"
app.debug = True

SUPPORTED_FORMATS = [
    "PDF", "JPEG", "JPG", "PNG"
]

ALLOWED_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/jpg"
}
def get_db_connection():
    return sqlite3.connect("db.db")

@app.route("/", methods=["GET", "POST"])
def login():
    check = None
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT uid, fname, lname FROM User WHERE email = ? AND password = ?", (email, password))
        user = cur.fetchone()
        conn.close()

        if user:
            session["uid"] = user[0]
            session["fname"] = user[1]
            session["lname"] = user[2]
            return redirect(url_for("home"))
        else:
            check = "Invalid email or password."
    return render_template("login.html", check=check)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    error = None
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        fname = request.form["firstName"]
        lname = request.form["lastName"]

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM User WHERE email = ?", (email,))
        if cur.fetchone():
            error = "Email already registered."
        else:
            cur.execute("INSERT INTO User (fname, lname, email, password) VALUES (?, ?, ?, ?)",
                        (fname, lname, email, password))
            conn.commit()
            uid = cur.lastrowid
            session["uid"] = uid
            session["fname"] = fname
            session["lname"] = lname
            conn.close()
            return redirect(url_for("home"))
        conn.close()
    return render_template("signup.html", error=error)


@app.route("/home", methods=["GET", "POST"])
def home():
    result = None
    image_path = None
    error = None

    if request.method == "POST":
        file = request.files["receipt"]
        if file:
            
            filepath = os.path.join('uploads', file.filename)
            file.save(filepath)

            ext = os.path.splitext(file.filename)[1][1:].upper()
            type = magic.from_file(filepath, mime=True)
            if ext not in SUPPORTED_FORMATS or type not in ALLOWED_TYPES:
                error = f"Unsupported or corrupted file. Allowed types: {', '.join(SUPPORTED_FORMATS)}."
            else:
                result, image_path = analyze_receipt(filepath)
    return render_template("home.html", result=result, image_path=image_path, error=error)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)