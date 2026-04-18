<<<<<<< HEAD
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
import os, random, time, jwt as pyjwt
from datetime import datetime, timedelta, timezone
from functools import wraps

db   = SQLAlchemy()
mail = Mail()

# In-memory store: { email: { code, expires_at } }
verification_store = {}

# In-memory user store (until you wire up the real DB models)
# Structure: { email: { password_hash, name, role, is_verified } }
users_store = {}

def create_app():
    app = Flask(__name__)

    # ── Database ──────────────────────────────────────────────
    local_db_url = "postgresql://md.abrarhossainzahin@localhost:5432/jobhive_db"
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", local_db_url)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ── Email ─────────────────────────────────────────────────
    app.config['MAIL_SERVER']         = os.environ.get('EMAIL_HOST', 'smtp-relay.brevo.com')
    app.config['MAIL_PORT']           = int(os.environ.get('EMAIL_PORT', 587))
    app.config['MAIL_USE_TLS']        = True
    app.config['MAIL_USERNAME']       = os.environ.get('EMAIL_USER')
    app.config['MAIL_PASSWORD']       = os.environ.get('EMAIL_PASS')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('EMAIL_FROM')

    # ── JWT secret ────────────────────────────────────────────
    app.config['JWT_SECRET'] = os.environ.get('JWT_SECRET_KEY', 'dev-secret-change-in-prod')

    db.init_app(app)
    mail.init_app(app)

    CORS(app,
         resources={r"/api/*": {"origins": "http://localhost:5173"}},
         supports_credentials=True)

    # ── JWT helper ────────────────────────────────────────────
    def make_token(email: str, role: str) -> str:
        payload = {
            "email": email,
            "role":  role,
            "exp":   datetime.now(timezone.utc) + timedelta(days=7)
        }
        return pyjwt.encode(payload, app.config['JWT_SECRET'], algorithm="HS256")

    def token_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                return jsonify({"success": False, "error": "Missing token"}), 401
            try:
                token   = auth.split(" ")[1]
                payload = pyjwt.decode(token, app.config['JWT_SECRET'], algorithms=["HS256"])
                request.current_user = payload
            except pyjwt.ExpiredSignatureError:
                return jsonify({"success": False, "error": "Token expired"}), 401
            except pyjwt.InvalidTokenError:
                return jsonify({"success": False, "error": "Invalid token"}), 401
            return f(*args, **kwargs)
        return decorated

    # ═══════════════════════════════════════════════════════════
    # ROUTE 1 — Send verification code
    # ═══════════════════════════════════════════════════════════
    @app.route("/api/send-verification-code", methods=["POST", "OPTIONS"])
    def send_code():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        data  = request.get_json()
        email = data.get("email")

        if not email:
            return jsonify({"success": False, "error": "Email is required"}), 400

        code = str(random.randint(100000, 999999))
        verification_store[email] = {
            "code":       code,
            "expires_at": time.time() + 600
        }
        print(f"[DEBUG] Stored code {code} for {email}")

        try:
            msg = Message(
                subject="Your JobHive Verification Code",
                recipients=[email],
                body=(
                    f"Your JobHive verification code is: {code}\n\n"
                    f"This code expires in 10 minutes.\n"
                    f"If you did not request this, ignore this email."
                )
            )
            mail.send(msg)
            print(f"[SUCCESS] Email sent to {email}")
            return jsonify({"success": True, "message": "Code sent successfully!"}), 200

        except Exception as e:
            verification_store.pop(email, None)
            print(f"[SMTP ERROR] {str(e)}")
            return jsonify({
                "success": False,
                "error":   "Failed to send email",
                "details": str(e)
            }), 500

    # ═══════════════════════════════════════════════════════════
    # ROUTE 2 — Verify the code
    # ═══════════════════════════════════════════════════════════
    @app.route("/api/verify-email", methods=["POST", "OPTIONS"])
    def verify_email():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        data           = request.get_json()
        email          = data.get("email")
        submitted_code = data.get("code")

        print(f"[DEBUG] Verify attempt — email: {email}, code: {submitted_code}")

        if email not in verification_store:
            return jsonify({
                "success": False,
                "error":   "No code found for this email. Please request a new one."
            }), 400

        record = verification_store[email]

        if time.time() > record["expires_at"]:
            verification_store.pop(email, None)
            return jsonify({
                "success": False,
                "error":   "Code has expired. Please request a new one."
            }), 400

        if submitted_code != record["code"]:
            print(f"[FAIL] Wrong code. Expected {record['code']}, got {submitted_code}")
            return jsonify({
                "success": False,
                "error":   "Incorrect code. Please try again."
            }), 400

        # Mark email as verified but don't delete — register route checks this
        verification_store[email]["verified"] = True
        print(f"[SUCCESS] {email} verified")

        return jsonify({
            "success":    True,
            "message":    "Email verified successfully!",
            "email":      email,
            "isVerified": True
        }), 200

    # ═══════════════════════════════════════════════════════════
    # ROUTE 3 — Register  ← THIS WAS MISSING
    # ═══════════════════════════════════════════════════════════
    @app.route("/api/register", methods=["POST", "OPTIONS"])
    def register():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        data     = request.get_json()
        email    = data.get("email", "").strip().lower()
        password = data.get("password", "")
        name     = data.get("name", "").strip()
        role     = data.get("role", "job_seeker")   # "job_seeker" | "employer"

        print(f"[DEBUG] Register attempt for {email}, role={role}")

        # Validation
        if not email or not password or not name:
            return jsonify({
                "success": False,
                "error":   "Name, email, and password are required."
            }), 400

        if email in users_store:
            return jsonify({
                "success": False,
                "error":   "An account with this email already exists."
            }), 409

        # Check that the email was verified
        record = verification_store.get(email)
        if not record or not record.get("verified"):
            return jsonify({
                "success": False,
                "error":   "Email not verified. Please complete verification first."
            }), 403

        # Save user
        users_store[email] = {
            "name":          name,
            "email":         email,
            "password_hash": generate_password_hash(password),
            "role":          role,
            "is_verified":   True,
            "created_at":    datetime.now(timezone.utc).isoformat()
        }

        # Clean up verification store
        verification_store.pop(email, None)

        token = make_token(email, role)
        print(f"[SUCCESS] Registered user {email} as {role}")

        return jsonify({
            "success": True,
            "message": "Account created successfully!",
            "token":   token,
            "user": {
                "name":       name,
                "email":      email,
                "role":       role,
                "isVerified": True
            }
        }), 201

    # ═══════════════════════════════════════════════════════════
    # ROUTE 4 — Login
    # ═══════════════════════════════════════════════════════════
    @app.route("/api/login", methods=["POST", "OPTIONS"])
    def login():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        data     = request.get_json()
        email    = data.get("email", "").strip().lower()
        password = data.get("password", "")

        user = users_store.get(email)

        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({
                "success": False,
                "error":   "Invalid email or password."
            }), 401

        token = make_token(email, user["role"])
        print(f"[SUCCESS] Login for {email}")

        return jsonify({
            "success": True,
            "token":   token,
            "user": {
                "name":       user["name"],
                "email":      email,
                "role":       user["role"],
                "isVerified": True
            }
        }), 200

    # ═══════════════════════════════════════════════════════════
    # ROUTE 5 — Get current user (protected)
    # ═══════════════════════════════════════════════════════════
    @app.route("/api/user/me", methods=["GET"])
    @token_required
    def get_me():
        email = request.current_user["email"]
        user  = users_store.get(email)
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404
        return jsonify({
            "success": True,
            "user": {
                "name":       user["name"],
                "email":      email,
                "role":       user["role"],
                "isVerified": user["is_verified"]
            }
        }), 200

    # ═══════════════════════════════════════════════════════════
    # ROUTE 6 — Jobs list (was 404 in your logs)
    # ═══════════════════════════════════════════════════════════
    @app.route("/api/jobs", methods=["GET"])
    def get_jobs():
        # Placeholder data until your DB models are wired up
        sample_jobs = [
            {
                "id":          1,
                "title":       "Frontend Developer",
                "company":     "TechCorp BD",
                "location":    "Dhaka",
                "type":        "Full-time",
                "skills":      ["React", "TypeScript", "Tailwind"],
                "posted_at":   "2026-04-18"
            },
            {
                "id":          2,
                "title":       "Data Analyst Intern",
                "company":     "DataMind",
                "location":    "Remote",
                "type":        "Internship",
                "skills":      ["Python", "SQL", "Power BI"],
                "posted_at":   "2026-04-17"
            },
        ]
        return jsonify({
            "success": True,
            "jobs":    sample_jobs,
            "total":   len(sample_jobs)
        }), 200

    @app.route("/api/hello", methods=["GET"])
    def hello():
        return jsonify({"message": "Hello from Flask!"}), 200

    return app

=======
from app import create_app
import os
>>>>>>> a0174eb1882d98f6fb0670cc5f8547e5b6cbe316

app = create_app()

if __name__ == "__main__":
<<<<<<< HEAD
    app.run(debug=True, port=8000)
=======
    # Get port from environment variable (for Render) or default to 8000
    port = int(os.environ.get('PORT', 8000))
    # Disable debug mode in production
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    # Bind to 0.0.0.0 for external access (required for Render)
    app.run(host='0.0.0.0', debug=debug_mode, port=port)
    

>>>>>>> a0174eb1882d98f6fb0670cc5f8547e5b6cbe316
