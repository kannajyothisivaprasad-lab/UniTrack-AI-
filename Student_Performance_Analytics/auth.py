"""
UniTrack AI - Authentication, Authorization, CSRF Protection & Audit Logging
Enforces role-based access control, tenant isolation, rate limiting, and security compliance.
"""

import functools
import secrets
import datetime
import json
from flask import session, request, redirect, url_for, flash, abort, jsonify, g, has_request_context
from werkzeug.security import check_password_hash, generate_password_hash
from database import db_session


MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15


def get_client_ip():
    """Extracts client IP safely from request headers."""
    try:
        if request and request.headers.get('X-Forwarded-For'):
            return request.headers.get('X-Forwarded-For').split(',')[0].strip()
        return request.remote_addr or '127.0.0.1'
    except Exception:
        return '127.0.0.1'


def log_audit_event(action, details=None, university_id=None, user_id=None, cursor=None):
    """Persists security and administrative events into audit_logs table."""
    try:
        user = session.get('user') if session else None
        if not user_id and user:
            user_id = user.get('id')
        if not university_id and user:
            university_id = user.get('university_id')

        ip = get_client_ip()
        if cursor:
            cursor.execute('''
                INSERT INTO audit_logs (university_id, user_id, action, details, ip_address)
                VALUES (?, ?, ?, ?, ?)
            ''', (university_id, user_id, action, details, ip))
        else:
            with db_session() as conn:
                cur = conn.cursor()
                cur.execute('''
                    INSERT INTO audit_logs (university_id, user_id, action, details, ip_address)
                    VALUES (?, ?, ?, ?, ?)
                ''', (university_id, user_id, action, details, ip))
    except Exception as e:
        pass


def generate_csrf_token():
    """Generates or retrieves CSRF token stored in user session."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def validate_csrf():
    """Validates CSRF token on mutating HTTP methods."""
    if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
        # Check header first, then form data, then JSON payload
        token = (
            request.headers.get('X-CSRFToken') or
            request.form.get('csrf_token') or
            (request.is_json and request.get_json(silent=True) and request.get_json(silent=True).get('csrf_token'))
        )
        expected_token = session.get('_csrf_token')
        if not expected_token or not token or token != expected_token:
            log_audit_event('CSRF_VALIDATION_FAILED', f"Path: {request.path}")
            if request.is_json:
                abort(403, description="CSRF token validation failed or missing.")
            flash("Security check failed (CSRF token missing or expired). Please try again.", "danger")
            abort(403)


def get_current_user():
    """Returns the authenticated user dict from session, or None."""
    return session.get('user')


def authenticate_user(email, password, expected_role=None):
    """
    Authenticates user credentials, enforces university status, and handles lockout.
    Returns (success: bool, user_dict_or_error_message: dict | str).
    """
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.*, un.status as uni_status, un.name as uni_name
            FROM users u
            LEFT JOIN universities un ON u.university_id = un.id
            WHERE u.email = ?
        ''', (email.strip().lower(),))
        user_row = cursor.fetchone()

        if not user_row:
            log_audit_event('LOGIN_FAILED_UNKNOWN_USER', f"Email: {email}", cursor=cursor)
            return False, "Invalid email or password."

        # Check account lockout
        now = datetime.datetime.now()
        locked_until = user_row['locked_until']
        if locked_until:
            if isinstance(locked_until, str):
                try:
                    locked_until_dt = datetime.datetime.fromisoformat(locked_until)
                except Exception:
                    locked_until_dt = datetime.datetime.strptime(locked_until, '%Y-%m-%d %H:%M:%S')
            else:
                locked_until_dt = locked_until

            if now < locked_until_dt:
                mins_left = int((locked_until_dt - now).total_seconds() / 60) + 1
                return False, f"Account temporarily locked due to multiple failed login attempts. Try again in {mins_left} minutes."

        # Check user active status
        if not user_row['is_active']:
            return False, "This account has been deactivated. Please contact your administrator."

        # Check password
        if not check_password_hash(user_row['password_hash'], password):
            failed = (user_row['failed_logins'] or 0) + 1
            if failed >= MAX_FAILED_LOGINS:
                lock_time = now + datetime.timedelta(minutes=LOCKOUT_MINUTES)
                cursor.execute(
                    "UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?",
                    (failed, lock_time.strftime('%Y-%m-%d %H:%M:%S'), user_row['id'])
                )
                log_audit_event('ACCOUNT_LOCKED', f"Account locked for {email}", university_id=user_row['university_id'], user_id=user_row['id'], cursor=cursor)
                return False, f"Too many failed login attempts. Account locked for {LOCKOUT_MINUTES} minutes."
            else:
                cursor.execute("UPDATE users SET failed_logins = ? WHERE id = ?", (failed, user_row['id']))
                log_audit_event('LOGIN_FAILED_PASSWORD', f"Attempt {failed} for {email}", university_id=user_row['university_id'], user_id=user_row['id'], cursor=cursor)
                return False, f"Invalid email or password. ({MAX_FAILED_LOGINS - failed} attempts remaining)"

        # Check University Status for tenant accounts
        if user_row['role'] != 'super_admin':
            uni_status = user_row['uni_status']
            if uni_status == 'pending':
                return False, "Your university registration is pending Platform Super Admin approval."
            elif uni_status == 'suspended':
                return False, "Access suspended: This university account is currently suspended. Please contact platform administration."
            elif uni_status == 'inactive':
                return False, "This university account has been deactivated."
            elif uni_status != 'active':
                return False, "University account is not active."

        # Reset failed login count
        cursor.execute("UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = ?", (user_row['id'],))

        # Permissions parsing
        perms = []
        if user_row['permissions']:
            try:
                perms = json.loads(user_row['permissions'])
            except Exception:
                perms = [user_row['permissions']]

        user_data = {
            'id': user_row['id'],
            'email': user_row['email'],
            'full_name': user_row['full_name'],
            'role': user_row['role'],
            'department': user_row['department'],
            'permissions': perms,
            'university_id': user_row['university_id'],
            'university_name': user_row['uni_name'] or 'UniTrack Platform HQ'
        }

        # Store in session if within active request context
        if has_request_context():
            session.clear()
            session['user'] = user_data
            session['_csrf_token'] = secrets.token_hex(32)
            session.permanent = True

        log_audit_event('LOGIN_SUCCESS', f"Role: {user_row['role']}", university_id=user_row['university_id'], user_id=user_row['id'], cursor=cursor)
        return True, user_data


def authenticate_student(student_id_code, password):
    """
    Authenticates a student using Student ID and password.
    Ensures university is active and student is not suspended.
    Returns (success: bool, user_dict_or_error: dict | str).
    """
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.*, un.status as uni_status, un.name as uni_name
            FROM students s
            JOIN universities un ON s.university_id = un.id
            WHERE UPPER(s.student_id) = UPPER(?)
        """, (student_id_code.strip(),))
        row = cursor.fetchone()

        if not row:
            log_audit_event('STUDENT_LOGIN_FAILED_NOT_FOUND', f"ID: {student_id_code}", cursor=cursor)
            return False, "Student ID not found in system records."

        if row['uni_status'] != 'active':
            return False, f"Your university status is currently {row['uni_status']}. Access restricted."

        if row['enrollment_status'] == 'Suspended':
            return False, "Your student account enrollment is currently suspended. Please contact the administrative office."

        stored_hash = row['password_hash']
        if not stored_hash or not check_password_hash(stored_hash, password):
            log_audit_event('STUDENT_LOGIN_FAILED_PASSWORD', f"Student: {student_id_code}", university_id=row['university_id'], cursor=cursor)
            return False, "Invalid Student ID or password."

        user_data = {
            'id': row['id'],
            'student_pk': row['id'],
            'student_id': row['student_id'],
            'student_code': row['student_id'],
            'full_name': row['full_name'],
            'email': row['email'],
            'role': 'student',
            'university_id': row['university_id'],
            'university_name': row['uni_name'],
            'course_name': row['course_name'] or 'Engineering',
            'batch_name': row['batch_name'] or 'Current',
            'department_id': row['department_id'],
            'permissions': ['student_portal']
        }

        if has_request_context():
            session.clear()
            session['user'] = user_data
            session['_csrf_token'] = secrets.token_hex(32)
            session.permanent = True

        log_audit_event('STUDENT_LOGIN_SUCCESS', f"Student: {student_id_code}", university_id=row['university_id'], user_id=row['id'], cursor=cursor)
        return True, user_data


