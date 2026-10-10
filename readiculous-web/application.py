"""Readiculous Goals - a small TBR (to-be-read) web app. Flask + MySQL.
File is named application.py with an `application` object so AWS Elastic Beanstalk
(Python platform) finds it automatically."""
import os
from functools import wraps

import pymysql
from pymysql.cursors import DictCursor
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, g)
from werkzeug.security import generate_password_hash, check_password_hash

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

application = Flask(__name__)
app = application
application.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

STATUSES = ("to_read", "reading", "finished")


# ---------------------------------------------------------------- database
def db_config(with_db=True):
    # DB_* for localhost/EC2; RDS_* are set automatically by Elastic Beanstalk
    cfg = dict(
        host=os.environ.get("DB_HOST") or os.environ.get("RDS_HOSTNAME", "localhost"),
        port=int(os.environ.get("DB_PORT") or os.environ.get("RDS_PORT", 3306)),
        user=os.environ.get("DB_USER") or os.environ.get("RDS_USERNAME", "root"),
        password=os.environ.get("DB_PASSWORD") or os.environ.get("RDS_PASSWORD", ""),
        cursorclass=DictCursor, autocommit=True, charset="utf8mb4",
        connect_timeout=10,
    )
    if with_db:
        cfg["database"] = os.environ.get("DB_NAME") or os.environ.get("RDS_DB_NAME", "readiculous")
    return cfg


def db():
    if "db" not in g:
        g.db = pymysql.connect(**db_config())
    return g.db


