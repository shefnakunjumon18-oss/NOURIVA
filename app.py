from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
import re
import os
import uuid
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from datetime import date


PEXELS_API_KEY = "pjWRo8ZHkKJ5eFdbpAcUgJdEwovJ32k0JcJfEHtPKpmppgcJjoWvYDhy"

def get_food_image(search_query):

    try:

        response = requests.get(
            "https://api.pexels.com/v1/search",
            headers={
                "Authorization": PEXELS_API_KEY
            },
            params={
                "query": search_query,
                "per_page": 10,
                "orientation": "landscape"
            },
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        photos = data.get("photos", [])

        if photos:

            # Words that usually indicate a cooked food image
            preferred_words = [
                "cooked",
                "dish",
                "curry",
                "meal",
                "food"
            ]

            # First try to find a matching cooked-food photo
            for photo in photos:

                alt_text = photo.get("alt", "").lower()

                if any(word in alt_text for word in preferred_words):

                    return {
                        "image_url": photo["src"]["large"],
                        "photo_url": photo["url"],
                        "photographer": photo["photographer"]
                    }

            # If no better match is found, use the first result
            photo = photos[0]

            return {
                "image_url": photo["src"]["large"],
                "photo_url": photo["url"],
                "photographer": photo["photographer"]
            }

        # Fallback search
        fallback_response = requests.get(
            "https://api.pexels.com/v1/search",
            headers={
                "Authorization": PEXELS_API_KEY
            },
            params={
                "query": "cooked food dish meal",
                "per_page": 5,
                "orientation": "landscape"
            },
            timeout=10
        )

        fallback_response.raise_for_status()

        fallback_data = fallback_response.json()

        if fallback_data.get("photos"):

            photo = fallback_data["photos"][0]

            return {
                "image_url": photo["src"]["large"],
                "photo_url": photo["url"],
                "photographer": photo["photographer"]
            }

    except Exception as e:

        print("Pexels image error:", e)

    return None


app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# DATABASE CONNECTION
def get_db():
    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    return conn


# CREATE TABLES
def create_table():
    conn = get_db()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        age INTEGER,
        gender TEXT,
        height REAL,
        weight REAL,
        goal TEXT,
        activity TEXT,
        diet TEXT,
        allergies TEXT,
        profile_pic TEXT,
        booked_trainer_id INTEGER
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS trainers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        specialization TEXT,
        experience INTEGER,
        fee REAL,
        profile_pic TEXT
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS recipes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        ingredients TEXT,
        instructions TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS groceries(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        item TEXT,
        quantity TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS meal_planner(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        meal_date TEXT,
        meal_type TEXT,
        recipe TEXT
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS reviews(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trainer_id INTEGER,
        user_id INTEGER,
        rating INTEGER,
        review TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS admin(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS trainer_payouts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trainer_id INTEGER,
        amount REAL,
        status TEXT DEFAULT 'Pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    
    # Bookings table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS bookings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        trainer_id INTEGER NOT NULL,
        session_type TEXT NOT NULL,
        session_date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        duration INTEGER NOT NULL,
        location TEXT,
        meeting_link TEXT,
        message TEXT,
        status TEXT NOT NULL DEFAULT 'Pending',
        rejection_reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Messages table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trainer_id INTEGER,
        user TEXT,
        sender TEXT,
        message TEXT,
        file TEXT,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Add read-status tracking to existing messages table
    existing_message_columns = [
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(messages)"
        ).fetchall()
    ]

    if "is_read" not in existing_message_columns:
        conn.execute("""
            ALTER TABLE messages
            ADD COLUMN is_read INTEGER NOT NULL DEFAULT 0
        """)

    conn.commit()
    conn.close()

create_table()


# Add missing trainer columns to the existing database safely
conn = get_db()

try:
    existing_trainer_columns = [
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(trainers)"
        ).fetchall()
    ]

    if "phone" not in existing_trainer_columns:
        conn.execute(
            "ALTER TABLE trainers ADD COLUMN phone TEXT"
        )

    if "certificate_name" not in existing_trainer_columns:
        conn.execute(
            "ALTER TABLE trainers ADD COLUMN certificate_name TEXT"
        )

    if "bio" not in existing_trainer_columns:
        conn.execute(
            "ALTER TABLE trainers ADD COLUMN bio TEXT"
        )

    if "status" not in existing_trainer_columns:
        conn.execute(
            "ALTER TABLE trainers ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'"
        )

    if "certificate_file" not in existing_trainer_columns:
        conn.execute(
            "ALTER TABLE trainers ADD COLUMN certificate_file TEXT"
        )

    if "photo" not in existing_trainer_columns:
        conn.execute(
            "ALTER TABLE trainers ADD COLUMN photo TEXT"
        )

    conn.commit()

finally:
    conn.close()

# Add rescheduling columns to existing bookings table
conn = get_db()

existing_booking_columns = [
    row["name"]
    for row in conn.execute(
        "PRAGMA table_info(bookings)"
    ).fetchall()
]

if "requested_date" not in existing_booking_columns:
    conn.execute("""
        ALTER TABLE bookings
        ADD COLUMN requested_date TEXT
    """)

if "requested_time" not in existing_booking_columns:
    conn.execute("""
        ALTER TABLE bookings
        ADD COLUMN requested_time TEXT
    """)

if "reschedule_status" not in existing_booking_columns:
    conn.execute("""
        ALTER TABLE bookings
        ADD COLUMN reschedule_status TEXT
    """)

conn.commit()
conn.close()


# HOME
@app.route("/")
def home():
    return render_template("index.html")



# REGISTER USER
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Validate required fields
        if not username or not email or not password:
            return render_template(
                "register.html",
                error_message="All fields are required."
            )

        # Validate username length
        if len(username) < 3 or len(username) > 30:
            return render_template(
                "register.html",
                error_message="Username must be between 3 and 30 characters."
            )

        # Validate email format
        email_pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

        if not re.match(email_pattern, email):
            return render_template(
                "register.html",
                error_message="Please enter a valid email address."
            )

        # Validate password length
        if len(password) < 8:
            return render_template(
                "register.html",
                error_message="Password must contain at least 8 characters."
            )

        # Validate uppercase letter
        if not re.search(r"[A-Z]", password):
            return render_template(
                "register.html",
                error_message="Password must contain an uppercase letter."
            )

        # Validate lowercase letter
        if not re.search(r"[a-z]", password):
            return render_template(
                "register.html",
                error_message="Password must contain a lowercase letter."
            )

        # Validate number
        if not re.search(r"[0-9]", password):
            return render_template(
                "register.html",
                error_message="Password must contain a number."
            )

        # Validate special character
        if not re.search(r"[^A-Za-z0-9]", password):
            return render_template(
                "register.html",
                error_message="Password must contain a special character."
            )

        # Validate confirm password
        if password != confirm_password:
            return render_template(
                "register.html",
                error_message="Passwords do not match."
            )

        conn = get_db()

        try:
            # Check if username or email already exists
            existing_user = conn.execute(
                """
                SELECT * FROM users
                WHERE username = ? OR email = ?
                """,
                (username, email)
            ).fetchone()

            if existing_user:
                return render_template(
                    "register.html",
                    error=True
                )

            # Hash the password before saving it
            hashed_password = generate_password_hash(password)

            # Create the user
            conn.execute(
                """
                INSERT INTO users
                (username, email, password, created_at)
                VALUES (?, ?, ?, datetime('now', 'localtime'))
                """,
                (username, email, hashed_password)
            )

            conn.commit()

        finally:
            conn.close()

        return redirect("/register?success=1")

    success = request.args.get("success")

    return render_template(
        "register.html",
        success=success
    )


# LOGIN USER
@app.route("/login", methods=["GET", "POST"])
def login():

    error = None

    if request.method == "POST":

        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        conn = get_db()

        try:
            # Find the account using email only
            user = conn.execute(
                "SELECT * FROM users WHERE email=?",
                (email,)
            ).fetchone()

            if user:
                stored_password = user["password"]

                # Check hashed passwords
                if stored_password.startswith(("scrypt:", "pbkdf2:")):
                    password_valid = check_password_hash(
                        stored_password, password
                    )

                else:
                    # Support existing accounts with plain-text passwords
                    password_valid = (stored_password == password)

                    # Upgrade the old password to a secure hash
                    if password_valid:
                        hashed_password = generate_password_hash(password)

                        conn.execute(
                            "UPDATE users SET password=? WHERE email=?",
                            (hashed_password, email)
                        )
                        conn.commit()

                if password_valid:
                    session["user"] = user["username"]
                    return redirect("/dashboard")

            error = "Invalid email or password!"

        finally:
            conn.close()

    return render_template("login.html", error=error)



# DASHBOARD
@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/login")

    conn = get_db()

    user = conn.execute(
        "SELECT * FROM users WHERE username=?",
        (session["user"],)
    ).fetchone()

    conn.close()

    return render_template(
        "dashboard.html",
        user=user["username"]
    )

# USER PROFILE
@app.route("/profile", methods=["GET", "POST"])
def profile():

    if "user" not in session:
        return redirect("/login")

    conn = get_db()

    user = conn.execute(
        "SELECT * FROM users WHERE username=?",
        (session["user"],)
    ).fetchone()

    success = None

    if request.method == "POST":

        phone = request.form.get("phone", "").strip()
        age = request.form.get("age", "").strip()
        gender = request.form.get("gender", "").strip()
        fitness_goal = request.form.get("fitness_goal", "").strip()
        bio = request.form.get("bio", "").strip()

        # Keep existing photo if no new photo is selected
        photo = user["photo"]

        file = request.files.get("photo")

        if file and file.filename != "":

            filename = secure_filename(file.filename)

            filename = str(user["id"]) + "_" + filename

            os.makedirs(
                app.config["UPLOAD_FOLDER"],
                exist_ok=True
            )

            file.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )

            photo = filename

        conn.execute("""
            UPDATE users
            SET phone=?,
                age=?,
                gender=?,
                fitness_goal=?,
                bio=?,
                photo=?
            WHERE username=?
        """, (
            phone,
            age if age else None,
            gender,
            fitness_goal,
            bio,
            photo,
            session["user"]
        ))

        conn.commit()

        # Get updated user data
        user = conn.execute(
            "SELECT * FROM users WHERE username=?",
            (session["user"],)
        ).fetchone()

        # Success message
        success = "Profile saved successfully!"

    conn.close()

    return render_template(
        "profile.html",
        user=user,
        success=success
    )


# TRAINER REGISTER
@app.route("/trainer_register", methods=["GET", "POST"])
def trainer_register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        phone = request.form.get("phone", "").strip()
        specialization = request.form.get("specialization", "").strip()
        experience = request.form.get("experience", "").strip()
        certificate_name = request.form.get("certificate_name", "").strip()
        bio = request.form.get("bio", "").strip()

        certificate_file = request.files.get("certificate_file")
        photo = request.files.get("photo")

        # Validate required fields
        if not all([
            name, email, password, confirm_password,
            phone, specialization, experience,
            certificate_name, bio
        ]):
            return render_template(
                "trainer_register.html",
                error_message="Please fill in all required fields."
            )

        # Validate email
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return render_template(
                "trainer_register.html",
                error_message="Please enter a valid email address."
            )

        # Validate password strength
        if (
            len(password) < 8
            or not re.search(r"[A-Z]", password)
            or not re.search(r"[a-z]", password)
            or not re.search(r"\d", password)
            or not re.search(r"[^A-Za-z0-9]", password)
        ):
            return render_template(
                "trainer_register.html",
                error_message=(
                    "Password must contain at least 8 characters, "
                    "one uppercase letter, one lowercase letter, "
                    "one number, and one special character."
                )
            )

        if password != confirm_password:
            return render_template(
                "trainer_register.html",
                error_message="Passwords do not match."
            )

        # Validate experience
        try:
            experience = int(experience)
            if experience < 0 or experience > 50:
                raise ValueError
        except ValueError:
            return render_template(
                "trainer_register.html",
                error_message="Experience must be between 0 and 50 years."
            )

        # Require both uploaded files
        if not certificate_file or not certificate_file.filename:
            return render_template(
                "trainer_register.html",
                error_message="Please upload your certification proof."
            )

        if not photo or not photo.filename:
            return render_template(
                "trainer_register.html",
                error_message="Please upload your profile photo."
            )

        # Validate file extensions
        certificate_ext = os.path.splitext(
            secure_filename(certificate_file.filename)
        )[1].lower()

        photo_ext = os.path.splitext(
            secure_filename(photo.filename)
        )[1].lower()

        if certificate_ext not in {".pdf", ".jpg", ".jpeg", ".png"}:
            return render_template(
                "trainer_register.html",
                error_message="Certificate must be a PDF, JPG, JPEG, or PNG file."
            )

        if photo_ext not in {".jpg", ".jpeg", ".png"}:
            return render_template(
                "trainer_register.html",
                error_message="Profile photo must be a JPG, JPEG, or PNG image."
            )

        # Create upload folders
        certificate_folder = os.path.join(
            app.root_path, "static", "uploads", "trainer_certificates"
        )
        photo_folder = os.path.join(
            app.root_path, "static", "uploads", "trainer_photos"
        )

        os.makedirs(certificate_folder, exist_ok=True)
        os.makedirs(photo_folder, exist_ok=True)

        # Generate unique filenames
        certificate_filename = (
            f"{uuid.uuid4().hex}{certificate_ext}"
        )
        photo_filename = f"{uuid.uuid4().hex}{photo_ext}"

        certificate_path = os.path.join(
            certificate_folder, certificate_filename
        )
        photo_path = os.path.join(photo_folder, photo_filename)

        # Relative paths stored in the database
        certificate_db_path = (
            f"uploads/trainer_certificates/{certificate_filename}"
        )
        photo_db_path = f"uploads/trainer_photos/{photo_filename}"

        conn = get_db()
        certificate_saved = False
        photo_saved = False

        try:
            # Check for duplicate email
            existing = conn.execute(
                "SELECT email FROM trainers WHERE email = ?",
                (email,)
            ).fetchone()

            if existing:
                return render_template(
                    "trainer_register.html",
                    error_message="This email is already registered."
                )

            # Save files
            certificate_file.save(certificate_path)
            certificate_saved = True

            photo.save(photo_path)
            photo_saved = True

            # Hash password
            hashed_password = generate_password_hash(password)

            # Save trainer details and uploaded file paths
            conn.execute("""
                INSERT INTO trainers (
                    name, email, password, phone, specialization,
                    experience, certificate_name, bio, status,
                    certificate_file, photo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                email,
                hashed_password,
                phone,
                specialization,
                experience,
                certificate_name,
                bio,
                "pending",
                certificate_db_path,
                photo_db_path
            ))

            conn.commit()

        except Exception:
            app.logger.exception("Trainer registration failed")

            # Remove newly uploaded files if registration fails
            if certificate_saved and os.path.exists(certificate_path):
                os.remove(certificate_path)

            if photo_saved and os.path.exists(photo_path):
                os.remove(photo_path)

            return render_template(
                "trainer_register.html",
                error_message=(
                    "Registration failed "
                    
                )
            )

        finally:
            conn.close()

        return render_template(
            "trainer_register.html",
            success_message=(
                "Registration submitted successfully! "
                "Please wait for admin approval."
            )
        )

    return render_template("trainer_register.html")

# TRAINER LOGIN

@app.route("/trainer_login", methods=["GET", "POST"])
def trainer_login():

    error = None

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()

        try:
            # Find trainer using email
            trainer = conn.execute(
                "SELECT * FROM trainers WHERE email=?",
                (email,)
            ).fetchone()

            if trainer:
                stored_password = trainer["password"]

                # Verify hashed password
                if stored_password.startswith(("scrypt:", "pbkdf2:")):
                    password_valid = check_password_hash(
                        stored_password, password
                    )

                else:
                    # Support existing plain-text passwords
                    password_valid = (stored_password == password)

                    # Upgrade old password after successful login
                    if password_valid:
                        hashed_password = generate_password_hash(password)

                        conn.execute(
                            "UPDATE trainers SET password=? WHERE email=?",
                            (hashed_password, email)
                        )
                        conn.commit()

                if password_valid:
                    if trainer["status"] == "approved":
                        session["trainer"] = trainer["name"]
                        return redirect("/trainer_dashboard")

                    elif trainer["status"] == "pending":
                        error = "Your trainer account is not approved by admin yet."

                    else:
                        error = "Your trainer account is not approved."

                else:
                    error = "Invalid email or password!"

            else:
                error = "Invalid email or password!"

        finally:
            conn.close()

    return render_template(
        "trainer_login.html",
        error=error
    )


# TRAINER DASHBOARD
@app.route("/trainer_dashboard")
def trainer_dashboard():

    if "trainer" not in session:
        return redirect("/trainer_login")

    conn = get_db()

    try:
        # Get the logged-in trainer
        trainer = conn.execute(
            "SELECT * FROM trainers WHERE name=?",
            (session["trainer"],)
        ).fetchone()

        if not trainer:
            session.pop("trainer", None)
            return redirect("/trainer_login")

        # Get clients assigned to this trainer
        users = conn.execute(
            """
            SELECT *,
                (
                    SELECT COUNT(*)
                    FROM messages
                    WHERE messages.trainer_id = users.booked_trainer_id
                      AND messages.user = users.username
                      AND messages.sender = 'user'
                      AND messages.is_read = 0
                ) AS unread_count
            FROM users
            WHERE booked_trainer_id = ?
            """,
            (trainer["id"],)
        ).fetchall()

        # Average rating
        avg_rating = conn.execute(
            """
            SELECT AVG(rating) AS avg_rating
            FROM trainer_reviews
            WHERE trainer_id=?
            """,
            (trainer["id"],)
        ).fetchone()

        # Review count
        review_count = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM trainer_reviews
            WHERE trainer_id=?
            """,
            (trainer["id"],)
        ).fetchone()

        # Get payouts belonging only to this trainer
        payouts = conn.execute(
            """
            SELECT id, amount_paise, payment_reference, note, status, paid_at
            FROM trainer_payouts
            WHERE trainer_id=?
            ORDER BY id DESC
            """,
            (trainer["id"],)
        ).fetchall()

        return render_template(
            "trainer_dashboard.html",
            trainer=trainer,
            users=users,
            avg_rating=avg_rating["avg_rating"],
            review_count=review_count["total"],
            payouts=payouts
        )

    finally:
        conn.close()



# TRAINER BOOKINGS
@app.route("/trainer_bookings")
def trainer_bookings():

    if "trainer" not in session:
        return redirect("/trainer_login")

    conn = get_db()

    try:
        # Get the logged-in trainer
        trainer = conn.execute(
            "SELECT * FROM trainers WHERE name=?",
            (session["trainer"],)
        ).fetchone()

        if not trainer:
            session.pop("trainer", None)
            return redirect("/trainer_login")

        # Detect the actual users table columns
        user_columns = [
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(users)"
            ).fetchall()
        ]

        # Select a client display name using an existing column
        if "name" in user_columns:
            client_name_column = "name"
        elif "username" in user_columns:
            client_name_column = "username"
        elif "email" in user_columns:
            client_name_column = "email"
        else:
            client_name_column = None

        # Get booking requests belonging to this trainer
        if client_name_column:
            bookings = conn.execute(
                f"""
                SELECT bookings.*,
                       users."{client_name_column}" AS client_name
                FROM bookings
                JOIN users ON bookings.user_id = users.id
                WHERE bookings.trainer_id = ?
                ORDER BY bookings.created_at DESC
                """,
                (trainer["id"],)
            ).fetchall()
        else:
            bookings = conn.execute(
                """
                SELECT bookings.*, 
                       CAST(bookings.user_id AS TEXT) AS client_name
                FROM bookings
                WHERE bookings.trainer_id = ?
                ORDER BY bookings.created_at DESC
                """,
                (trainer["id"],)
            ).fetchall()

        return render_template(
            "trainer_bookings.html",
            trainer=trainer,
            bookings=bookings
        )

    finally:
        conn.close()



# APPROVE OR REJECT A BOOKING
@app.route("/trainer_booking_action/<int:booking_id>", methods=["POST"])
def trainer_booking_action(booking_id):

    if "trainer" not in session:
        return redirect("/trainer_login")

    from datetime import datetime

    conn = get_db()

    try:
        trainer = conn.execute(
            "SELECT * FROM trainers WHERE name=?",
            (session["trainer"],)
        ).fetchone()

        if not trainer:
            session.pop("trainer", None)
            return redirect("/trainer_login")

        booking = conn.execute(
            """
            SELECT * FROM bookings
            WHERE id=? AND trainer_id=?
            """,
            (booking_id, trainer["id"])
        ).fetchone()

        if not booking:
            return redirect("/trainer_bookings")

        # Only pending requests can be processed
        if booking["status"] != "Pending":
            return redirect("/trainer_bookings")

        action = request.form.get("action", "").strip()

        if action == "reject":
            reason = request.form.get(
                "rejection_reason", ""
            ).strip()

            conn.execute(
                """
                UPDATE bookings
                SET status='Rejected', rejection_reason=?
                WHERE id=? AND trainer_id=? AND status='Pending'
                """,
                (reason, booking_id, trainer["id"])
            )

            conn.commit()
            return redirect("/trainer_bookings")

        if action == "approve":

            # Validate the requested session time
            try:
                start = datetime.strptime(
                    booking["start_time"], "%H:%M"
                )

                requested_start = (
                    start.hour * 60 + start.minute
                )
                requested_end = (
                    requested_start + int(booking["duration"])
                )

            except (ValueError, TypeError):
                return "Invalid booking time or duration.", 400

            # Check approved sessions on the same date
            approved = conn.execute(
                """
                SELECT start_time, duration
                FROM bookings
                WHERE trainer_id=?
                  AND session_date=?
                  AND status='Approved'
                  AND id != ?
                """,
                (
                    trainer["id"],
                    booking["session_date"],
                    booking_id
                )
            ).fetchall()

            for existing in approved:
                try:
                    existing_time = datetime.strptime(
                        existing["start_time"], "%H:%M"
                    )
                    existing_start = (
                        existing_time.hour * 60
                        + existing_time.minute
                    )
                    existing_end = (
                        existing_start + int(existing["duration"])
                    )
                except (ValueError, TypeError):
                    continue

                
                # Sessions overlap if their time intervals intersect
                if (
                    requested_start < existing_end
                    and existing_start < requested_end
                ):
                    return render_template(
                        "booking_overlap_error.html",
                        message=(
                            "This time overlaps with another approved "
                            "session. Please reject this request or ask "
                            "the client to choose another time."
                        )
                    ), 409


            meeting_link = request.form.get(
                "meeting_link", ""
            ).strip()

            location = request.form.get(
                "location", ""
            ).strip()

            # Require the appropriate details for the session type
            if (
                booking["session_type"] == "Online"
                and not meeting_link
            ):
                return (
                    "Enter a meeting link before approving an "
                    "online session.",
                    400
                )

            if (
                booking["session_type"] == "Offline"
                and not (location or booking["location"])
            ):
                return (
                    "Enter the offline session location before "
                    "approving.",
                    400
                )

            conn.execute(
                """
                UPDATE bookings
                SET status='Approved',
                    meeting_link=?,
                    location=?
                WHERE id=? AND trainer_id=? AND status='Pending'
                """,
                (
                    meeting_link or None,
                    location or booking["location"],
                    booking_id,
                    trainer["id"]
                )
            )

            conn.commit()
            return redirect("/trainer_bookings")

        return "Invalid booking action.", 400

    finally:
        conn.close()



# APPROVE OR REJECT A RESCHEDULE REQUEST
@app.route(
    "/trainer_reschedule_action/<int:booking_id>",
    methods=["POST"]
)
def trainer_reschedule_action(booking_id):

    if "trainer" not in session:
        return redirect("/trainer_login")

    from datetime import datetime

    conn = get_db()

    try:
        trainer = conn.execute(
            "SELECT * FROM trainers WHERE name=?",
            (session["trainer"],)
        ).fetchone()

        if not trainer:
            session.pop("trainer", None)
            return redirect("/trainer_login")

        booking = conn.execute(
            """
            SELECT *
            FROM bookings
            WHERE id=? AND trainer_id=?
            """,
            (booking_id, trainer["id"])
        ).fetchone()

        if not booking:
            return "Booking not found.", 404

        if (
            booking["status"] != "Approved"
            or booking["reschedule_status"] != "Pending"
        ):
            return redirect("/trainer_bookings")

        action = request.form.get("action", "").strip()

        if action == "reject":
            conn.execute(
                """
                UPDATE bookings
                SET reschedule_status='Rejected',
                    requested_date=NULL,
                    requested_time=NULL
                WHERE id=? AND trainer_id=?
                  AND reschedule_status='Pending'
                """,
                (booking_id, trainer["id"])
            )

            conn.commit()
            return redirect("/trainer_bookings")

        if action != "approve":
            return "Invalid reschedule action.", 400

        new_date = booking["requested_date"]
        new_time = booking["requested_time"]

        # Validate the proposed date and time
        try:
            selected_date = datetime.strptime(
                new_date, "%Y-%m-%d"
            ).date()

            selected_time = datetime.strptime(
                new_time, "%H:%M"
            )

            if selected_date < datetime.now().date():
                return "The requested date is in the past.", 400

            new_start = (
                selected_time.hour * 60
                + selected_time.minute
            )

            new_end = new_start + int(booking["duration"])

        except (ValueError, TypeError):
            return "Invalid requested date, time, or duration.", 400

        # Check other approved sessions for this trainer
        approved_bookings = conn.execute(
            """
            SELECT start_time, duration
            FROM bookings
            WHERE trainer_id=?
              AND session_date=?
              AND status='Approved'
              AND id != ?
            """,
            (
                trainer["id"],
                new_date,
                booking_id
            )
        ).fetchall()

        for existing in approved_bookings:
            try:
                existing_time = datetime.strptime(
                    existing["start_time"], "%H:%M"
                )

                existing_start = (
                    existing_time.hour * 60
                    + existing_time.minute
                )

                existing_end = (
                    existing_start + int(existing["duration"])
                )

            except (ValueError, TypeError):
                continue

            # Do not approve overlapping sessions
            if (
                new_start < existing_end
                and existing_start < new_end
            ):
                return render_template(
                    "booking_overlap_error.html",
                    message=(
                        "The requested reschedule time overlaps "
                        "with another approved session. The original "
                        "booking has not been changed. Reject this "
                        "request and ask the client to choose another time."
                    )
                ), 409

        # Check the original booking's two-hour deadline again
        original_start = datetime.strptime(
            booking["session_date"] + " " + booking["start_time"],
            "%Y-%m-%d %H:%M"
        )

        from datetime import timedelta

        if datetime.now() >= original_start - timedelta(hours=2):
            return (
                "The reschedule deadline has passed. "
                "The original booking remains unchanged.",
                400
            )

        # Apply the new schedule only after validation
        conn.execute(
            """
            UPDATE bookings
            SET session_date=?,
                start_time=?,
                reschedule_status='Approved',
                requested_date=NULL,
                requested_time=NULL
            WHERE id=? AND trainer_id=?
              AND status='Approved'
              AND reschedule_status='Pending'
            """,
            (
                new_date,
                new_time,
                booking_id,
                trainer["id"]
            )
        )

        conn.commit()
        return redirect("/trainer_bookings")

    finally:
        conn.close()

       



# TRAINER PROFILE
@app.route("/trainer_profile")
def trainer_profile():

    if "trainer" not in session:
        return redirect("/trainer_login")

    conn = get_db()

    trainer = conn.execute(
        "SELECT * FROM trainers WHERE name=?",
        (session["trainer"],)
    ).fetchone()

    conn.close()

    if not trainer:
        session.pop("trainer", None)
        return redirect("/trainer_login")

    return render_template(
        "trainer_profile.html",
        trainer=trainer
    )

# EDIT TRAINER PROFILE
@app.route("/trainer_edit_profile", methods=["GET", "POST"])
def trainer_edit_profile():

    if "trainer" not in session:
        return redirect("/trainer_login")

    conn = get_db()

    trainer = conn.execute(
        "SELECT * FROM trainers WHERE name=?",
        (session["trainer"],)
    ).fetchone()

    if not trainer:
        conn.close()
        session.pop("trainer", None)
        return redirect("/trainer_login")

    if request.method == "POST":

        phone = request.form.get("phone", "").strip()
        specialization = request.form.get("specialization", "").strip()
        experience = request.form.get("experience", "").strip()
        certificate_name = request.form.get("certificate_name", "").strip()
        bio = request.form.get("bio", "").strip()

        # Keep existing photo
        photo = trainer["photo"]

        # New photo
        file = request.files.get("photo")

        if file and file.filename != "":

            filename = secure_filename(file.filename)

            filename = str(trainer["id"]) + "_" + filename

            os.makedirs(
                app.config["UPLOAD_FOLDER"],
                exist_ok=True
            )

            file.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )

            photo = filename

        conn.execute("""
            UPDATE trainers
            SET phone=?,
                specialization=?,
                experience=?,
                certificate_name=?,
                bio=?,
                photo=?
            WHERE id=?
        """, (
            phone,
            specialization,
            experience if experience else None,
            certificate_name,
            bio,
            photo,
            trainer["id"]
        ))

        conn.commit()

        # Get updated trainer
        trainer = conn.execute(
            "SELECT * FROM trainers WHERE id=?",
            (trainer["id"],)
        ).fetchone()

        # Keep session name updated
        session["trainer"] = trainer["name"]

        conn.close()

        return render_template(
            "trainer_edit_profile.html",
            trainer=trainer,
            success="Profile updated successfully!"
        )

    conn.close()

    return render_template(
        "trainer_edit_profile.html",
        trainer=trainer,
        success=None
    )