def student_required(f):
    """Decorator requiring an active student session."""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        user = session.get('user')
        if not user or user.get('role') != 'student':
            flash("Please log in through the Student Portal to access this dashboard.", "warning")
            return redirect(url_for('student_login_view'))
        return f(*args, **kwargs)
    return decorated_function


def login_required(f):
    """Requires an authenticated user session."""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user'):
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login_view', next=request.path))
        return f(*args, **kwargs)
    return decorated_function


def roles_required(*allowed_roles):
    """Enforces specific user roles (e.g. 'super_admin', 'university_admin')."""
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            user = session.get('user')
            if not user:
                flash("Please log in to continue.", "warning")
                return redirect(url_for('login_view', next=request.path))
            if user.get('role') not in allowed_roles:
                log_audit_event('UNAUTHORIZED_ACCESS_ATTEMPT', f"Target: {request.path}, User Role: {user.get('role')}")
                if request.is_json:
                    return jsonify({'status': 'error', 'message': 'Forbidden: Insufficient permissions.'}), 403
                flash("Access denied: You do not have permission to view this resource.", "danger")
                if user.get('role') == 'super_admin':
                    return redirect(url_for('super_admin_dashboard'))
                return redirect(url_for('dashboard_view'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def permission_required(permission_name):
    """Enforces module permissions for university staff."""
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            user = session.get('user')
            if not user:
                return redirect(url_for('login_view'))
            # Super admin and university admin have unrestricted university access
            if user.get('role') in ['super_admin', 'university_admin']:
                return f(*args, **kwargs)
            # Staff check
            perms = user.get('permissions', [])
            if 'all' in perms or permission_name in perms:
                return f(*args, **kwargs)
            
            log_audit_event('STAFF_PERMISSION_DENIED', f"Required: {permission_name}")
            if request.is_json:
                return jsonify({'status': 'error', 'message': f"Access denied: Missing '{permission_name}' permission."}), 403
            flash(f"You do not have permission to access the {permission_name.capitalize()} module.", "warning")
            return redirect(url_for('dashboard_view'))
        return decorated_function
    return decorator


def get_current_university_id():
    """
    Returns the server-authenticated university_id.
    NEVER accepts or trusts tenant ID from request query params or user input!
    """
    user = session.get('user')
    if not user:
        return None
    return user.get('university_id')
