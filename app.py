import sqlite3
import random
import time
import smtplib

from email.message import EmailMessage

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    session
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from config import (
    GMAIL_EMAIL,
    GMAIL_APP_PASSWORD,
    FLASK_SECRET_KEY
)


# =========================================
# APP CONFIGURATION
# =========================================

app = Flask(__name__)

app.secret_key = FLASK_SECRET_KEY

DATABASE = "nexra.db"

CODE_EXPIRATION_SECONDS = 300


# =========================================
# TEMPORARY VERIFICATION DATA
# =========================================

verification_codes = {}

verified_emails = set()


# =========================================
# EMAIL SEND COOLDOWN
# =========================================

SEND_COOLDOWN_SECONDS = 60

last_code_sent = {}


# =========================================
# DATABASE CONNECTION
# =========================================

def get_db_connection():

    connection = sqlite3.connect(DATABASE)

    connection.row_factory = sqlite3.Row

    return connection


# =========================================
# DATABASE INITIALIZATION
# =========================================

def init_db():

    connection = get_db_connection()

    cursor = connection.cursor()


    # =====================================
    # CREATE STUDENTS TABLE
    # =====================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            email TEXT NOT NULL,

            name TEXT NOT NULL,

            grade TEXT NOT NULL,

            language TEXT NOT NULL,

            password_hash TEXT,

            email_verified INTEGER DEFAULT 0,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP

        )
    """)


    # =====================================
    # DATABASE MIGRATION
    # =====================================

    cursor.execute("""
        PRAGMA table_info(students)
    """)

    columns = [
        column["name"]
        for column in cursor.fetchall()
    ]


    # Add password_hash if database is old

    if "password_hash" not in columns:

        cursor.execute("""
            ALTER TABLE students
            ADD COLUMN password_hash TEXT
        """)

        print("--------------------------------")
        print("DATABASE MIGRATION")
        print("Added: password_hash")
        print("--------------------------------")


    # Add email_verified if database is old

    if "email_verified" not in columns:

        cursor.execute("""
            ALTER TABLE students
            ADD COLUMN email_verified INTEGER DEFAULT 0
        """)

        print("--------------------------------")
        print("DATABASE MIGRATION")
        print("Added: email_verified")
        print("--------------------------------")


    connection.commit()

    connection.close()


# Initialize database

init_db()


# =========================================
# HOME
# =========================================

@app.route("/")
def home():

    return render_template("index.html")


# =========================================
# EMAIL VERIFICATION EMAIL
# =========================================

def send_verification_email(
    recipient_email,
    verification_code
):

    message = EmailMessage()

    message["From"] = (
        f"Nexra Education <{GMAIL_EMAIL}>"
    )

    message["To"] = recipient_email

    message["Subject"] = (
        "Nexra Education - Email Verification"
    )


    # =====================================
    # EMAIL CONTENT
    # =====================================

    html_content = f"""
    <div
        style="
            font-family: Arial, sans-serif;
            max-width: 500px;
            margin: auto;
            padding: 20px;
            background: #FAF8F6;
            border-radius: 12px;
        "
    >

        <h2 style="color: #3E2723;">
            Welcome to Nexra Education 🎓
        </h2>

        <p>
            Your Nexra verification code is:
        </p>

        <h1
            style="
                letter-spacing: 8px;
                font-size: 32px;
                color: #6D4C41;
            "
        >
            {verification_code}
        </h1>

        <p>
            This code will expire in
            <strong>5 minutes</strong>.
        </p>

        <p>
            If you did not request this code,
            you can safely ignore this email.
        </p>

        <hr>

        <p style="color: #806F69;">
            Nexra Education
        </p>

    </div>
    """


    # =====================================
    # PLAIN TEXT VERSION
    # =====================================

    plain_text = f"""
Welcome to Nexra Education!

Your verification code is:

{verification_code}

This code will expire in 5 minutes.

If you did not request this code,
you can ignore this email.