# TRAINER VIEW CLIENT PROFILE
@app.route("/trainer_client/<int:id>")
def trainer_client(id):

    if "trainer" not in session:
        return redirect("/trainer_login")

    conn = get_db()

    # Get logged-in trainer
    trainer = conn.execute(
        "SELECT * FROM trainers WHERE name=?",
        (session["trainer"],)
    ).fetchone()

    if not trainer:
        conn.close()
        return redirect("/trainer_login")

    # Get client only if this client belongs to this trainer
    client = conn.execute(
        """
        SELECT * FROM users
        WHERE id=?
        AND booked_trainer_id=?
        """,
        (id, trainer["id"])
    ).fetchone()

    conn.close()

    # Client not found or does not belong to this trainer
    if not client:
        return redirect("/trainer_dashboard")

    return render_template(
        "trainer_client.html",
        client=client
    )
# ADMIN TRAINER APPROVAL

@app.route("/admin_trainers")
def admin_trainers():

    if "admin" not in session:
        return redirect("/admin_login")

    conn = get_db()

    trainers = conn.execute(
        "SELECT * FROM trainers WHERE status='pending'"
    ).fetchall()

    conn.close()

    return render_template("admin_trainers.html", trainers=trainers)


# APPROVE TRAINER

@app.route("/approve_trainer/<int:id>", methods=["POST"])
def approve_trainer(id):

    if "admin" not in session:
        return redirect("/admin_login")

    conn = get_db()

    conn.execute(
        "UPDATE trainers SET status='approved' WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/admin_trainers")

