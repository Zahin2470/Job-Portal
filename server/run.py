from flask import Flask, request, jsonify, g
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
import os, random, time, jwt as pyjwt
from datetime import datetime, timedelta, timezone
from functools import wraps

db   = SQLAlchemy()
mail = Mail()

# Only verification codes stay in memory (short-lived by design)
verification_store = {}

def create_app():
    app = Flask(__name__)

    # ── Database ──────────────────────────────────────────────
    # Using the postgres superuser and lowercase database name as verified in your setup
    app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://postgres@localhost:5432/jobhive_db"

    # ── JWT ───────────────────────────────────────────────────
    app.config['JWT_SECRET'] = os.environ.get('JWT_SECRET_KEY', 'dev-secret-change-in-prod')

    # ── Email ─────────────────────────────────────────────────
    app.config['MAIL_SERVER']         = os.environ.get('EMAIL_HOST', 'smtp-relay.brevo.com')
    app.config['MAIL_PORT']           = int(os.environ.get('EMAIL_PORT', 587))
    app.config['MAIL_USE_TLS']        = True
    app.config['MAIL_USERNAME']       = os.environ.get('EMAIL_USER')
    app.config['MAIL_PASSWORD']       = os.environ.get('EMAIL_PASS')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('EMAIL_FROM')

    # ── Initialize Extensions ─────────────────────────────────
    db.init_app(app)
    mail.init_app(app)

    # 3. CORS - This must match your frontend port (5173)
    CORS(app, resources={r"/api/*": {"origins": "http://localhost:5173"}}, supports_credentials=True)

    # ════════════════════════════════════════════════════════════
    # DATABASE MODELS — persisted to PostgreSQL, survive restarts
    # ════════════════════════════════════════════════════════════
    class User(db.Model):
        __tablename__ = "users"
        id            = db.Column(db.Integer, primary_key=True)
        email         = db.Column(db.String(255), unique=True, nullable=False)
        name          = db.Column(db.String(255), nullable=False)
        password_hash = db.Column(db.String(512), nullable=False)
        role          = db.Column(db.String(50),  nullable=False, default="job_seeker")
        is_verified   = db.Column(db.Boolean,     default=False)
        created_at    = db.Column(db.DateTime,    default=datetime.utcnow)

        # Profile fields
        title       = db.Column(db.String(255), default="")
        bio         = db.Column(db.Text,         default="")
        phone       = db.Column(db.String(50),   default="")
        location    = db.Column(db.String(255),  default="")
        website     = db.Column(db.String(255),  default="")
        skills      = db.Column(db.JSON,         default=list)
        education   = db.Column(db.JSON,         default=list)
        cv_url      = db.Column(db.String(512),  default="")
        profile_pic = db.Column(db.String(512),  default="")

        # Employer fields
        company_name = db.Column(db.String(255), default="")
        industry     = db.Column(db.String(255), default="")
        company_size = db.Column(db.String(100), default="")
        description  = db.Column(db.Text,        default="")
        logo_url     = db.Column(db.String(512),  default="")

        jobs         = db.relationship("Job", back_populates="employer",
                                    cascade="all, delete-orphan")

        def to_dict(self):
            return {
                "id":           self.id,
                "email":        self.email,
                "name":         self.name,
                "role":         self.role,
                "isVerified":   self.is_verified,
                "title":        self.title,
                "bio":          self.bio,
                "phone":        self.phone,
                "location":     self.location,
                "website":      self.website,
                "skills":       self.skills or [],
                "education":    self.education or [],
                "cv_url":       self.cv_url,
                "profilePicture": self.profile_pic,
                "company_name": self.company_name,
                "logo_url":     self.logo_url,
            }

    class Job(db.Model):
        __tablename__ = "jobs"
        id          = db.Column(db.Integer, primary_key=True)
        title       = db.Column(db.String(255), nullable=False)
        company     = db.Column(db.String(255), nullable=False)
        location    = db.Column(db.String(255), nullable=False)
        job_type    = db.Column(db.String(100), nullable=False)
        description = db.Column(db.Text,        nullable=False)
        skills      = db.Column(db.JSON,        default=list)
        salary      = db.Column(db.String(100), default="")
        employer_id = db.Column(db.Integer,
                                db.ForeignKey("users.id", ondelete="CASCADE"),
                                nullable=False)
        posted_at   = db.Column(db.DateTime, default=datetime.utcnow)
        employer    = db.relationship("User", back_populates="jobs")
        applications = db.relationship("Application", back_populates="job",
                                    cascade="all, delete-orphan")

        def to_dict(self):
            return {
                "id":          self.id,
                "title":       self.title,
                "company":     self.company,
                "location":    self.location,
                "type":        self.job_type,
                "description": self.description,
                "skills":      self.skills or [],
                "salary":      self.salary,
                "posted_at":   self.posted_at.isoformat(),
            }

    class Application(db.Model):
        __tablename__ = "applications"
        id           = db.Column(db.Integer, primary_key=True)
        job_id       = db.Column(db.Integer,
                                db.ForeignKey("jobs.id", ondelete="CASCADE"),
                                nullable=False)
        applicant_id = db.Column(db.Integer,
                                db.ForeignKey("users.id", ondelete="CASCADE"),
                                nullable=False)
        status       = db.Column(db.String(50), default="pending")
        applied_at   = db.Column(db.DateTime,   default=datetime.utcnow)
        job          = db.relationship("Job", back_populates="applications")
        applicant    = db.relationship("User")

    # ── HELPERS ──────────────────────────────────────────────────
    verification_store = {}

    def make_token(user, secret):
        payload = {
            "id":    user.id,
            "email": user.email,
            "role":  user.role,
            "exp":   datetime.now(timezone.utc) + timedelta(days=7)
        }
        return pyjwt.encode(payload, secret, algorithm="HS256")

    def token_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            from flask import current_app # Local import to avoid circular issues
            if request.method == "OPTIONS":
                return jsonify({"status": "ok"}), 200

            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                return jsonify({"success": False, "error": "Missing token"}), 401
            try:
                token   = auth.split(" ")[1]
                payload = pyjwt.decode(
                    token, current_app.config['JWT_SECRET'], algorithms=["HS256"])
                user = User.query.get(payload["id"])
                if not user:
                    return jsonify({"success": False, "error": "User not found"}), 401
                request.current_user = user
            except Exception:
                return jsonify({"success": False, "error": "Invalid token"}), 401
            return f(*args, **kwargs)
        return decorated

    # ════════════════════════════════════════════════════════════
    # ROUTES
    # ════════════════════════════════════════════════════════════

    @app.route("/api/hello")
    def hello():
        return jsonify({"message": "Hello from Flask!"}), 200

    # ── Send verification code ───────────────────────────────
    @app.route("/api/send-verification-code", methods=["POST", "OPTIONS"])
    def send_code():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        data  = request.get_json()
        email = data.get("email", "").strip().lower()

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
                body=(f"Your JobHive verification code is: {code}\n\n"
                      f"This code expires in 10 minutes.")
            )
            mail.send(msg)
            print(f"[SUCCESS] Email sent to {email}")
            return jsonify({"success": True, "message": "Code sent!"}), 200
        except Exception as e:
            verification_store.pop(email, None)
            print(f"[SMTP ERROR] {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    # ── Verify code ──────────────────────────────────────────
    @app.route("/api/verify-email", methods=["POST", "OPTIONS"])
    def verify_email():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        data           = request.get_json()
        email          = data.get("email", "").strip().lower()
        submitted_code = data.get("code", "")

        record = verification_store.get(email)
        if not record:
            return jsonify({"success": False,
                            "error": "No code found. Request a new one."}), 400
        if time.time() > record["expires_at"]:
            verification_store.pop(email, None)
            return jsonify({"success": False, "error": "Code expired."}), 400
        if submitted_code != record["code"]:
            return jsonify({"success": False, "error": "Incorrect code."}), 400

        verification_store[email]["verified"] = True
        print(f"[SUCCESS] {email} verified")
        return jsonify({"success": True, "email": email}), 200

    # ── Register ─────────────────────────────────────────────
    @app.route("/api/register", methods=["POST", "OPTIONS"])
    def register():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        data     = request.get_json()
        email    = data.get("email", "").strip().lower()
        password = data.get("password", "")
        name     = data.get("name", "").strip()
        role     = data.get("role", "job_seeker")

        print(f"[DEBUG] Register: email={email}, name={name}, role={role}, "
              f"password={'✓' if password else '✗'}")

        if not all([email, password, name]):
            return jsonify({"success": False,
                            "error": "Email, name and password are required."}), 400

        if User.query.filter_by(email=email).first():
            return jsonify({"success": False,
                            "error": "Account already exists."}), 409

        record = verification_store.get(email)
        if not record or not record.get("verified"):
            return jsonify({"success": False,
                            "error": "Email not verified."}), 403

        user = User(
            email         = email,
            name          = name,
            password_hash = generate_password_hash(password),
            role          = role,
            is_verified   = True,
        )
        db.session.add(user)
        db.session.commit()
        verification_store.pop(email, None)

        token = make_token(user)
        print(f"[SUCCESS] Registered {email} as {role} (DB id={user.id})")
        return jsonify({
            "success":      True,
            "access_token": token,
            "user":         user.to_dict()
        }), 201

    # ── Login ────────────────────────────────────────────────
    @app.route("/api/login", methods=["POST", "OPTIONS"])
    def login():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        data     = request.get_json()
        email    = data.get("email", "").strip().lower()
        password = data.get("password", "")

        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password_hash, password):
            print(f"[FAIL] Login failed for {email}")
            return jsonify({"success": False,
                            "error": "Invalid email or password."}), 401

        token = make_token(user)
        print(f"[SUCCESS] Login: {email}")
        return jsonify({
            "success":      True,
            "access_token": token,
            "user":         user.to_dict()
        }), 200

    # ── Current user ─────────────────────────────────────────
    @app.route("/api/user/me", methods=["GET", "OPTIONS"])
    @token_required
    def get_me():
        return jsonify({"success": True,
                        "user": request.current_user.to_dict()}), 200

    # ── Jobs ─────────────────────────────────────────────────
    @app.route("/api/jobs", methods=["GET", "POST", "OPTIONS"])
    def jobs():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        if request.method == "GET":
            all_jobs = Job.query.order_by(Job.posted_at.desc()).all()
            return jsonify({
                "success": True,
                "jobs":    [j.to_dict() for j in all_jobs],
                "total":   len(all_jobs)
            }), 200

        # POST — requires auth
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"success": False, "error": "Login required"}), 401
        try:
            payload = pyjwt.decode(
                auth.split(" ")[1], app.config['JWT_SECRET'], algorithms=["HS256"])
            employer = User.query.get(payload["id"])
        except Exception:
            return jsonify({"success": False, "error": "Invalid token"}), 401

        if not employer or employer.role != "employer":
            return jsonify({"success": False,
                            "error": "Only employers can post jobs."}), 403

        data     = request.get_json()
        missing  = [f for f in ["title","company","location","type","description"]
                    if not data.get(f)]
        if missing:
            return jsonify({"success": False,
                            "error": f"Missing: {', '.join(missing)}"}), 400

        job = Job(
            title       = data["title"],
            company     = data["company"],
            location    = data["location"],
            job_type    = data["type"],
            description = data["description"],
            skills      = data.get("skills", []),
            salary      = data.get("salary", ""),
            employer_id = employer.id,
        )
        db.session.add(job)
        db.session.commit()
        print(f"[SUCCESS] Job '{job.title}' posted by {employer.email}")
        return jsonify({"success": True, "job": job.to_dict()}), 201

    # ── Job-seeker profile ───────────────────────────────────
    @app.route("/api/job-seeker/profile", methods=["GET", "POST", "OPTIONS"])
    @token_required
    def jobseeker_profile():
        user = request.current_user
        if request.method == "GET":
            return jsonify({"success": True, "profile": user.to_dict()}), 200

        data = request.get_json()
        user.title       = data.get("title",       user.title)
        user.bio         = data.get("bio",          user.bio)
        user.phone       = data.get("phone",        user.phone)
        user.location    = data.get("address",      user.location)
        user.website     = data.get("website",      user.website)
        user.skills      = data.get("skills",       user.skills)
        user.education   = data.get("education",    user.education)
        user.profile_pic = data.get("profile_pic_url", user.profile_pic)
        if data.get("full_name"):
            user.name    = data["full_name"]
        db.session.commit()
        print(f"[SUCCESS] Profile updated for {user.email}")
        return jsonify({"success": True,
                        "message": "Profile updated!",
                        "profile_pic_url": user.profile_pic}), 200

    # ── Employer profile ─────────────────────────────────────
    @app.route("/api/employer/profile", methods=["GET", "POST", "OPTIONS"])
    @token_required
    def employer_profile():
        user = request.current_user
        if request.method == "GET":
            return jsonify({"success": True, "profile": user.to_dict()}), 200

        data = request.get_json()
        user.company_name = data.get("company_name", user.company_name)
        user.industry     = data.get("industry",     user.industry)
        user.company_size = data.get("company_size", user.company_size)
        user.website      = data.get("website",      user.website)
        user.location     = data.get("location",     user.location)
        user.description  = data.get("description",  user.description)
        user.logo_url     = data.get("logo_url",     user.logo_url)
        db.session.commit()
        print(f"[SUCCESS] Employer profile updated for {user.email}")
        return jsonify({"success": True, "message": "Company profile updated!"}), 200

    # ── Resume ───────────────────────────────────────────────
    @app.route("/api/resume", methods=["GET", "POST", "OPTIONS"])
    @token_required
    def resume():
        user = request.current_user
        if request.method == "GET":
            return jsonify({
                "success":   True,
                "cv_url":    user.cv_url,
                "skills":    user.skills or [],
                "education": user.education or [],
            }), 200

        data        = request.get_json()
        user.cv_url = data.get("cv_url", user.cv_url)
        db.session.commit()
        return jsonify({"success": True, "cv_url": user.cv_url}), 200

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(debug=True, host="0.0.0.0", port=port)