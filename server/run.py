from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
import os, random, time, jwt as pyjwt
from datetime import datetime, timedelta, timezone
from functools import wraps

# ── Extensions ────────────────────────────────────────────────
db   = SQLAlchemy()
mail = Mail()

# ── Verification codes (short-lived, memory is fine) ──────────
verification_store = {}


# ══════════════════════════════════════════════════════════════
# MODELS  (module-level — SQLAlchemy registry requires this)
# ══════════════════════════════════════════════════════════════

class User(db.Model):
    __tablename__ = "users"
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(255), unique=True, nullable=False)
    name          = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(512), nullable=False)
    role          = db.Column(db.String(50),  nullable=False, default="job_seeker")
    is_verified   = db.Column(db.Boolean,     default=False)
    created_at    = db.Column(db.DateTime,    default=datetime.utcnow)

    # Job-seeker profile
    title       = db.Column(db.String(255), default="")
    bio         = db.Column(db.Text,        default="")
    phone       = db.Column(db.String(50),  default="")
    location    = db.Column(db.String(255), default="")
    website     = db.Column(db.String(255), default="")
    skills      = db.Column(db.JSON,        default=list)
    education   = db.Column(db.JSON,        default=list)
    cv_url      = db.Column(db.String(512), default="")
    profile_pic = db.Column(db.String(512), default="")

    # Employer profile
    company_name = db.Column(db.String(255), default="")
    industry     = db.Column(db.String(255), default="")
    company_size = db.Column(db.String(100), default="")
    description  = db.Column(db.Text,        default="")
    logo_url     = db.Column(db.String(512), default="")

    jobs         = db.relationship("Job",         back_populates="employer",
                                   cascade="all, delete-orphan")
    applications = db.relationship("Application", back_populates="applicant",
                                   cascade="all, delete-orphan",
                                   foreign_keys="Application.applicant_id")

    def to_dict(self):
        return {
            "id":             self.id,
            "email":          self.email,
            "name":           self.name,
            "role":           self.role,
            "isVerified":     self.is_verified,
            "title":          self.title        or "",
            "bio":            self.bio          or "",
            "phone":          self.phone        or "",
            "location":       self.location     or "",
            "website":        self.website      or "",
            "skills":         self.skills       or [],
            "education":      self.education    or [],
            "cv_url":         self.cv_url       or "",
            "profilePicture": self.profile_pic  or "",
            "company_name":   self.company_name or "",
            "logo_url":       self.logo_url     or "",
            "industry":       self.industry     or "",
            "company_size":   self.company_size or "",
            "description":    self.description  or "",
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

    employer     = db.relationship("User",        back_populates="jobs")
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
            "skills":      self.skills  or [],
            "salary":      self.salary  or "",
            "posted_at":   self.posted_at.isoformat(),
            "employer_id": self.employer_id,
        }


class Application(db.Model):
    __tablename__ = "applications"
    id           = db.Column(db.Integer, primary_key=True)
    job_id       = db.Column(db.Integer,
                             db.ForeignKey("jobs.id",  ondelete="CASCADE"),
                             nullable=False)
    applicant_id = db.Column(db.Integer,
                             db.ForeignKey("users.id", ondelete="CASCADE"),
                             nullable=False)
    status     = db.Column(db.String(50), default="pending")
    applied_at = db.Column(db.DateTime,   default=datetime.utcnow)

    job       = db.relationship("Job",  back_populates="applications")
    applicant = db.relationship("User", back_populates="applications",
                                foreign_keys=[applicant_id])

    def to_dict(self):
        return {
            "id":         self.id,
            "job_id":     self.job_id,
            "job_title":  self.job.title   if self.job else "",
            "company":    self.job.company  if self.job else "",
            "status":     self.status,
            "applied_at": self.applied_at.isoformat(),
        }


# Many-to-many: saved jobs
saved_jobs_table = db.Table(
    "saved_jobs",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id", ondelete="CASCADE")),
    db.Column("job_id",  db.Integer, db.ForeignKey("jobs.id",  ondelete="CASCADE")),
)