# TRAINER PAGE
@app.route("/trainer")
def trainer():

    if "user" not in session:
        return redirect("/login")

    conn = get_db()

    user = conn.execute(
        "SELECT * FROM users WHERE username=?",
        (session["user"],)
    ).fetchone()

    if not user:
        conn.close()
        return redirect("/login")

    if user["booked_trainer_id"]:

        trainer = conn.execute(
            "SELECT * FROM trainers WHERE id=? AND status='approved'",
            (user["booked_trainer_id"],)
        ).fetchone()

        if trainer:

            conn.close()

            return render_template(
                "trainer_details.html",
                trainer=trainer
            )

        # Invalid trainer ID
        # Clear it from the user's account

        conn.execute(
            "UPDATE users SET booked_trainer_id=NULL WHERE username=?",
            (session["user"],)
        )

        conn.commit()

    if user["premium"] == 0:
        conn.close()
        return render_template("trainer_premium.html")

    trainers = conn.execute(
        "SELECT * FROM trainers WHERE status='approved'"
    ).fetchall()

    conn.close()

    return render_template(
        "trainers_list.html",
        trainers=trainers
    )
# PREMIUM TRAINER PAGE

@app.route("/premium_trainer")
def premium_trainer():

    if "user" not in session:
        return redirect("/login")

    conn = get_db()

    user = conn.execute(
        "SELECT * FROM users WHERE username=?",
        (session["user"],)
    ).fetchone()

    conn.close()

    # If already premium, go directly to trainers
    if user["premium"] == 1:
        return redirect("/trainer")

    return render_template("trainer_premium.html")