Nexra Education
    """


    message.set_content(plain_text)

    message.add_alternative(
        html_content,
        subtype="html"
    )


    # =====================================
    # CONNECT TO GMAIL SMTP
    # =====================================

    with smtplib.SMTP(
        "smtp.gmail.com",
        587,
        timeout=30
    ) as server:

        server.ehlo()

        server.starttls()

        server.ehlo()

        server.login(
            GMAIL_EMAIL,
            GMAIL_APP_PASSWORD
        )

        server.send_message(message)


# =========================================
# SEND VERIFICATION CODE
# =========================================

@app.route(
    "/send-code",
    methods=["POST"]
)
def send_code():

    data = request.get_json(
        silent=True
    )


    if not data:

        return jsonify({
            "message":
                "Invalid request."
        }), 400


    email = data.get(
        "email",
        ""
    ).strip().lower()


    # =====================================
    # VALIDATE EMAIL
    # =====================================

    if not email:

        return jsonify({
            "message":
                "Email is required."
        }), 400


    # =====================================
    # CHECK IF ALREADY REGISTERED
    # =====================================

    connection = get_db_connection()

    cursor = connection.cursor()


    cursor.execute("""
        SELECT id
        FROM students
        WHERE email = ?
        LIMIT 1
    """, (email,))


    existing_student = cursor.fetchone()

    connection.close()


    if existing_student:

        return jsonify({
            "message":
                "This email is already registered."
        }), 409


    # =====================================
    # CHECK SEND COOLDOWN
    # =====================================

    current_time = time.time()

    last_sent_time = last_code_sent.get(email)

    if last_sent_time is not None:

        elapsed_time = (
            current_time - last_sent_time
        )

        if elapsed_time < SEND_COOLDOWN_SECONDS:

            remaining_seconds = int(
                SEND_COOLDOWN_SECONDS - elapsed_time
            )

            if remaining_seconds < 1:
                remaining_seconds = 1


            return jsonify({

                "message":
                    f"Please wait {remaining_seconds} seconds before requesting another code.",

                "cooldown":
                    True,

                "remaining_seconds":
                    remaining_seconds

            }), 429


    # =====================================
    # GENERATE 6-DIGIT CODE
    # =====================================

    code = str(
        random.randint(
            100000,
            999999
        )
    )


    # Save the time of the last code request

    last_code_sent[email] = time.time()


    expires_at = (
        time.time()
        + CODE_EXPIRATION_SECONDS
    )


    # =====================================
    # SAVE VERIFICATION DATA
    # =====================================

    verification_codes[email] = {

        "code":
            code,

        "expires_at":
            expires_at

    }


    # =====================================
    # SEND EMAIL
    # =====================================

    try:

        send_verification_email(
            email,
            code
        )


        print("--------------------------------")
        print("NEXRA VERIFICATION EMAIL SENT")
        print("To:", email)
        print("Code:", code)
        print("--------------------------------")


    except Exception as error:

        print("--------------------------------")
        print("EMAIL SENDING ERROR")
        print(error)
        print("--------------------------------")


        # Remove code if email failed

        verification_codes.pop(
            email,
            None
        )


        # Remove cooldown if email failed

        last_code_sent.pop(
            email,
            None
        )


        return jsonify({
            "message":
                "Could not send verification email."
        }), 500


    return jsonify({

        "message":
            "Verification code sent to your email.",

        "expires_in":
            CODE_EXPIRATION_SECONDS,

        "cooldown_seconds":
            SEND_COOLDOWN_SECONDS

    }), 200


# =========================================
# VERIFY EMAIL CODE
# =========================================

@app.route(
    "/verify-code",
    methods=["POST"]
)
def verify_code():

    data = request.get_json(
        silent=True
    )


    if not data:

        return jsonify({
            "message":
                "Invalid request."
        }), 400


    email = data.get(
        "email",
        ""
    ).strip().lower()


    code = data.get(
        "code",
        ""
    ).strip()


    # =====================================
    # VALIDATE DATA
    # =====================================

    if not email or not code:

        return jsonify({
            "message":
                "Email and code are required."
        }), 400


    # =====================================
    # CHECK CODE EXISTS
    # =====================================

    if email not in verification_codes:

        return jsonify({
            "message":
                "No verification code was requested."
        }), 400


    saved_data = verification_codes[email]


    # =====================================
    # CHECK EXPIRATION
    # =====================================

    if time.time() > saved_data["expires_at"]:

        del verification_codes[email]


        return jsonify({
            "message":
                "Verification code expired."
        }), 400


    # =====================================
    # CHECK CODE
    # =====================================

    if code != saved_data["code"]:

        return jsonify({
            "message":
                "Invalid verification code."
        }), 400


    # =====================================
    # VERIFICATION SUCCESSFUL
    # =====================================

    del verification_codes[email]


    verified_emails.add(email)


    print("--------------------------------")
    print("EMAIL VERIFIED")
    print("Email:", email)
    print("--------------------------------")


    return jsonify({

        "message":
            "Email verified successfully!",

        "verified":
            True

    }), 200


# =========================================
# REGISTER STUDENT
# =========================================

@app.route(
    "/register",
    methods=["POST"]
)
def register():

    data = request.get_json(
        silent=True
    )


    if not data:

        return jsonify({
            "message":
                "Invalid request."
        }), 400


    email = data.get(
        "email",
        ""
    ).strip().lower()


    name = data.get(
        "name",
        ""
    ).strip()


    grade = data.get(
        "grade",
        ""
    ).strip()


    language = data.get(
        "language",
        "ar"
    ).strip()


    password = data.get(
        "password",
        ""
    )


    # =====================================
    # REQUIRED FIELDS
    # =====================================

    if not email or not name or not grade:

        return jsonify({
            "message":
                "Please complete all required fields."
        }), 400


    # =====================================
    # PASSWORD REQUIRED
    # =====================================

    if not password:

        return jsonify({
            "message":
                "Password is required."
        }), 400


    # =====================================
    # PASSWORD LENGTH
    # =====================================

    if len(password) < 8:

        return jsonify({
            "message":
                "Password must be at least 8 characters."
        }), 400


    # =====================================
    # CHECK EMAIL VERIFICATION
    # =====================================

    if email not in verified_emails:

        return jsonify({
            "message":
                "Email must be verified before creating an account."
        }), 403


    # =====================================
    # DATABASE CONNECTION
    # =====================================

    connection = get_db_connection()

    cursor = connection.cursor()


    # =====================================
    # CHECK EXISTING ACCOUNT
    # =====================================

    cursor.execute("""
        SELECT id
        FROM students
        WHERE email = ?
        LIMIT 1
    """, (email,))


    existing_student = cursor.fetchone()


    if existing_student:

        connection.close()


        verified_emails.discard(email)


        return jsonify({
            "message":
                "This email is already registered."
        }), 409


    # =====================================
    # HASH PASSWORD
    # =====================================

    password_hash = generate_password_hash(
        password
    )


    # =====================================
    # SAVE STUDENT
    # =====================================

    cursor.execute("""
        INSERT INTO students
        (
            email,
            name,
            grade,
            language,
            password_hash,
            email_verified
        )

        VALUES (?, ?, ?, ?, ?, ?)
    """, (

        email,

        name,

        grade,

        language,

        password_hash,

        1

    ))


    connection.commit()


    student_id = cursor.lastrowid


    connection.close()


    # =====================================
    # REMOVE VERIFICATION STATE
    # =====================================

    verified_emails.discard(email)


    # =====================================
    # SERVER LOG
    # =====================================

    print("--------------------------------")
    print("NEW NEXRA EDUCATION STUDENT")
    print("ID:", student_id)
    print("Name:", name)
    print("Email:", email)
    print("Grade:", grade)
    print("Language:", language)
    print("Email Verified: YES")
    print("Password: HASHED")
    print("--------------------------------")


    # =====================================
    # RESPONSE
    # =====================================

    return jsonify({

        "message":
            "Registration successful!",

        "student_id":
            student_id,

        "name":
            name,

        "verified":
            True

    }), 201


# =========================================
# LOGIN
# =========================================

@app.route(
    "/login",
    methods=["POST"]
)
def login():

    data = request.get_json(
        silent=True
    )


    # =====================================
    # VALIDATE REQUEST
    # =====================================

    if not data:

        return jsonify({
            "message":
                "Invalid request."
        }), 400


    email = data.get(
        "email",
        ""
    ).strip().lower()


    password = data.get(
        "password",
        ""
    )


    # =====================================
    # REQUIRED FIELDS
    # =====================================

    if not email or not password:

        return jsonify({
            "message":
                "Email and password are required."
        }), 400


    # =====================================
    # FIND STUDENT
    # =====================================

    connection = get_db_connection()

    cursor = connection.cursor()


    cursor.execute("""
        SELECT
            id,
            email,
            name,
            grade,
            language,
            password_hash,
            email_verified
        FROM students
        WHERE email = ?
        LIMIT 1
    """, (email,))


    student = cursor.fetchone()

    connection.close()


    # =====================================
    # ACCOUNT NOT FOUND
    # =====================================

    if not student:

        return jsonify({
            "message":
                "Invalid email or password."
        }), 401


    # =====================================
    # CHECK PASSWORD HASH
    # =====================================

    password_hash = student["password_hash"]


    if not password_hash:

        return jsonify({
            "message":
                "This account does not have a valid password."
        }), 401


    if not check_password_hash(
        password_hash,
        password
    ):

        return jsonify({
            "message":
                "Invalid email or password."
        }), 401


    # =====================================
    # CHECK EMAIL VERIFICATION
    # =====================================

    if not student["email_verified"]:

        return jsonify({
            "message":
                "This email has not been verified."
        }), 403


    # =====================================
    # CREATE LOGIN SESSION
    # =====================================

    session.clear()


    session["student_id"] = student["id"]

    session["student_email"] = student["email"]

    session["student_name"] = student["name"]

    session["student_grade"] = student["grade"]

    session["student_language"] = student["language"]


    # =====================================
    # SERVER LOG
    # =====================================

    print("--------------------------------")
    print("NEXRA EDUCATION LOGIN")
    print("ID:", student["id"])
    print("Email:", student["email"])
    print("Name:", student["name"])
    print("Login: SUCCESS")
    print("--------------------------------")


    # =====================================
    # RESPONSE
    # =====================================

    return jsonify({

        "message":
            "Login successful.",

        "logged_in":
            True,

        "student": {

            "id":
                student["id"],

            "email":
                student["email"],

            "name":
                student["name"],

            "grade":
                student["grade"],

            "language":
                student["language"]

        }

    }), 200


# =========================================
# CURRENT LOGGED-IN STUDENT
# =========================================

@app.route(
    "/me",
    methods=["GET"]
)
def current_student():

    # =====================================
    # CHECK LOGIN
    # =====================================

    if "student_id" not in session:

        return jsonify({

            "logged_in":
                False

        }), 401


    # =====================================
    # RETURN SESSION DATA
    # =====================================

    return jsonify({

        "logged_in":
            True,

        "student": {

            "id":
                session["student_id"],

            "email":
                session["student_email"],

            "name":
                session["student_name"],

            "grade":
                session["student_grade"],

            "language":
                session["student_language"]

        }

    }), 200


# =========================================
# LOGOUT
# =========================================

@app.route(
    "/logout",
    methods=["POST"]
)
def logout():

    student_name = session.get(
        "student_name",
        "Unknown"
    )


    session.clear()


    print("--------------------------------")
    print("NEXRA EDUCATION LOGOUT")
    print("Student:", student_name)
    print("Logout: SUCCESS")
    print("--------------------------------")


    return jsonify({

        "message":
            "Logged out successfully.",

        "logged_out":
            True

    }), 200


# =========================================
# PROTECTED TEST ROUTE
# =========================================

@app.route(
    "/dashboard-data",
    methods=["GET"]
)
def dashboard_data():

    # =====================================
    # CHECK LOGIN
    # =====================================

    if "student_id" not in session:

        return jsonify({

            "message":
                "Login required.",

            "logged_in":
                False

        }), 401


    # =====================================
    # RETURN BASIC DASHBOARD DATA
    # =====================================

    return jsonify({

        "logged_in":
            True,

        "student": {

            "id":
                session["student_id"],

            "name":
                session["student_name"],

            "email":
                session["student_email"],

            "grade":
                session["student_grade"],

            "language":
                session["student_language"]

        }

    }), 200


# =========================================
# RUN SERVER
# =========================================

if __name__ == "__main__":

    import os

    host = os.getenv(
        "HOST",
        "127.0.0.1"
    )

    port = int(
        os.getenv(
            "PORT",
            "5000"
        )
    )

    debug = os.getenv(
        "FLASK_DEBUG",
        "0"
    ) == "1"


    print("")
    print("========================================")
    print("      NEXRA EDUCATION BACKEND")
    print("========================================")
    print("Database:", DATABASE)
    print("Server:", f"http://{host}:{port}")
    print("Email:", GMAIL_EMAIL)
    print("Email Service: Gmail SMTP")
    print("Authentication: Login + Session")
    print("Debug:", debug)
    print("Status: READY")
    print("========================================")
    print("")


    app.run(
        host=host,
        port=port,
        debug=debug
    )