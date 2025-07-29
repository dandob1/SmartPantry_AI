import os
from receipt_analysis import analyze_receipt, classify_item, recipe
import magic
import sqlite3
from flask import Flask, session, render_template, redirect, url_for, request, flash
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
    total_cost = 0.0
    broken = None

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
                result, image_path, broken = analyze_receipt(filepath, session["uid"])
            
            #items = result
            total_cost = sum(item[1] for item in result)

    return render_template("home.html", table_data=result, image_path=image_path,total_cost=total_cost, error=error, broken=broken)

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
    #see all/less button
    show_all = session.get('show_all', False)
    if request.method == "POST" and 'toggle_all' in request.form:
        show_all = not show_all
        session['show_all'] = show_all

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
            cur.execute("""DELETE FROM receiptData WHERE rid IN (SELECT rid FROM receipt WHERE uid = ?)""", (uid,))
            conn.commit()
        # delete only some
        elif 'delete_selected' in request.form:
            ids = request.form.getlist('selected')
            if ids:
                placeholders = ",".join("?" for _ in ids)
                cur.execute(f"DELETE FROM receiptData WHERE id IN ({placeholders})", ids)
                conn.commit()

    #get rows for history
    cur.execute("SELECT DISTINCT d.category FROM receiptData d JOIN receipt r ON d.rid = r.rid WHERE r.uid = ?", (uid,))
    categories = [row[0] for row in cur.fetchall()]

    cur.execute("SELECT DISTINCT d.subcategory FROM receiptData d JOIN receipt r ON d.rid = r.rid WHERE r.uid = ?", (uid,))
    subcategories = [row[0] for row in cur.fetchall()]

    category = request.args.get('filter_category', '').strip()
    subcategory = request.args.get('filter_subcategory', '').strip()
    word = request.args.get('search_term', '').strip()

    sql = "SELECT d.id, d.itemName, d.itemPrice, d.category, d.subcategory, DATE(r.date_uploaded) AS date FROM receiptData d JOIN receipt r ON d.rid = r.rid"
    uidis = ["r.uid = ?"]
    params = [uid]

    if not show_all:
        uidis.append("d.category IN ('Groceries', 'Other')")

    if category:
        uidis.append("d.category = ?")
        params.append(category)

    if subcategory:
        uidis.append("d.subcategory = ?")
        params.append(subcategory)

    if word:
        uidis.append("d.itemName LIKE ?")
        params.append(f"%{word}%")

    query = (sql + " WHERE " + " AND ".join(uidis) + " ORDER BY r.date_uploaded DESC")
    cur.execute(query, params)
    rows = cur.fetchall()

    conn.close()

    return render_template("history.html", purchases=rows, error=error, show_all=show_all, override_item=override_item, categories=categories,
        subcategories=subcategories, filter_category=category, filter_subcategory=subcategory,search_term=word)

#financial page data
@app.route("/financial")
def financial():
    if 'uid' not in session:
        return redirect(url_for('login'))

    uid = session['uid']

    conn = get_db_connection()
    cur = conn.cursor()
    #current total spending
    cur.execute("""SELECT COALESCE(SUM(d.itemPrice),0) FROM receiptData d JOIN receipt r ON d.rid = r.rid WHERE r.uid = ?""", (uid,))
    current_total = cur.fetchone()[0]
    #all time total spending
    cur.execute("""SELECT COALESCE(SUM(total_spend),0) FROM receipt WHERE uid = ?""", (uid,))
    total = cur.fetchone()[0]
    #dates for graph
    cur.execute("""SELECT date_uploaded, total_spend FROM receipt WHERE uid = ? ORDER BY date_uploaded""", (uid,))
    rows = cur.fetchall()
    conn.close()

    dates = []
    sums = []
    running = 0.0
    for ts_str, amt in rows:
        date = datetime.fromisoformat(ts_str)
        dates.append(date.isoformat())
        running += float(amt)
        sums.append(running)

    return render_template("financial.html", current_total=current_total, all_time_total=total, x_vals=dates, y_vals=sums)

@app.route("/recipes", methods=["GET", "POST"])
def recipes():
    if 'uid' not in session:
        return redirect(url_for('login'))

    #get pantry
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""SELECT d.itemName FROM receiptData d JOIN receipt r ON d.rid = r.rid WHERE r.uid = ?""", (session['uid'],))
    pantry = [row[0] for row in cur.fetchall()]
    
    #get saved items
    cur.execute(
        "SELECT recipe_id, name, date_saved FROM savedRecipe WHERE uid = ? ORDER BY date_saved DESC",
        (session['uid'],)
    )
    saved = cur.fetchall()
    conn.close()

    #generate
    result = None
    srequest = ""
    if request.method == "POST":
        #save vs delete a recipe
        if request.form.get('action') == 'save':
            name = request.form.get('recipe_name', '').strip()
            raw  = request.form.get('recipe_data')

            if not name:
                flash('Please provide a name for your recipe.', 'error')
                return redirect(url_for('recipes'))

            conn = get_db_connection()
            cur  = conn.cursor()
            cur.execute("INSERT INTO savedRecipe (uid, name, ingredients, instructions)VALUES (?, ?, ?, ?)", (session['uid'], name, raw, raw))
            conn.commit()
            conn.close()

            flash(f'Recipe “{name}” saved successfully!')
            return redirect(url_for('recipes'))
        elif request.form.get('action') == 'delete':
            rid = request.form.get('recipe_id')
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM savedRecipe WHERE recipe_id = ? AND uid = ?", (rid, session['uid']))
            conn.commit()
            conn.close()
            flash('Saved recipe deleted.')
            return redirect(url_for('recipes'))
        else:
            #get a recipe
            difficulty = request.form.get("difficulty")
            srequest = request.form.get("srequest", "").strip()
            result = recipe(pantry, difficulty, srequest)

    return render_template("recipes.html", pantry=pantry, recipe=result, saved_recipes=saved, srequest=srequest)

@app.route("/saved_recipes")
def saved_recipes():
    if 'uid' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT recipe_id, name, date_saved FROM savedRecipe WHERE uid = ? ORDER BY date_saved DESC", (session['uid'],))
    saved = cur.fetchall()
    conn.close()
    return render_template("saved_recipes.html", recipes=saved)

@app.route("/recipes/<int:recipe_id>")
def view_saved(recipe_id):
    if 'uid' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT name, ingredients, instructions, date_saved FROM savedRecipe WHERE recipe_id = ? AND uid = ?", (recipe_id, session['uid']))
    row = cur.fetchone()
    conn.close()

    if not row:
        flash("Recipe not found or you don't have permission to view it.")
        return redirect(url_for('recipes'))

    name, ingredients, instructions, date_saved = row
    return render_template("view_recipe.html", name=name, ingredients=ingredients, instructions=instructions, date_saved=date_saved)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081, debug=True)