# PAYMENT
@app.route("/trainer_payment", methods=["POST"])
def trainer_payment():

    if "user" not in session:
        return redirect("/login")

    conn = get_db()

    conn.execute(
        "UPDATE users SET premium=1 WHERE username=?",
        (session["user"],)
    )

    conn.commit()
    conn.close()

    return redirect("/trainer")


# BOOK TRAINER
@app.route("/book_trainer/<int:id>", methods=["GET", "POST"])
def book_trainer(id):

    if "user" not in session:
        return redirect("/login")

    conn = get_db()

    # Get the selected trainer
    trainer = conn.execute(
        "SELECT * FROM trainers WHERE id=?",
        (id,)
    ).fetchone()

    if not trainer:
        conn.close()
        return redirect("/")

    # Get the logged-in user's database ID
    user = conn.execute(
        "SELECT * FROM users WHERE username=?",
        (session["user"],)
    ).fetchone()

    if not user:
        conn.close()
        return redirect("/login")

    if request.method == "POST":

        session_type = request.form.get("session_type", "").strip()
        session_date = request.form.get("session_date", "").strip()
        start_time = request.form.get("start_time", "").strip()
        duration = request.form.get("duration", "").strip()
        location = request.form.get("location", "").strip()
        message = request.form.get("message", "").strip()

        # Validate required fields
        if (
            session_type not in ["Online", "Offline"]
            or not session_date
            or not start_time
            or duration not in ["30", "45", "60", "90", "120"]
        ):
            conn.close()
            return "Please provide valid booking details.", 400

        # Validate date and time formats
        from datetime import date, datetime

        try:
            booking_date = date.fromisoformat(session_date)
            datetime.strptime(start_time, "%H:%M")

            if booking_date < date.today():
                conn.close()
                return "Please select today or a future date.", 400

        except ValueError:
            conn.close()
            return "Invalid date or time.", 400

        # Save the booking request as Pending
        conn.execute(
            """
            INSERT INTO bookings (
                user_id, trainer_id, session_type,
                session_date, start_time, duration,
                location, message, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
            """,
            (
                user["id"],
                id,
                session_type,
                session_date,
                start_time,
                int(duration),
                location,
                message
            )
        )

        # Preserve the existing trainer association
        conn.execute(
            "UPDATE users SET booked_trainer_id=? WHERE id=?",
            (id, user["id"])
        )

        conn.commit()
        conn.close()

        return redirect("/my_bookings")

    conn.close()

    return render_template(
        "book_session.html",
        trainer=trainer
    )