@application.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
      id INT AUTO_INCREMENT PRIMARY KEY,
      username VARCHAR(50) NOT NULL UNIQUE,
      email VARCHAR(120) NOT NULL UNIQUE,
      password_hash VARCHAR(255) NOT NULL,
      role ENUM('admin','reader') NOT NULL DEFAULT 'reader',
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS books (
      id INT AUTO_INCREMENT PRIMARY KEY,
      title VARCHAR(200) NOT NULL,
      author VARCHAR(120) NOT NULL,
      genre VARCHAR(60) NOT NULL,
      pages INT NOT NULL DEFAULT 0,
      description TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS tbr_items (
      id INT AUTO_INCREMENT PRIMARY KEY,
      user_id INT NOT NULL,
      book_id INT NOT NULL,
      status ENUM('to_read','reading','finished') NOT NULL DEFAULT 'to_read',
      added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      finished_at DATETIME NULL,
      UNIQUE KEY uq_user_book (user_id, book_id),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS reading_goals (
      id INT AUTO_INCREMENT PRIMARY KEY,
      user_id INT NOT NULL,
      year INT NOT NULL,
      target_books INT NOT NULL,
      UNIQUE KEY uq_user_year (user_id, year),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)""",
]

SAMPLE_BOOKS = [
    ("The Hobbit", "J.R.R. Tolkien", "Fantasy", 310, "A hobbit's unexpected journey."),
    ("Pride and Prejudice", "Jane Austen", "Romance", 279, "Manners, marriage and misjudgment."),
    ("1984", "George Orwell", "Dystopian", 328, "Big Brother is watching."),
    ("Dune", "Frank Herbert", "Sci-Fi", 412, "Spice, sand and politics."),
    ("Gone Girl", "Gillian Flynn", "Thriller", 422, "A marriage gone very wrong."),
]


def init_db():
    conn = pymysql.connect(**db_config())
    try:
        with conn.cursor() as cur:
            for stmt in SCHEMA:
                cur.execute(stmt)
            cur.execute("SELECT COUNT(*) AS c FROM users")
            if cur.fetchone()["c"] == 0:
                cur.execute(
                    "INSERT INTO users (username,email,password_hash,role) VALUES (%s,%s,%s,'admin')",
                    ("admin", "admin@example.com", generate_password_hash("admin123")))
            cur.execute("SELECT COUNT(*) AS c FROM books")
            if cur.fetchone()["c"] == 0:
                cur.executemany(
                    "INSERT INTO books (title,author,genre,pages,description) VALUES (%s,%s,%s,%s,%s)",
                    SAMPLE_BOOKS)
    finally:
        conn.close()


try:
    init_db()
except Exception as e:  # app still boots; /health will show the problem
    print("DB init failed:", e)


# ------------------------------------------------------------------ auth
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*a, **kw):
        if session.get("role") != "admin":
            flash("Admins only.", "error")
            return redirect(url_for("books"))
        return f(*a, **kw)
    return wrapper


@application.route("/")
def index():
    return redirect(url_for("books" if "user_id" in session else "login"))


@application.route("/health")
def health():
    try:
        with db().cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM books")
            return {"status": "ok", "database": "connected", "books": cur.fetchone()["c"]}
    except Exception as e:
        return {"status": "error", "database": str(e)}, 500


@application.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        if not username or not email or len(password) < 6:
            flash("Fill all fields; password needs 6+ characters.", "error")
            return render_template("register.html")
        try:
            with db().cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username,email,password_hash) VALUES (%s,%s,%s)",
                    (username, email, generate_password_hash(password)))
        except pymysql.err.IntegrityError:
            flash("Username or email already taken.", "error")
            return render_template("register.html")
        flash("Account created. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@application.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        with db().cursor() as cur:
            cur.execute("SELECT * FROM users WHERE username=%s", (request.form["username"].strip(),))
            user = cur.fetchone()
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session.clear()
            session.update(user_id=user["id"], username=user["username"], role=user["role"])
            return redirect(url_for("books"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@application.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------------------------------------------- module: book catalog
@application.route("/books")
@login_required
def books():
    q = request.args.get("q", "").strip()
    genre = request.args.get("genre", "").strip()
    sql, params = "SELECT * FROM books WHERE 1=1", []
    if q:
        sql += " AND (title LIKE %s OR author LIKE %s)"
        params += [f"%{q}%", f"%{q}%"]
    if genre:
        sql += " AND genre=%s"
        params.append(genre)
    sql += " ORDER BY title"
    with db().cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.execute("SELECT DISTINCT genre FROM books ORDER BY genre")
        genres = [r["genre"] for r in cur.fetchall()]
        cur.execute("SELECT book_id FROM tbr_items WHERE user_id=%s", (session["user_id"],))
        mine = {r["book_id"] for r in cur.fetchall()}
    return render_template("books.html", books=rows, genres=genres, mine=mine, q=q, genre=genre)


def _book_from_form():
    f = request.form
    try:
        pages = max(0, int(f.get("pages") or 0))
    except ValueError:
        pages = 0
    return (f["title"].strip(), f["author"].strip(), f["genre"].strip(), pages,
            f.get("description", "").strip())


@application.route("/books/add", methods=["GET", "POST"])
@admin_required
def add_book():
    if request.method == "POST":
        data = _book_from_form()
        if not data[0] or not data[1] or not data[2]:
            flash("Title, author and genre are required.", "error")
            return render_template("book_form.html", book=None)
        with db().cursor() as cur:
            cur.execute("INSERT INTO books (title,author,genre,pages,description) VALUES (%s,%s,%s,%s,%s)", data)
        flash("Book added.", "success")
        return redirect(url_for("books"))
    return render_template("book_form.html", book=None)


@application.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_book(book_id):
    with db().cursor() as cur:
        cur.execute("SELECT * FROM books WHERE id=%s", (book_id,))
        book = cur.fetchone()
        if not book:
            flash("Book not found.", "error")
            return redirect(url_for("books"))
        if request.method == "POST":
            cur.execute("UPDATE books SET title=%s, author=%s, genre=%s, pages=%s, description=%s WHERE id=%s",
                        _book_from_form() + (book_id,))
            flash("Book updated.", "success")
            return redirect(url_for("books"))
    return render_template("book_form.html", book=book)


@application.route("/books/<int:book_id>/delete", methods=["POST"])
@admin_required
def delete_book(book_id):
    with db().cursor() as cur:
        cur.execute("DELETE FROM books WHERE id=%s", (book_id,))
    flash("Book deleted.", "success")
    return redirect(url_for("books"))


# ------------------------------------------- module: TBR list + reading goals
@application.route("/tbr")
@login_required
def tbr():
    uid, year = session["user_id"], __import__("datetime").date.today().year
    with db().cursor() as cur:
        cur.execute("""SELECT t.id, t.status, b.title, b.author, b.genre, b.pages
                       FROM tbr_items t JOIN books b ON b.id=t.book_id
                       WHERE t.user_id=%s ORDER BY t.added_at DESC""", (uid,))
        items = cur.fetchall()
        cur.execute("SELECT target_books FROM reading_goals WHERE user_id=%s AND year=%s", (uid, year))
        g_row = cur.fetchone()
        cur.execute("SELECT COUNT(*) AS c FROM tbr_items WHERE user_id=%s AND status='finished' "
                    "AND YEAR(finished_at)=%s", (uid, year))
        done = cur.fetchone()["c"]
    target = g_row["target_books"] if g_row else 0
    pct = min(100, int(done * 100 / target)) if target else 0
    return render_template("tbr.html", items=items, year=year, target=target,
                           done=done, pct=pct, statuses=STATUSES)


@application.route("/tbr/add/<int:book_id>", methods=["POST"])
@login_required
def tbr_add(book_id):
    try:
        with db().cursor() as cur:
            cur.execute("INSERT INTO tbr_items (user_id,book_id) VALUES (%s,%s)", (session["user_id"], book_id))
        flash("Added to your TBR.", "success")
    except pymysql.err.IntegrityError:
        flash("Already in your TBR (or book missing).", "error")
    return redirect(request.referrer or url_for("books"))


@application.route("/tbr/<int:item_id>/status", methods=["POST"])
@login_required
def tbr_status(item_id):
    status = request.form.get("status")
    if status not in STATUSES:
        flash("Invalid status.", "error")
        return redirect(url_for("tbr"))
    with db().cursor() as cur:
        cur.execute("UPDATE tbr_items SET status=%s, finished_at=IF(%s='finished', NOW(), NULL) "
                    "WHERE id=%s AND user_id=%s", (status, status, item_id, session["user_id"]))
    return redirect(url_for("tbr"))


@application.route("/tbr/<int:item_id>/remove", methods=["POST"])
@login_required
def tbr_remove(item_id):
    with db().cursor() as cur:
        cur.execute("DELETE FROM tbr_items WHERE id=%s AND user_id=%s", (item_id, session["user_id"]))
    flash("Removed from your TBR.", "success")
    return redirect(url_for("tbr"))


@application.route("/goal", methods=["POST"])
@login_required
def set_goal():
    try:
        target = int(request.form["target"])
        if target < 1:
            raise ValueError
    except (ValueError, KeyError):
        flash("Goal must be a positive number.", "error")
        return redirect(url_for("tbr"))
    year = __import__("datetime").date.today().year
    with db().cursor() as cur:
        cur.execute("INSERT INTO reading_goals (user_id,year,target_books) VALUES (%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE target_books=VALUES(target_books)",
                    (session["user_id"], year, target))
    flash("Reading goal saved.", "success")
    return redirect(url_for("tbr"))


if __name__ == "__main__":
    application.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
