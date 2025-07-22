from flask import Flask, render_template, request
import os
from receipt_analysis import analyze_receipt, classify_item
import magic
import sqlite3
from flask import Flask, session, render_template, redirect, url_for, request
from datetime import datetime, timezone

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

#login route
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

#signup route
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

#logout route
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

#home page display
@app.route("/home", methods=["GET", "POST"])
def home():
    if 'uid' not in session:
        return redirect(url_for('login'))
    
    result = []
    image_path = None
    error = None

    if request.method == "POST":
        file = request.files["receipt"]
        if file:
            #make sure right type of file
            filepath = os.path.join('uploads', file.filename)
            file.save(filepath)

            ext = os.path.splitext(file.filename)[1][1:].upper()
            type = magic.from_file(filepath, mime=True)
            if ext not in SUPPORTED_FORMATS or type not in ALLOWED_TYPES:
                error = f"Unsupported or corrupted file. Allowed types: {', '.join(SUPPORTED_FORMATS)}."
            else:
                result, image_path = analyze_receipt(filepath, session["uid"])

    return render_template("home.html", table_data=result, image_path=image_path, error=error)

#see all items bought page/control delete
@app.route("/history", methods=["GET", "POST"])
def history():
    if 'uid' not in session:
        return redirect(url_for('login'))

    uid = session['uid']
    conn = get_db_connection()
    cur = conn.cursor()
    error = None
    override_item = None

    if 'add_item' in request.form:
            item = request.form.get('new_item','').strip()
            forceAdd = request.form.get('force_add') == '1'

            if item:
                #get existing items
                cur.execute("""SELECT d.itemName FROM receiptData d JOIN receipt r ON d.rid = r.rid WHERE r.uid = ?""", (uid,))
                rows = cur.fetchall()
                existing = []
                for row in rows:
                    existing.append(row[0])
                #classify item and check if its there
                cat, sub = classify_item(item, existing)
                if cat is None and not forceAdd:
                    # duplicate found, show override button
                    error = f"It looks like <b>{item}</b> is already in your history."
                    override_item = item
                else:
                    #update table
                    cur.execute("INSERT INTO receipt (uid, total_spend) VALUES (?,?)", (uid, 0.00))
                    rid = cur.lastrowid
                    cur.execute(
                        "INSERT INTO receiptData (rid, itemName, itemPrice, category, subcategory) VALUES (?,?,?,?,?)",
                        (rid, item, 0.00, cat or "Other", sub or "Force Added")
                    )
                    conn.commit()
                    error = None
                    override_item = None

    if request.method == "POST":
        #delete all
        if 'clear_all' in request.form:
            cur.execute("""SELECT d.id, d.itemName, d.itemPrice, d.category, d.subcategory, DATE(r.date_uploaded) AS date
                FROM receiptData d JOIN receipt r ON d.rid = r.rid WHERE r.uid = ? ORDER BY r.date_uploaded DESC""", (uid,))
            conn.commit()
        # delete only some
        elif 'delete_selected' in request.form:
            ids = request.form.getlist('selected')
            if ids:
                placeholders = ",".join("?" for _ in ids)
                cur.execute(f"DELETE FROM receiptData WHERE id IN ({placeholders})", ids)
                conn.commit()

    #get rows for history
    cur.execute("""
        SELECT d.id, d.itemName, d.itemPrice, d.category, d.subcategory, DATE(r.date_uploaded) AS date
        FROM receiptData d JOIN receipt r ON d.rid = r.rid WHERE r.uid = ? ORDER BY r.date_uploaded DESC""", (uid,))
    rows = cur.fetchall()
    conn.close()

    return render_template("history.html", purchases=rows, error=error, override_item=override_item)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081, debug=True)