# ══════════════════════════════════════════════════════════════
# APP FACTORY
# ══════════════════════════════════════════════════════════════

def create_app():
    app = Flask(__name__)

    # ── Database ──────────────────────────────────────────────
    local_db = "postgresql://md.abrarhossainzahin@localhost/jobhive_db"
    app.config["SQLALCHEMY_DATABASE_URI"]  = os.environ.get("DATABASE_URL", local_db)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ── JWT secret ────────────────────────────────────────────
    app.config["JWT_SECRET"] = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-in-prod")

    # ── Email (Brevo SMTP) ────────────────────────────────────
    app.config["MAIL_SERVER"]         = os.environ.get("EMAIL_HOST", "smtp-relay.brevo.com")
    app.config["MAIL_PORT"]           = int(os.environ.get("EMAIL_PORT", 587))
    app.config["MAIL_USE_TLS"]        = True
    app.config["MAIL_USERNAME"]       = os.environ.get("EMAIL_USER")
    app.config["MAIL_PASSWORD"]       = os.environ.get("EMAIL_PASS")
    app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("EMAIL_FROM")

    db.init_app(app)
    mail.init_app(app)

    # ── CORS ──────────────────────────────────────────────────
    allowed_origins = [
        "http://localhost:5173",
        "https://job-portal-five-sable.vercel.app",
        os.environ.get("FRONTEND_URL", ""),
    ]
    CORS(app,
         resources={r"/api/*": {"origins": [o for o in allowed_origins if o]}},
         supports_credentials=True)

    # ── Create / verify all tables ────────────────────────────
    with app.app_context():
        db.create_all()
        print("[DB] All tables created / verified ✓")

    # ══════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════

    def make_token(user: User) -> str:
        payload = {
            "id":    user.id,
            "email": user.email,
            "role":  user.role,
            "exp":   datetime.now(timezone.utc) + timedelta(days=7),
        }
        return pyjwt.encode(payload, app.config["JWT_SECRET"], algorithm="HS256")

    def get_current_user():
        """Read Bearer token from header → return User or None."""
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        try:
            payload = pyjwt.decode(
                auth.split(" ")[1],
                app.config["JWT_SECRET"],
                algorithms=["HS256"],
            )
            return db.session.get(User, payload["id"])
        except Exception:
            return None

    def token_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Always allow CORS preflight through
            if request.method == "OPTIONS":
                return jsonify({"status": "ok"}), 200
            user = get_current_user()
            if not user:
                return jsonify({"success": False, "error": "Login required"}), 401
            request.current_user = user
            return f(*args, **kwargs)
        return decorated

    # ══════════════════════════════════════════════════════════
    # AUTH ROUTES
    # ══════════════════════════════════════════════════════════

    @app.route("/api/hello")
    def hello():
        return jsonify({"message": "Hello from JobHive!"}), 200

    # ── 1. Send verification code ──────────────────────────────
    @app.route("/api/send-verification-code", methods=["POST", "OPTIONS"])
    def send_code():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        data  = request.get_json() or {}
        email = data.get("email", "").strip().lower()

        if not email:
            return jsonify({"success": False, "error": "Email is required"}), 400

        code = str(random.randint(100000, 999999))
        verification_store[email] = {
            "code":       code,
            "expires_at": time.time() + 600,
            "verified":   False,
        }
        print(f"[DEBUG] Code {code} stored for {email}")

        try:
            msg = Message(
                subject="Your JobHive Verification Code",
                recipients=[email],
                body=(
                    f"Your JobHive verification code is: {code}\n\n"
                    f"This code expires in 10 minutes.\n"
                    f"If you did not request this, ignore this email."
                ),
            )
            mail.send(msg)
            print(f"[SUCCESS] Email sent to {email}")
            return jsonify({"success": True, "message": "Code sent!"}), 200
        except Exception as e:
            verification_store.pop(email, None)
            print(f"[SMTP ERROR] {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    # ── 2. Verify the code ─────────────────────────────────────
    @app.route("/api/verify-email", methods=["POST", "OPTIONS"])
    def verify_email():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        data           = request.get_json() or {}
        email          = data.get("email", "").strip().lower()
        submitted_code = data.get("code", "")

        record = verification_store.get(email)
        if not record:
            return jsonify({"success": False,
                            "error": "No code found. Please request a new one."}), 400
        if time.time() > record["expires_at"]:
            verification_store.pop(email, None)
            return jsonify({"success": False, "error": "Code expired."}), 400
        if submitted_code != record["code"]:
            return jsonify({"success": False, "error": "Incorrect code."}), 400

        verification_store[email]["verified"] = True
        print(f"[SUCCESS] {email} verified")
        return jsonify({"success": True, "email": email}), 200

    # ── 3. Register ────────────────────────────────────────────
    @app.route("/api/register", methods=["POST", "OPTIONS"])
    def register():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        data     = request.get_json() or {}
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
                            "error": "An account with this email already exists."}), 409

        record = verification_store.get(email)
        if not record or not record.get("verified"):
            return jsonify({"success": False,
                            "error": "Email not verified. Please verify first."}), 403

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
        print(f"[SUCCESS] Registered {email} as {role} → DB id={user.id}")
        return jsonify({
            "success":      True,
            "access_token": token,
            "user":         user.to_dict(),
        }), 201

    # ── 4. Login ───────────────────────────────────────────────
    @app.route("/api/login", methods=["POST", "OPTIONS"])
    def login():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        data     = request.get_json() or {}
        email    = data.get("email", "").strip().lower()
        password = data.get("password", "")

        user = User.query.filter_by(email=email).first()
        if not user:
            print(f"[FAIL] No user: {email}")
            return jsonify({"success": False,
                            "error": "Invalid email or password."}), 401
        if not check_password_hash(user.password_hash, password):
            print(f"[FAIL] Wrong password: {email}")
            return jsonify({"success": False,
                            "error": "Invalid email or password."}), 401

        token = make_token(user)
        print(f"[SUCCESS] Login: {email} (role={user.role})")
        return jsonify({
            "success":      True,
            "access_token": token,
            "user":         user.to_dict(),
        }), 200

    # ── 5. Current user ────────────────────────────────────────
    @app.route("/api/user/me", methods=["GET", "OPTIONS"])
    @token_required
    def get_me():
        return jsonify({"success": True,
                        "user": request.current_user.to_dict()}), 200

    # ══════════════════════════════════════════════════════════
    # JOB ROUTES
    # ══════════════════════════════════════════════════════════

    @app.route("/api/jobs", methods=["GET", "POST", "OPTIONS"])
    def jobs():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        # GET — public, no auth needed
        if request.method == "GET":
            all_jobs = Job.query.order_by(Job.posted_at.desc()).all()
            return jsonify({
                "success": True,
                "jobs":    [j.to_dict() for j in all_jobs],
                "total":   len(all_jobs),
            }), 200

        # POST — employer only, auth required
        user = get_current_user()
        if not user:
            return jsonify({"success": False, "error": "Login required"}), 401
        if user.role != "employer":
            return jsonify({"success": False,
                            "error": "Only employers can post jobs."}), 403

        data    = request.get_json() or {}
        missing = [f for f in ["title", "company", "location", "type", "description"]
                   if not data.get(f)]
        if missing:
            return jsonify({"success": False,
                            "error": f"Missing fields: {', '.join(missing)}"}), 400

        job = Job(
            title       = data["title"],
            company     = data["company"],
            location    = data["location"],
            job_type    = data["type"],
            description = data["description"],
            skills      = data.get("skills",  []),
            salary      = data.get("salary",  ""),
            employer_id = user.id,
        )
        db.session.add(job)
        db.session.commit()
        print(f"[SUCCESS] Job '{job.title}' posted by {user.email}")
        return jsonify({"success": True, "job": job.to_dict()}), 201

    @app.route("/api/jobs/<int:job_id>", methods=["GET", "OPTIONS"])
    def get_job(job_id):
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        job = db.session.get(Job, job_id)
        if not job:
            return jsonify({"success": False, "error": "Job not found"}), 404
        return jsonify({"success": True, "job": job.to_dict()}), 200

    @app.route("/api/employer/<int:user_id>/jobs", methods=["GET", "OPTIONS"])
    @token_required
    def employer_jobs(user_id):
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        jobs_list = Job.query.filter_by(employer_id=user_id)\
                             .order_by(Job.posted_at.desc()).all()
        return jsonify({
            "success": True,
            "jobs":    [j.to_dict() for j in jobs_list],
        }), 200

    # ══════════════════════════════════════════════════════════
    # APPLICATION ROUTES
    # ══════════════════════════════════════════════════════════

    @app.route("/api/jobs/<int:job_id>/apply", methods=["POST", "OPTIONS"])
    @token_required
    def apply_to_job(job_id):
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        user = request.current_user
        if user.role not in ("student", "job_seeker"):
            return jsonify({"success": False,
                            "error": "Only job seekers can apply."}), 403

        job = db.session.get(Job, job_id)
        if not job:
            return jsonify({"success": False, "error": "Job not found"}), 404

        already = Application.query.filter_by(
            job_id=job_id, applicant_id=user.id).first()
        if already:
            return jsonify({"success": False,
                            "error": "You already applied to this job."}), 409

        application = Application(job_id=job_id, applicant_id=user.id)
        db.session.add(application)
        db.session.commit()
        print(f"[SUCCESS] {user.email} applied to job {job_id}")
        return jsonify({"success": True, "message": "Applied successfully!"}), 201

    @app.route("/api/job-seeker/<int:user_id>/applied-jobs", methods=["GET", "OPTIONS"])
    @token_required
    def applied_jobs(user_id):
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        apps = Application.query.filter_by(applicant_id=user_id).all()
        return jsonify({
            "success":      True,
            "applications": [a.to_dict() for a in apps],
        }), 200

    # ══════════════════════════════════════════════════════════
    # SAVED JOBS ROUTES
    # ══════════════════════════════════════════════════════════

    @app.route("/api/job-seeker/<int:user_id>/saved-jobs", methods=["GET", "OPTIONS"])
    @token_required
    def get_saved_jobs(user_id):
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        rows    = db.session.execute(
            saved_jobs_table.select().where(
                saved_jobs_table.c.user_id == user_id)
        ).fetchall()
        job_ids = [r.job_id for r in rows]
        jobs_list = Job.query.filter(Job.id.in_(job_ids)).all() if job_ids else []
        return jsonify({
            "success":   True,
            "saved_jobs": [j.to_dict() for j in jobs_list],
        }), 200

    # New-style save/unsave  POST /api/jobs/<id>/save
    @app.route("/api/jobs/<int:job_id>/save", methods=["POST", "DELETE", "OPTIONS"])
    @token_required
    def toggle_save_job(job_id):
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        user = request.current_user
        job  = db.session.get(Job, job_id)
        if not job:
            return jsonify({"success": False, "error": "Job not found"}), 404

        exists = db.session.execute(
            saved_jobs_table.select().where(
                (saved_jobs_table.c.user_id == user.id) &
                (saved_jobs_table.c.job_id  == job_id)
            )
        ).fetchone()

        if request.method == "POST":
            if not exists:
                db.session.execute(saved_jobs_table.insert().values(
                    user_id=user.id, job_id=job_id))
                db.session.commit()
            return jsonify({"success": True, "message": "Job saved!"}), 200

        # DELETE
        if exists:
            db.session.execute(saved_jobs_table.delete().where(
                (saved_jobs_table.c.user_id == user.id) &
                (saved_jobs_table.c.job_id  == job_id)
            ))
            db.session.commit()
        return jsonify({"success": True, "message": "Job removed from saved."}), 200

    # Legacy-style  POST /api/job-seeker/<seeker_id>/save/<job_id>
    @app.route("/api/job-seeker/<int:seeker_id>/save/<int:job_id>",
               methods=["POST", "DELETE", "OPTIONS"])
    @token_required
    def save_job_legacy(seeker_id, job_id):
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        user = request.current_user
        job  = db.session.get(Job, job_id)
        if not job:
            return jsonify({"success": False, "error": "Job not found"}), 404

        exists = db.session.execute(
            saved_jobs_table.select().where(
                (saved_jobs_table.c.user_id == user.id) &
                (saved_jobs_table.c.job_id  == job_id)
            )
        ).fetchone()

        if request.method == "POST":
            if not exists:
                db.session.execute(saved_jobs_table.insert().values(
                    user_id=user.id, job_id=job_id))
                db.session.commit()
            return jsonify({"success": True, "message": "Job saved!"}), 200

        if exists:
            db.session.execute(saved_jobs_table.delete().where(
                (saved_jobs_table.c.user_id == user.id) &
                (saved_jobs_table.c.job_id  == job_id)
            ))
            db.session.commit()
        return jsonify({"success": True, "message": "Removed."}), 200

    # ══════════════════════════════════════════════════════════
    # PROFILE ROUTES
    # ══════════════════════════════════════════════════════════

    @app.route("/api/job-seeker/profile", methods=["GET", "POST", "OPTIONS"])
    @token_required
    def jobseeker_profile():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        user = request.current_user

        if request.method == "GET":
            return jsonify({"success": True, "profile": user.to_dict()}), 200

        data = request.get_json() or {}
        user.title       = data.get("title",          user.title)
        user.bio         = data.get("bio",             user.bio)
        user.phone       = data.get("phone",           user.phone)
        user.location    = data.get("address",         user.location) \
                        or data.get("location",        user.location)
        user.website     = data.get("website",         user.website)
        user.skills      = data.get("skills",          user.skills)
        user.education   = data.get("education",       user.education)
        user.profile_pic = data.get("profile_pic_url", user.profile_pic)
        if data.get("full_name"):
            user.name = data["full_name"]

        db.session.commit()
        print(f"[SUCCESS] Job-seeker profile saved for {user.email}")
        return jsonify({
            "success":         True,
            "message":         "Profile updated!",
            "profile_pic_url": user.profile_pic,
            "profile":         user.to_dict(),
        }), 200

    @app.route("/api/employer/profile", methods=["GET", "POST", "OPTIONS"])
    @token_required
    def employer_profile():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        user = request.current_user

        if request.method == "GET":
            return jsonify({"success": True, "profile": user.to_dict()}), 200

        data = request.get_json() or {}
        user.company_name = data.get("company_name", user.company_name)
        user.industry     = data.get("industry",     user.industry)
        user.company_size = data.get("company_size", user.company_size)
        user.website      = data.get("website",      user.website)
        user.location     = data.get("location",     user.location)
        user.description  = data.get("description",  user.description)
        user.logo_url     = data.get("logo_url",     user.logo_url)
        if data.get("full_name"):
            user.name = data["full_name"]

        db.session.commit()
        print(f"[SUCCESS] Employer profile saved for {user.email}")
        return jsonify({
            "success": True,
            "message": "Company profile updated!",
            "profile": user.to_dict(),
        }), 200

    # Alias — some frontend pages call /api/employer/company-info
    @app.route("/api/employer/company-info", methods=["GET", "POST", "OPTIONS"])
    @token_required
    def employer_company_info():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        user = request.current_user

        if request.method == "GET":
            return jsonify({"success": True, "profile": user.to_dict()}), 200

        data = request.get_json() or {}
        user.company_name = data.get("company_name", user.company_name)
        user.industry     = data.get("industry",     user.industry)
        user.company_size = data.get("company_size", user.company_size)
        user.website      = data.get("website",      user.website)
        user.location     = data.get("location",     user.location)
        user.description  = data.get("description",  user.description)
        user.logo_url     = data.get("logo_url",     user.logo_url)
        if data.get("name"):
            user.name = data["name"]

        db.session.commit()
        print(f"[SUCCESS] Company info saved for {user.email}")
        return jsonify({
            "success": True,
            "message": "Company info saved!",
            "profile": user.to_dict(),
        }), 200

    # ══════════════════════════════════════════════════════════
    # RESUME ROUTE
    # ══════════════════════════════════════════════════════════

    @app.route("/api/resume", methods=["GET", "POST", "OPTIONS"])
    @token_required
    def resume():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        user = request.current_user

        if request.method == "GET":
            return jsonify({
                "success":   True,
                "cv_url":    user.cv_url    or "",
                "skills":    user.skills    or [],
                "education": user.education or [],
            }), 200

        data        = request.get_json() or {}
        user.cv_url = data.get("cv_url", user.cv_url)
        if data.get("skills")   is not None:
            user.skills    = data["skills"]
        if data.get("education") is not None:
            user.education = data["education"]
        db.session.commit()
        print(f"[SUCCESS] Resume saved for {user.email}")
        return jsonify({"success": True, "cv_url": user.cv_url or ""}), 200

    # ══════════════════════════════════════════════════════════
    # UPLOAD ROUTES  (placeholder — use S3/R2 in production)
    # ══════════════════════════════════════════════════════════

    @app.route("/api/upload/profile-picture", methods=["POST", "OPTIONS"])
    @token_required
    def upload_profile_picture():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        user        = request.current_user
        placeholder = (f"https://api.dicebear.com/7.x/initials/svg"
                       f"?seed={user.name.replace(' ', '+')}")
        user.profile_pic = placeholder
        db.session.commit()
        print(f"[SUCCESS] Profile picture set for {user.email}")
        return jsonify({
            "success":         True,
            "profile_pic_url": placeholder,
            "message":         "Profile picture updated!",
        }), 200

    @app.route("/api/employer/upload-image", methods=["POST", "OPTIONS"])
    @token_required
    def employer_upload_image():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        user        = request.current_user
        seed        = (user.company_name or user.name).replace(" ", "+")
        placeholder = f"https://api.dicebear.com/7.x/initials/svg?seed={seed}"
        user.logo_url = placeholder
        db.session.commit()
        print(f"[SUCCESS] Company logo set for {user.email}")
        return jsonify({
            "success":  True,
            "logo_url": placeholder,
            "message":  "Company logo updated!",
        }), 200

    # ══════════════════════════════════════════════════════════
    # NOTIFICATION ROUTES  (stub — no 401, no crash)
    # ══════════════════════════════════════════════════════════

    @app.route("/api/notifications/<int:user_id>", methods=["GET", "OPTIONS"])
    def get_notifications(user_id):
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        # No auth required — return empty list so dashboard doesn't crash
        return jsonify({"success": True, "notifications": []}), 200

    @app.route("/api/notifications/<int:user_id>/mark-all-read",
               methods=["POST", "OPTIONS"])
    def mark_all_read(user_id):
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        return jsonify({"success": True}), 200

    # ── Change password ───────────────────────────────────────────
    @app.route("/api/change-password", methods=["POST", "OPTIONS"])
    @token_required
    def change_password():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        user = request.current_user
        data = request.get_json() or {}

        current_password = data.get("current_password", "")
        new_password     = data.get("new_password", "")

        if not current_password or not new_password:
            return jsonify({"success": False,
                            "error": "Both current and new password are required."}), 400

        if not check_password_hash(user.password_hash, current_password):
            return jsonify({"success": False,
                            "error": "Current password is incorrect."}), 401

        if len(new_password) < 8:
            return jsonify({"success": False,
                            "error": "New password must be at least 8 characters."}), 400

        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        print(f"[SUCCESS] Password changed for {user.email}")
        return jsonify({"success": True,
                        "message": "Password changed successfully!"}), 200

    return app

# ══════════════════════════════════════════════════════════════
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(debug=True, host="0.0.0.0", port=port)