# MY BOOKINGS
@app.route("/my_bookings")
def my_bookings():

    if "user" not in session:
        return redirect("/login")

    conn = get_db()

    user = conn.execute(
        "SELECT * FROM users WHERE username=?",
        (session["user"],)
    ).fetchone()

    if not user:
        conn.close()
        return redirect("/login")

    bookings = conn.execute(
        """
        SELECT bookings.*, trainers.name AS trainer_name
        FROM bookings
        JOIN trainers ON bookings.trainer_id = trainers.id
        WHERE bookings.user_id = ?
        ORDER BY bookings.created_at DESC
        """,
        (user["id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "my_bookings.html",
        bookings=bookings,
        today=date.today().isoformat()
    )


    
    


# CANCEL BOOKING
@app.route("/cancel_booking/<int:booking_id>", methods=["POST"])
def cancel_booking(booking_id):

    if "user" not in session:
        return redirect("/login")

    conn = get_db()

    try:
        user = conn.execute(
            "SELECT * FROM users WHERE username=?",
            (session["user"],)
        ).fetchone()

        if not user:
            return redirect("/login")

        booking = conn.execute(
            """
            SELECT *
            FROM bookings
            WHERE id=? AND user_id=?
            """,
            (booking_id, user["id"])
        ).fetchone()

        if not booking:
            return "Booking not found.", 404

        # Only Pending or Approved bookings can be cancelled
        if booking["status"] not in ["Pending", "Approved"]:
            return redirect("/my_bookings")

        conn.execute(
            """
            UPDATE bookings
            SET status='Cancelled'
            WHERE id=? AND user_id=?
              AND status IN ('Pending', 'Approved')
            """,
            (booking_id, user["id"])
        )

        conn.commit()

        return redirect("/my_bookings")

    finally:
        conn.close()


# REQUEST BOOKING RESCHEDULE
@app.route("/reschedule_booking/<int:booking_id>", methods=["POST"])
def reschedule_booking(booking_id):

    if "user" not in session:
        return redirect("/login")

    conn = get_db()

    try:
        user = conn.execute(
            "SELECT * FROM users WHERE username=?",
            (session["user"],)
        ).fetchone()

        if not user:
            return redirect("/login")

        booking = conn.execute(
            """
            SELECT *
            FROM bookings
            WHERE id=? AND user_id=?
            """,
            (booking_id, user["id"])
        ).fetchone()

        if not booking:
            return "Booking not found.", 404

        if booking["status"] != "Approved":
            return "Only approved bookings can be rescheduled.", 400

        if booking["reschedule_status"] == "Pending":
            return "A reschedule request is already pending.", 400

        # Check the 2-hour rescheduling deadline
        from datetime import datetime, timedelta

        session_start = datetime.strptime(
            booking["session_date"] + " " + booking["start_time"],
            "%Y-%m-%d %H:%M"
        )

        if datetime.now() >= session_start - timedelta(hours=2):
            return (
                "Rescheduling is not allowed within 2 hours "
                "of the session start time.",
                400
            )

        new_date = request.form.get("requested_date", "").strip()
        new_time = request.form.get("requested_time", "").strip()

        try:
            selected_date = datetime.strptime(
                new_date, "%Y-%m-%d"
            ).date()

            datetime.strptime(new_time, "%H:%M")

            if selected_date < datetime.now().date():
                return "Please select today or a future date.", 400

        except ValueError:
            return "Please enter a valid date and time.", 400

        conn.execute(
            """
            UPDATE bookings
            SET requested_date=?,
                requested_time=?,
                reschedule_status='Pending'
            WHERE id=? AND user_id=?
            """,
            (new_date, new_time, booking_id, user["id"])
        )

        conn.commit()

        return redirect("/my_bookings")

    finally:
        conn.close()


# CANCEL SELECTED TRAINER
@app.route("/cancel_trainer", methods=["POST"])
def cancel_trainer():

    if "user" not in session:
        return redirect("/login")

    conn = get_db()

    # Remove the currently selected trainer
    # Payment status remains unchanged
    conn.execute(
        "UPDATE users SET booked_trainer_id=NULL WHERE username=?",
        (session["user"],)
    )

    conn.commit()
    conn.close()

    return redirect("/trainer")


# USER UNREAD MESSAGE COUNT
@app.route("/user_unread_counts")
def user_unread_counts():

    if "user" not in session:
        return {"error": "Unauthorized"}, 401

    conn = get_db()

    try:
        counts = conn.execute(
            """
            SELECT trainer_id, COUNT(*) AS unread_count
            FROM messages
            WHERE user = ?
              AND sender = 'trainer'
              AND is_read = 0
            GROUP BY trainer_id
            """,
            (session["user"],)
        ).fetchall()

        return {
            str(row["trainer_id"]): row["unread_count"]
            for row in counts
        }

    finally:
        conn.close()


# USER CHAT
@app.route("/chat/<int:id>", methods=["GET", "POST"])
def chat(id):

    if "user" not in session:
        return redirect("/login")

    conn = get_db()

    if request.method == "POST":

        # DELETE MESSAGE
        if request.form.get("action") == "delete":

            message_id = request.form.get("message_id")

            if message_id:
                conn.execute(
                    """
                    DELETE FROM messages
                    WHERE id = ?
                    AND trainer_id = ?
                    AND user = ?
                    AND sender = 'user'
                    """,
                    (message_id, id, session["user"])
                )

                conn.commit()

            conn.close()
            return redirect(f"/chat/{id}")

        # SEND MESSAGE
        message = request.form.get("message")
        file = request.files.get("file")
        filename = None

        if file and file.filename != "":
            filename = secure_filename(file.filename)
            file.save(
                os.path.join(app.config["UPLOAD_FOLDER"], filename)
            )

        if (message and message.strip()) or filename:

            conn.execute(
                """
                INSERT INTO messages
                (trainer_id, user, sender, message, file)
                VALUES (?, ?, ?, ?, ?)
                """,
                (id, session["user"], "user", message, filename)
            )

            conn.commit()

    # MARK TRAINER MESSAGES AS READ
    conn.execute(
        """
        UPDATE messages
        SET is_read = 1
        WHERE trainer_id = ?
          AND user = ?
          AND sender = 'trainer'
          AND is_read = 0
        """,
        (id, session["user"])
    )

    conn.commit()

    # GET CHAT MESSAGES
    messages = conn.execute(
        """
        SELECT * FROM messages
        WHERE trainer_id = ? AND user = ?
        ORDER BY sent_at
        """,
        (id, session["user"])
    ).fetchall()

    # GET TRAINER DETAILS
    trainer = conn.execute(
        "SELECT * FROM trainers WHERE id = ?",
        (id,)
    ).fetchone()

    conn.close()

    return render_template(
        "chat.html",
        trainer=trainer,
        messages=messages
    )

# GET UNREAD MESSAGE COUNTS
@app.route("/trainer_unread_counts")
def trainer_unread_counts():

    if "trainer" not in session:
        return {"error": "Unauthorized"}, 401

    conn = get_db()

    try:
        trainer = conn.execute(
            "SELECT * FROM trainers WHERE name = ?",
            (session["trainer"],)
        ).fetchone()

        if not trainer:
            return {"error": "Trainer not found"}, 401

        counts = conn.execute(
            """
            SELECT users.id AS client_id,
                   COUNT(messages.id) AS unread_count
            FROM users
            LEFT JOIN messages
                ON messages.trainer_id = users.booked_trainer_id
                AND messages.user = users.username
                AND messages.sender = 'user'
                AND messages.is_read = 0
            WHERE users.booked_trainer_id = ?
            GROUP BY users.id
            """,
            (trainer["id"],)
        ).fetchall()

        return {
            str(row["client_id"]): row["unread_count"]
            for row in counts
        }

    finally:
        conn.close()




# TRAINER CHAT
@app.route("/trainer_chat/<username>", methods=["GET", "POST"])
def trainer_chat(username):

    if "trainer" not in session:
        return redirect("/trainer_login")

    conn = get_db()

    try:
        # Get logged-in trainer and their profile photo
        trainer = conn.execute(
            "SELECT * FROM trainers WHERE name = ?",
            (session["trainer"],)
        ).fetchone()

        if not trainer:
            session.pop("trainer", None)
            return redirect("/trainer_login")

        # Only allow chat with a client assigned to this trainer
        client = conn.execute(
            """
            SELECT * FROM users
            WHERE username = ? AND booked_trainer_id = ?
            """,
            (username, trainer["id"])
        ).fetchone()

        if not client:
            return redirect("/trainer_dashboard")

        if request.method == "POST":
            message = request.form.get("message", "").strip()
            uploaded_file = request.files.get("file")
            filename = None

            if uploaded_file and uploaded_file.filename:
                safe_name = secure_filename(uploaded_file.filename)

                if safe_name:
                    os.makedirs(
                        app.config["UPLOAD_FOLDER"],
                        exist_ok=True
                    )

                    # Unique prefix helps avoid filename collisions
                    filename = (
                        str(trainer["id"]) + "_"
                        + str(client["id"]) + "_"
                        + safe_name
                    )

                    uploaded_file.save(
                        os.path.join(
                            app.config["UPLOAD_FOLDER"],
                            filename
                        )
                    )

            # Save trainer's message
            if message or filename:
                conn.execute(
                    """
                    INSERT INTO messages
                    (trainer_id, user, sender, message, file)
                    VALUES (?, ?, 'trainer', ?, ?)
                    """,
                    (
                        trainer["id"],
                        username,
                        message,
                        filename
                    )
                )
                conn.commit()

            return redirect(
                url_for("trainer_chat", username=username)
            )

        # Mark client messages as read when trainer opens the chat
        conn.execute(
            """
            UPDATE messages
            SET is_read = 1
            WHERE trainer_id = ?
              AND user = ?
              AND sender = 'user'
              AND is_read = 0
            """,
            (trainer["id"], username)
        )
        conn.commit()

        # Load messages in chronological order
        messages = conn.execute(
            """
            SELECT * FROM messages
            WHERE trainer_id = ? AND user = ?
            ORDER BY sent_at, id
            """,
            (trainer["id"], username)
        ).fetchall()

        return render_template(
            "trainer_chat.html",
            messages=messages,
            username=username,
            trainer=trainer,
            client=client
        )

    finally:
        conn.close()


# RECIPE GENERATOR
@app.route("/recipe_generator", methods=["GET", "POST"])
def recipe_generator():

    recipe = None
    error = None
    image_data = None

    if request.method == "POST":

        ingredients = request.form.get("ingredients", "").strip()

        print("\n====================================")
        print("FORM DATA:", request.form)
        print("INGREDIENTS:", ingredients)
        print("====================================\n")

        if not ingredients:
            error = "Please enter some ingredients."

            return render_template(
                "recipe_generator.html",
                recipe=None,
                error=error,
                user=session.get("user")
            )

        prompt = f"""
You are an AI cooking assistant.

Create a delicious cooking recipe using these ingredients:

{ingredients}

You may use basic ingredients such as salt, pepper, oil, and water when necessary.

Return the recipe using this format:

Recipe Name:
[recipe name]

Ingredients:
- ingredient
- ingredient
- ingredient

Steps:
1. Step one
2. Step two
3. Step three

Cooking Time:
[time]

Make the recipe practical and easy to follow.
"""

        print("\n====================================")
        print("PROMPT SENT TO OLLAMA:")
        print(prompt)
        print("====================================\n")

        try:

            response = requests.post(
                "http://127.0.0.1:11434/api/generate",
                json={
                    "model": "qwen2.5:3b",
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 500
                    }
                },
                timeout=120
            )

            print("OLLAMA STATUS:", response.status_code)
            print("OLLAMA RESPONSE:")
            print(response.text)
            print("====================================\n")

            response.raise_for_status()

            result = response.json()

            recipe = result.get("response", "").strip()

            if recipe:

                recipe_name = ingredients

                for line in recipe.splitlines():

                    if line.lower().startswith("recipe name:"):
                        name = line.split(":", 1)[1].strip()

                        if name:
                            recipe_name = name
                        break

                image_data = get_food_image(recipe_name + " recipe dish food")

            else:

                error = "Ollama returned an empty recipe."
                image_data = None

        except requests.exceptions.ConnectionError:
            error = "Cannot connect to Ollama. Please make sure Ollama is running."

        except requests.exceptions.Timeout:
            error = "Ollama took too long to generate the recipe."

        except requests.exceptions.RequestException as e:
            error = f"Ollama request failed: {e}"

        except Exception as e:
            error = f"Unexpected error: {e}"

    return render_template(
        "recipe_generator.html",
        recipe=recipe,
        error=error,
        user=session.get("user"),
        image_data=image_data
    )


# SAVE RECIPE
@app.route("/save_recipe", methods=["POST"])
def save_recipe():

    if "user" not in session:
        return redirect("/login")

    recipe = request.form["recipe"]

    conn = get_db()

    conn.execute(
        "INSERT INTO saved_recipes(user,recipe) VALUES (?,?)",
        (session["user"], recipe)
    )

    conn.commit()
    conn.close()

    return redirect("/saved_recipes")


# SAVED RECIPES
@app.route("/saved_recipes")
def saved_recipes():

    if "user" not in session:
        return redirect("/login")

    conn = get_db()

    recipes = conn.execute(
        "SELECT * FROM saved_recipes WHERE user=?",
        (session["user"],)
    ).fetchall()

    conn.close()

    return render_template(
        "saved_recipes.html",
        recipes=recipes
    )


# GROCERIES
@app.route("/groceries", methods=["GET", "POST"])
def groceries():

    if "user" not in session:
        return redirect("/login")

    conn = get_db()

    if request.method == "POST":

        item = request.form["item"]

        conn.execute(
            "INSERT INTO groceries(user,item) VALUES(?,?)",
            (session["user"], item)
        )

        conn.commit()

    items = conn.execute(
        "SELECT * FROM groceries WHERE user=?",
        (session["user"],)
    ).fetchall()

    conn.close()

    return render_template(
        "groceries.html",
        items=items
    )

# DELETE GROCERY
@app.route("/delete_grocery/<int:id>", methods=["POST"])
def delete_grocery(id):

    if "user" not in session:
        return redirect("/login")

    conn = get_db()

    conn.execute(
        "DELETE FROM groceries WHERE id=? AND user=?",
        (id, session["user"])
    )

    conn.commit()
    conn.close()

    return redirect("/groceries")


# MEAL PLANNER
@app.route("/meal_planner", methods=["GET", "POST"])
def meal_planner():

    if "user" not in session:
        return redirect("/login")

    conn = get_db()

    if request.method == "POST":

        day = request.form["day"]
        meal_type = request.form["meal_type"]
        meal = request.form["meal"]

        conn.execute(
            "INSERT INTO meal_planner(user,day,meal_type,meal) VALUES(?,?,?,?)",
            (session["user"], day, meal_type, meal)
        )

        conn.commit()

    meals = conn.execute(
        "SELECT * FROM meal_planner WHERE user=? ORDER BY day",
        (session["user"],)
    ).fetchall()

    conn.close()

    return render_template(
        "meal_planner.html",
        meals=meals
    )


# PAYMENT PAGE
@app.route("/payment_page")
def payment_page():

    if "user" not in session:
        return redirect("/login")

    return render_template("payment_page.html")


# ADD REVIEW
@app.route("/add_review/<int:trainer_id>", methods=["POST"])
def add_review(trainer_id):

    if "user" not in session:
        return redirect("/login")

    rating = request.form["rating"]
    feedback = request.form["feedback"]

    conn = get_db()

    conn.execute(
        "INSERT INTO trainer_reviews(trainer_id,user,rating,feedback) VALUES(?,?,?,?)",
        (trainer_id, session["user"], rating, feedback)
    )

    conn.commit()
    conn.close()

    return redirect("/trainer_details/" + str(trainer_id))


# TRAINER DETAILS
@app.route("/trainer_details/<int:id>")
def trainer_details(id):

    conn = get_db()

    trainer = conn.execute(
        "SELECT * FROM trainers WHERE id=?",
        (id,)
    ).fetchone()

    reviews = conn.execute(
        "SELECT * FROM trainer_reviews WHERE trainer_id=? ORDER BY created_at DESC",
        (id,)
    ).fetchall()

    conn.close()

    return render_template(
        "trainer_details.html",
        trainer=trainer,
        reviews=reviews
    )


# TRAINER REVIEWS
@app.route("/trainer_reviews")
def trainer_reviews():

    if "trainer" not in session:
        return redirect("/trainer_login")

    conn = get_db()

    trainer = conn.execute(
        "SELECT * FROM trainers WHERE name=?",
        (session["trainer"],)
    ).fetchone()

    reviews = conn.execute(
        "SELECT * FROM trainer_reviews WHERE trainer_id=? ORDER BY created_at DESC",
        (trainer["id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "trainer_reviews.html",
        reviews=reviews
    )


# ADMIN LOGIN
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()

        admin = conn.execute(
            "SELECT * FROM admin WHERE username=? AND password=?",
            (username, password)
        ).fetchone()

        conn.close()

        if admin:
            session["admin"] = username
            return redirect("/admin_dashboard")

        return "Invalid admin login"

    return render_template("admin_login.html")


# ADMIN DASHBOARD
@app.route("/admin_dashboard")
def admin_dashboard():

    if "admin" not in session:
        return redirect("/admin_login")

    return render_template("admin_dashboard.html")





# ADMIN USERS
@app.route("/admin_users")
def admin_users():

    if "admin" not in session:
        return redirect("/admin_login")

    conn = get_db()

    users = conn.execute(
        "SELECT * FROM users"
    ).fetchall()

    conn.close()

    return render_template(
        "admin_users.html",
        users=users
    )

# ADMIN VIEW USER PROFILE
@app.route("/admin_user/<int:id>")
def admin_user(id):

    # Only admin can view user profiles
    if "admin" not in session:
        return redirect("/admin_login")

    conn = get_db()

    # Get selected user
    user = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (id,)
    ).fetchone()

    # User does not exist
    if not user:
        conn.close()
        return redirect("/admin_users")

    # Get assigned trainer if the user has one
    trainer = None

    if user["booked_trainer_id"]:

        trainer = conn.execute(
            "SELECT * FROM trainers WHERE id=?",
            (user["booked_trainer_id"],)
        ).fetchone()

    conn.close()

    return render_template(
        "admin_user_profile.html",
        user=user,
        trainer=trainer
    )


# DELETE USER

@app.route("/delete_user/<int:id>", methods=["POST"])
def delete_user(id):

    if "admin" not in session:
        return redirect("/admin_login")

    conn = get_db()

    conn.execute(
        "DELETE FROM users WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/admin_users")


# ADMIN TRAINERS LIST

@app.route("/admin_trainers_list")
def admin_trainers_list():

    if "admin" not in session:
        return redirect("/admin_login")

    conn = get_db()

    trainers = conn.execute(
        "SELECT * FROM trainers"
    ).fetchall()

    conn.close()

    return render_template(
        "admin_trainers_list.html",
        trainers=trainers
    )

# ADMIN VIEW TRAINER PROFILE
@app.route("/admin_trainer/<int:id>")
def admin_trainer(id):

    # Only admin can view trainer profiles
    if "admin" not in session:
        return redirect("/admin_login")

    conn = get_db()

    trainer = conn.execute(
        "SELECT * FROM trainers WHERE id=?",
        (id,)
    ).fetchone()

    conn.close()

    if not trainer:
        return redirect("/admin_trainers_list")

    return render_template(
        "admin_trainer_profile.html",
        trainer=trainer
    )


# DELETE TRAINER

@app.route("/delete_trainer/<int:id>", methods=["POST"])
def delete_trainer(id):

    # Check whether admin is logged in
    if "admin" not in session:
        return redirect("/admin_login")

    # Connect to database
    conn = get_db()

    # Delete the selected trainer
    conn.execute(
        "DELETE FROM trainers WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    # Return to trainer list
    return redirect("/admin_trainers_list")

# ADMIN REVIEWS

@app.route("/admin_reviews")
def admin_reviews():

    # Check whether admin is logged in
    if "admin" not in session:
        return redirect("/admin_login")

    # Connect to database
    conn = get_db()

    # Fetch all trainer reviews
    reviews = conn.execute(
        "SELECT * FROM trainer_reviews"
    ).fetchall()

    conn.close()

    # Display reviews on admin page
    return render_template(
        "admin_reviews.html",
        reviews=reviews
    )



# DELETE REVIEW

@app.route("/delete_review/<int:id>", methods=["POST"])
def delete_review(id):

    # Check whether admin is logged in
    if "admin" not in session:
        return redirect("/admin_login")

    # Connect to database
    conn = get_db()

    # Delete the selected review
    conn.execute(
        "DELETE FROM trainer_reviews WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    # Return to admin reviews page
    return redirect("/admin_reviews")


# ROUTES
@app.route("/logout")
def logout():

    if "trainer" in session:
        session.pop("trainer", None)
        return redirect("/trainer_login")

    if "admin" in session:
        session.pop("admin", None)
        return redirect("/admin_login")

    if "user" in session:
        session.pop("user", None)
        return redirect("/login")

    return redirect("/login")

# ADMIN TRAINER PAYOUTS
@app.route("/admin_payouts", methods=["GET", "POST"])
def admin_payouts():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db()

    if request.method == "POST":
        trainer_id = request.form.get("trainer_id", type=int)
        amount = request.form.get("amount", type=float)
        payment_reference = request.form.get("payment_reference", "").strip()
        note = request.form.get("note", "").strip()

        if not trainer_id or not amount or amount <= 0:
            conn.close()
            return "Please enter a valid trainer and amount.", 400

        trainer = conn.execute(
            "SELECT id FROM trainers WHERE id = ?",
            (trainer_id,)
        ).fetchone()

        if not trainer:
            conn.close()
            return "Trainer not found.", 404

        amount_paise = round(amount * 100)

        conn.execute("""
            INSERT INTO trainer_payouts
            (trainer_id, amount_paise, payment_reference, note, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, (
            trainer_id,
            amount_paise,
            payment_reference,
            note,
            session["admin"]
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("admin_payouts"))

    trainers = conn.execute(
        "SELECT id, name, email FROM trainers ORDER BY name"
    ).fetchall()

    payouts = conn.execute("""
        SELECT p.*, t.name AS trainer_name
        FROM trainer_payouts p
        JOIN trainers t ON p.trainer_id = t.id
        ORDER BY p.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admin_payouts.html",
        trainers=trainers,
        payouts=payouts
    )


# TRAINER PAYOUT HISTORY PAGE
@app.route("/trainer_payout_history")
def trainer_payout_history():
    if "trainer" not in session:
        return redirect("/trainer_login")

    conn = get_db()

    trainer = conn.execute(
        "SELECT * FROM trainers WHERE name = ?",
        (session["trainer"],)
    ).fetchone()

    if not trainer:
        conn.close()
        session.pop("trainer", None)
        return redirect("/trainer_login")

    payouts = conn.execute("""
        SELECT id, amount_paise, payment_reference, note, status, paid_at
        FROM trainer_payouts
        WHERE trainer_id = ?
        ORDER BY id DESC
    """, (trainer["id"],)).fetchall()

    conn.close()

    return render_template(
        "trainer_payout_history.html",
        trainer=trainer,
        payouts=payouts
    )






if __name__ == "__main__":
    app.run(debug=True)