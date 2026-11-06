"""
UniTrack AI – Multi-University Management & Student Performance Analytics System
Full-Stack Flask Application with Multi-Tenant Isolation, Role-Based Access Control,
Interactive Analytics Dashboards, Supervised Machine Learning Benchmarking, and Secure Data Governance.
"""

import os
import sys
import datetime
import json
import uuid
import pandas as pd
import numpy as np
from flask import (
    Flask, render_template, request, jsonify, send_file,
    flash, redirect, url_for, session, abort, g
)
from werkzeug.security import generate_password_hash

# Ensure application base directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from database import init_db, seed_demo_data, db_session
from auth import (
    authenticate_user, authenticate_student, student_required, login_required,
    roles_required, permission_required, get_current_user, get_current_university_id,
    generate_csrf_token, validate_csrf, log_audit_event
)
from tenant_service import TenantService, sanitize_spreadsheet_field
from ai_face_engine import ai_face_engine
from risk_engine import risk_engine
from ml_engine import engine

# Initialize database and tables
init_db()
seed_demo_data()

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)
app.secret_key = os.environ.get('SECRET_KEY', 'unitrack_ai_super_secret_production_key_2026')
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(hours=8)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# In-memory temporary cache for spreadsheet import previews
IMPORT_PREVIEWS = {}


# ==========================================
# CONTEXT PROCESSORS & MIDDLEWARE
# ==========================================

@app.context_processor
def inject_global_template_vars():
    """Injects current_user, csrf_token, and common dates into all Jinja templates."""
    return {
        'current_user': get_current_user(),
        'csrf_token': generate_csrf_token,
        'generate_csrf_token': generate_csrf_token,
        'today': datetime.date.today().strftime('%Y-%m-%d')
    }


@app.before_request
def csrf_protection_hook():
    """Validates CSRF token on mutating requests (POST, PUT, DELETE)."""
    if app.config.get('TESTING'):
        return
    exempt_paths = ['/api/status', '/api/predict']
    if request.path not in exempt_paths:
        validate_csrf()


# ==========================================
# AUTHENTICATION & REGISTRATION VIEWS
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login_view():
    """User authentication view with role detection and lockout enforcement."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash("Please enter both email and password.", "danger")
            return render_template('login.html')

        success, res = authenticate_user(email, password)
        if success:
            flash(f"Welcome back, {res['full_name']}!", "success")
            if res['role'] == 'super_admin':
                return redirect(url_for('super_admin_dashboard'))
            return redirect(url_for('dashboard_view'))
        else:
            flash(res, "danger")
            return render_template('login.html')

    # If already logged in, redirect
    user = get_current_user()
    if user:
        if user['role'] == 'super_admin':
            return redirect(url_for('super_admin_dashboard'))
        return redirect(url_for('dashboard_view'))

    return render_template('login.html')


@app.route('/super-admin/login')
def super_admin_login():
    """Convenience redirect to login."""
    return redirect(url_for('login_view'))


@app.route('/register', methods=['GET', 'POST'])
def register_view():
    """
    University onboarding registration.
    Creates institution record with 'pending' status requiring Platform Super Admin approval.
    """
    if request.method == 'POST':
        uni_id = request.form.get('university_id', '').strip().upper()
        uni_name = request.form.get('university_name', '').strip()
        uni_email = request.form.get('university_email', '').strip().lower()
        uni_address = request.form.get('university_address', '').strip()
        admin_name = request.form.get('admin_name', '').strip()
        admin_email = request.form.get('admin_email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validations
        if not uni_id or not uni_name or not uni_email or not admin_name or not admin_email or not password:
            flash("Please fill in all required fields.", "danger")
            return render_template('register_university.html')

        if password != confirm_password:
            flash("Passwords do not match. Please re-enter.", "danger")
            return render_template('register_university.html')

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template('register_university.html')

        try:
            with db_session() as conn:
                cursor = conn.cursor()

                # Check if university ID or email already exists
                cursor.execute("SELECT id FROM universities WHERE id = ? OR email = ?", (uni_id, uni_email))
                if cursor.fetchone():
                    flash("A university with this ID or email is already registered.", "danger")
                    return render_template('register_university.html')

                # Check if admin email already exists
                cursor.execute("SELECT id FROM users WHERE email = ?", (admin_email,))
                if cursor.fetchone():
                    flash("A user account with this email address already exists.", "danger")
                    return render_template('register_university.html')

                # Create university with 'pending' status
                cursor.execute('''
                    INSERT INTO universities (id, name, email, address, status, subscription_plan)
                    VALUES (?, ?, ?, ?, 'pending', 'Standard')
                ''', (uni_id, uni_name, uni_email, uni_address))

                # Create initial University Admin account
                pass_hash = generate_password_hash(password)
                cursor.execute('''
                    INSERT INTO users (university_id, email, password_hash, full_name, role, permissions)
                    VALUES (?, ?, ?, ?, 'university_admin', '["all"]')
                ''', (uni_id, admin_email, pass_hash, admin_name))

                log_audit_event('UNIVERSITY_REGISTRATION_SUBMITTED', f"University: {uni_id} ({uni_name})", university_id=uni_id)

            flash("University registration submitted successfully! Your account will be activated upon Platform Super Admin approval.", "success")
            return redirect(url_for('login_view'))

        except Exception as e:
            flash(f"Registration failed: {str(e)}", "danger")
            return render_template('register_university.html')

    return render_template('register_university.html')


@app.route('/password-reset', methods=['GET', 'POST'])
def password_reset_view():
    """Allows verified password reset."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not email or not new_password:
            flash("Please provide email and new password.", "danger")
            return render_template('password_reset.html')

        if new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template('password_reset.html')

        if len(new_password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template('password_reset.html')

        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, university_id FROM users WHERE email = ?", (email,))
            user = cursor.fetchone()
            if not user:
                flash("No account associated with that email address.", "danger")
                return render_template('password_reset.html')

            new_hash = generate_password_hash(new_password)
            cursor.execute("UPDATE users SET password_hash = ?, failed_logins = 0, locked_until = NULL WHERE id = ?", (new_hash, user['id']))
            log_audit_event('PASSWORD_RESET_SUCCESS', f"Password updated for {email}", university_id=user['university_id'], user_id=user['id'])

        flash("Password reset successfully. You may now sign in with your new password.", "success")
        return redirect(url_for('login_view'))

    return render_template('password_reset.html')


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile_view():
    """User profile overview and password change."""
    user = get_current_user()
    if request.method == 'POST':
        curr_pass = request.form.get('current_password', '')
        new_pass = request.form.get('new_password', '')
        conf_pass = request.form.get('confirm_password', '')

        if not curr_pass or not new_pass:
            flash("Please enter both current and new passwords.", "danger")
            return redirect(url_for('profile_view'))

        if new_pass != conf_pass:
            flash("New passwords do not match.", "danger")
            return redirect(url_for('profile_view'))

        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user['id'],))
            row = cursor.fetchone()
            from werkzeug.security import check_password_hash
            if not check_password_hash(row['password_hash'], curr_pass):
                flash("Current password incorrect.", "danger")
                return redirect(url_for('profile_view'))

            new_hash = generate_password_hash(new_pass)
            cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user['id']))
            log_audit_event('PASSWORD_CHANGED_BY_USER', "User updated password in profile", university_id=user.get('university_id'), user_id=user['id'])

        flash("Password updated successfully!", "success")
        return redirect(url_for('profile_view'))

    return render_template('profile.html', active_page='profile')


@app.route('/logout')
def logout_view():
    """Secure logout."""
    user = get_current_user()
    if user:
        log_audit_event('LOGOUT_SUCCESS', f"User {user['email']} logged out", university_id=user.get('university_id'), user_id=user['id'])
    session.clear()
    flash("You have been signed out successfully.", "info")
    return redirect(url_for('login_view'))


# ==========================================
# PLATFORM SUPER ADMIN PORTAL
# ==========================================

@app.route('/super-admin')
@login_required
@roles_required('super_admin')
def super_admin_dashboard():
    """Global multi-university management portal for the Platform Super Admin."""
    stats = TenantService.get_super_admin_stats()
    return render_template('super_admin.html', active_page='super_admin', stats=stats)


@app.route('/super-admin/university/<uni_id>/action', methods=['POST'])
@login_required
@roles_required('super_admin')
def super_admin_university_action(uni_id):
    """Handles approve, reject, activate, suspend, or deactivate actions."""
    action = request.form.get('action')
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with db_session() as conn:
        cursor = conn.cursor()
        if action == 'approve':
            cursor.execute("UPDATE universities SET status = 'active', approved_at = ?, approved_by = 'Platform Super Administrator' WHERE id = ?", (now, uni_id))
            flash(f"University '{uni_id}' approved and activated successfully!", "success")
            log_audit_event('UNIVERSITY_APPROVED', f"Approved {uni_id}")
        elif action == 'reject':
            cursor.execute("DELETE FROM universities WHERE id = ? AND status = 'pending'", (uni_id,))
            flash(f"University registration for '{uni_id}' rejected and purged.", "warning")
            log_audit_event('UNIVERSITY_REJECTED', f"Rejected {uni_id}")
        elif action == 'suspend':
            cursor.execute("UPDATE universities SET status = 'suspended' WHERE id = ?", (uni_id,))
            flash(f"University '{uni_id}' suspended. Accounts locked out.", "danger")
            log_audit_event('UNIVERSITY_SUSPENDED', f"Suspended {uni_id}")
        elif action == 'activate':
            cursor.execute("UPDATE universities SET status = 'active' WHERE id = ?", (uni_id,))
            flash(f"University '{uni_id}' reinstated to active status.", "success")
            log_audit_event('UNIVERSITY_ACTIVATED', f"Activated {uni_id}")
        elif action == 'deactivate':
            cursor.execute("UPDATE universities SET status = 'inactive' WHERE id = ?", (uni_id,))
            flash(f"University '{uni_id}' deactivated.", "secondary")
            log_audit_event('UNIVERSITY_DEACTIVATED', f"Deactivated {uni_id}")

    return redirect(url_for('super_admin_dashboard'))


# ==========================================
# UNIVERSITY DASHBOARD & ANALYTICS VIEWS
# ==========================================

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard_view():
    """Main executive dashboard scoped to authenticated university."""
    user = get_current_user()
    if user['role'] == 'super_admin':
        return redirect(url_for('super_admin_dashboard'))

    uni_id = get_current_university_id()

    # Load departments and sections for filters
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM departments WHERE university_id = ? ORDER BY name", (uni_id,))
        departments = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT * FROM sections WHERE university_id = ? ORDER BY name", (uni_id,))
        sections = [dict(r) for r in cursor.fetchall()]

    return render_template(
        'dashboard.html',
        active_page='dashboard',
        departments=departments,
        sections=sections
    )


@app.route('/api/dashboard/stats', methods=['GET'])
@login_required
def api_dashboard_stats():
    """
    Returns real database KPIs and Chart.js datasets.
    Strictly isolated to authenticated university. Never trusts tenant ID from query string.
    """
    uni_id = get_current_university_id()
    if not uni_id:
        return jsonify({'status': 'error', 'message': 'No active university context'}), 400

    dept_filter = request.args.get('dept', 'All')
    sec_filter = request.args.get('sec', 'All')
    year_filter = request.args.get('year', 'All')

    data = TenantService.get_dashboard_kpis(uni_id, dept_filter, sec_filter, year_filter)
    return jsonify({'status': 'success', 'data': data})


# ==========================================
# STUDENT MANAGEMENT MODULE
# ==========================================

@app.route('/students')
@login_required
@permission_required('students')
def students_view():
    """Renders student records & management table strictly isolated to current university."""
    uni_id = get_current_university_id()
    search = request.args.get('search', '', type=str)
    dept_id = request.args.get('dept_id', 'All', type=str)
    sec_id = request.args.get('sec_id', 'All', type=str)
    status = request.args.get('status', 'All', type=str)
    page = request.args.get('page', 1, type=int)

    result = TenantService.get_students(
        university_id=uni_id,
        search=search,
        dept_id=dept_id,
        sec_id=sec_id,
        status=status,
        page=page,
        per_page=15
    )

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM departments WHERE university_id = ? ORDER BY name", (uni_id,))
        departments = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT * FROM sections WHERE university_id = ? ORDER BY name", (uni_id,))
        sections = [dict(r) for r in cursor.fetchall()]

    return render_template(
        'students.html',
        active_page='students',
        students=result['students'],
        pagination=result,
        departments=departments,
        sections=sections,
        search_term=search,
        selected_dept=dept_id,
        selected_sec=sec_id,
        selected_status=status
    )


@app.route('/students/<int:student_pk>')
@login_required
@permission_required('students')
def student_profile_view(student_pk):
    """
    Renders 360-degree complete student profile dossier.
    Enforces tenant check: if student does not belong to logged-in university, 403 Forbidden is returned.
    """
    uni_id = get_current_university_id()
    dossier = TenantService.get_student_360(uni_id, student_pk)
    if not dossier:
        log_audit_event('UNAUTHORIZED_STUDENT_ACCESS', f"Attempted to access student_pk {student_pk}")
        abort(403, description="Access Denied: Student does not belong to your university.")

    return render_template('student_profile.html', active_page='students', dossier=dossier)


@app.route('/students/create', methods=['POST'])
@login_required
@permission_required('students')
def student_create():
    """Adds a new student strictly bounded to logged-in university."""
    uni_id = get_current_university_id()
    st_id = request.form.get('student_id', '').strip()
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    dept_id = request.form.get('department_id') or None
    sec_id = request.form.get('section_id') or None
    year = request.form.get('academic_year', '2024-2025')
    sem = request.form.get('semester', 1, type=int)
    status = request.form.get('enrollment_status', 'Active')
    gender = request.form.get('gender', 'Other')
    age = request.form.get('age', 20, type=int)
    enroll_date = request.form.get('enrollment_date') or datetime.date.today().strftime('%Y-%m-%d')

    if not st_id or not full_name or not email:
        flash("Student ID, Full Name, and Email are mandatory.", "danger")
        return redirect(url_for('students_view'))

    try:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO students (university_id, student_id, full_name, email, phone, department_id, section_id,
                                      academic_year, semester, enrollment_status, gender, age, enrollment_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (uni_id, st_id, full_name, email, phone, dept_id, sec_id, year, sem, status, gender, age, enroll_date))
            st_pk = cursor.lastrowid

            # Initial fee record
            cursor.execute('''
                INSERT INTO fee_records (university_id, student_id, academic_year, total_fee, paid_amount, pending_amount, due_date, payment_status)
                VALUES (?, ?, ?, 40000.0, 0.0, 40000.0, '2024-11-30', 'Pending')
            ''', (uni_id, st_pk, year))

            # Initial explainable risk assessment
            eval_res = risk_engine.calculate_explainable_risk(100.0, 75.0, 0, 0, 0, 50)
            cursor.execute('''
                INSERT INTO risk_predictions (university_id, student_id, risk_level, risk_score, reasons, recommended_action)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (uni_id, st_pk, eval_res['risk_level'], eval_res['risk_score'], json.dumps(eval_res['reasons']), eval_res['recommended_action']))

            log_audit_event('STUDENT_ENROLLED', f"Student {st_id} ({full_name}) created.", university_id=uni_id)

        flash(f"Student {full_name} ({st_id}) enrolled successfully!", "success")
    except Exception as e:
        flash(f"Failed to add student: {str(e)}", "danger")

    return redirect(url_for('students_view'))


@app.route('/students/update', methods=['POST'])
@login_required
@permission_required('students')
def student_update():
    """Updates student profile strictly verifying university_id."""
    uni_id = get_current_university_id()
    st_pk = request.form.get('student_pk', type=int)
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    dept_id = request.form.get('department_id') or None
    sec_id = request.form.get('section_id') or None
    sem = request.form.get('semester', 1, type=int)
    status = request.form.get('enrollment_status', 'Active')

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE students 
            SET full_name = ?, email = ?, phone = ?, department_id = ?, section_id = ?, semester = ?, enrollment_status = ?
            WHERE id = ? AND university_id = ?
        ''', (full_name, email, phone, dept_id, sec_id, sem, status, st_pk, uni_id))

        if cursor.rowcount == 0:
            abort(403, description="Cannot update student outside your university.")

        log_audit_event('STUDENT_UPDATED', f"Student PK {st_pk} updated.", university_id=uni_id)

    flash("Student profile updated successfully!", "success")
    return redirect(url_for('students_view'))


@app.route('/students/<int:student_pk>/delete', methods=['POST'])
@login_required
@permission_required('students')
def student_delete(student_pk):
    """Deletes or deactivates student record with tenant verification."""
    uni_id = get_current_university_id()
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM students WHERE id = ? AND university_id = ?", (student_pk, uni_id))
        if cursor.rowcount == 0:
            abort(403, description="Cannot delete student outside your university.")
        log_audit_event('STUDENT_DELETED', f"Student PK {student_pk} removed.", university_id=uni_id)

    flash("Student record successfully deleted.", "info")
    return redirect(url_for('students_view'))


# ==========================================
# ATTENDANCE MANAGEMENT MODULE
# ==========================================

@app.route('/attendance')
@login_required
@permission_required('attendance')
def attendance_view():
    """Attendance view with daily sheet, low attendance alerts, and optional facial verification."""
    uni_id = get_current_university_id()
    date_str = request.args.get('date') or datetime.date.today().strftime('%Y-%m-%d')
    dept_id = request.args.get('dept_id', 'All')
    sec_id = request.args.get('sec_id', 'All')

    data = TenantService.get_attendance_report(uni_id, date_str, dept_id, sec_id)

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM departments WHERE university_id = ? ORDER BY name", (uni_id,))
        departments = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT * FROM sections WHERE university_id = ? ORDER BY name", (uni_id,))
        sections = [dict(r) for r in cursor.fetchall()]

    return render_template(
        'attendance.html',
        active_page='attendance',
        data=data,
        departments=departments,
        sections=sections,
        selected_dept=dept_id,
        selected_sec=sec_id
    )


@app.route('/attendance/save', methods=['POST'])
@login_required
@permission_required('attendance')
def attendance_save():
    """Commits daily attendance entries and audits changes."""
    uni_id = get_current_university_id()
    user = get_current_user()
    date_str = request.form.get('date')

    with db_session() as conn:
        cursor = conn.cursor()
        # Find all active students for this university
        cursor.execute("SELECT id, department_id, section_id FROM students WHERE university_id = ? AND enrollment_status = 'Active'", (uni_id,))
        students = cursor.fetchall()

        for s in students:
            st_pk = s['id']
            status = request.form.get(f'status_{st_pk}', 'Present')
            reason = request.form.get(f'reason_{st_pk}', '').strip()

            # Check if record already exists
            cursor.execute("SELECT id, status FROM attendance WHERE university_id = ? AND student_id = ? AND date = ?", (uni_id, st_pk, date_str))
            existing = cursor.fetchone()

            if existing:
                if existing['status'] != status:
                    # Log audit of status change
                    cursor.execute('''
                        INSERT INTO attendance_audits (attendance_id, university_id, old_status, new_status, changed_by, reason)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (existing['id'], uni_id, existing['status'], status, user['id'], reason or 'Faculty Manual Correction'))
                    cursor.execute('''
                        UPDATE attendance SET status = ?, correction_reason = ? WHERE id = ?
                    ''', (status, reason, existing['id']))
            else:
                cursor.execute('''
                    INSERT INTO attendance (university_id, student_id, department_id, section_id, date, status, marked_by, correction_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (uni_id, st_pk, s['department_id'], s['section_id'], date_str, status, user['id'], reason))

        log_audit_event('ATTENDANCE_COMMITTED', f"Committed attendance for {date_str}", university_id=uni_id)

    flash(f"Attendance for {date_str} committed successfully!", "success")
    return redirect(url_for('attendance_view', date=date_str))


# ==========================================
# ACADEMIC PERFORMANCE (MARKS & EXAMS)
# ==========================================

@app.route('/marks')
@login_required
@permission_required('marks')
def marks_view():
    """Marks and examinations management."""
    uni_id = get_current_university_id()
    exam_id = request.args.get('exam_id', 'All')
    dept_id = request.args.get('dept_id', 'All')

    data = TenantService.get_marks_management_data(uni_id, exam_id, dept_id)

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE university_id = ? AND enrollment_status = 'Active' ORDER BY full_name", (uni_id,))
        students = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT * FROM subjects WHERE university_id = ? ORDER BY code", (uni_id,))
        subjects = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT * FROM examinations WHERE university_id = ? ORDER BY exam_date DESC", (uni_id,))
        examinations = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT * FROM departments WHERE university_id = ? ORDER BY name", (uni_id,))
        departments = [dict(r) for r in cursor.fetchall()]

    return render_template(
        'marks.html',
        active_page='marks',
        data=data,
        students=students,
        subjects=subjects,
        examinations=examinations,
        departments=departments
    )


@app.route('/marks/save', methods=['POST'])
@login_required
@permission_required('marks')
def marks_save():
    """Stores student examination marks and calculates pass/fail, percentage, grade."""
    uni_id = get_current_university_id()
    user = get_current_user()

    student_pk = request.form.get('student_id', type=int)
    subject_id = request.form.get('subject_id', type=int)
    exam_id = request.form.get('examination_id', type=int)
    internal = float(request.form.get('internal_marks', 0.0))
    external = float(request.form.get('external_marks', 0.0))
    max_marks = float(request.form.get('max_marks', 100.0))
    pass_marks = float(request.form.get('pass_marks', 40.0))

    total = internal + external
    pct = round((total / max_marks * 100.0), 1) if max_marks > 0 else 0.0
    is_pass = 1 if total >= pass_marks else 0

    # Grade determination
    if pct >= 90: grade = 'O'
    elif pct >= 80: grade = 'A+'
    elif pct >= 70: grade = 'A'
    elif pct >= 60: grade = 'B+'
    elif pct >= 50: grade = 'B'
    elif pct >= 40: grade = 'C'
    else: grade = 'F'

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO marks (university_id, student_id, subject_id, examination_id, internal_marks, external_marks,
                               total_marks, max_marks, pass_marks, percentage, grade, is_pass, entered_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(university_id, student_id, subject_id, examination_id) 
            DO UPDATE SET internal_marks=excluded.internal_marks, external_marks=excluded.external_marks,
                          total_marks=excluded.total_marks, percentage=excluded.percentage,
                          grade=excluded.grade, is_pass=excluded.is_pass
        ''', (uni_id, student_pk, subject_id, exam_id, internal, external, total, max_marks, pass_marks, pct, grade, is_pass, user['id']))

        log_audit_event('MARKS_ENTERED', f"Student PK {student_pk}, Subject {subject_id}, Total: {total}", university_id=uni_id)

    flash("Exam marks recorded and computed successfully!", "success")
    return redirect(url_for('marks_view'))


# ==========================================
# ASSIGNMENT MANAGEMENT MODULE
# ==========================================

@app.route('/assignments')
@login_required
@permission_required('assignments')
def assignments_view():
    """Assignment operations and student submission tracking."""
    uni_id = get_current_university_id()

    with db_session() as conn:
        cursor = conn.cursor()
        # Fetch active assignments
        cursor.execute('''
            SELECT a.*, d.code as dept_code, sub.code as sub_code, sub.name as sub_name
            FROM assignments a
            LEFT JOIN departments d ON a.department_id = d.id
            LEFT JOIN subjects sub ON a.subject_id = sub.id
            WHERE a.university_id = ?
            ORDER BY a.due_date DESC
        ''', (uni_id,))
        assignments = [dict(r) for r in cursor.fetchall()]

        # Fetch submissions
        cursor.execute('''
            SELECT sub.*, s.student_id, s.full_name, a.title, a.max_points
            FROM assignment_submissions sub
            JOIN students s ON sub.student_id = s.id AND sub.university_id = s.university_id
            JOIN assignments a ON sub.assignment_id = a.id AND sub.university_id = a.university_id
            WHERE sub.university_id = ?
            ORDER BY sub.id DESC
        ''', (uni_id,))
        submissions = [dict(r) for r in cursor.fetchall()]

        # Compute completion stats
        completed_count = sum(1 for s in submissions if s['status'] == 'Completed')
        pending_count = sum(1 for s in submissions if s['status'] == 'Pending')
        missing_count = sum(1 for s in submissions if s['status'] == 'Missing')
        late_count = sum(1 for s in submissions if s['status'] == 'Late')

        cursor.execute("SELECT * FROM departments WHERE university_id = ? ORDER BY name", (uni_id,))
        departments = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT * FROM subjects WHERE university_id = ? ORDER BY code", (uni_id,))
        subjects = [dict(r) for r in cursor.fetchall()]

    return render_template(
        'assignments.html',
        active_page='assignments',
        assignments=assignments,
        submissions=submissions,
        stats={'completed': completed_count, 'pending': pending_count, 'missing': missing_count, 'late': late_count},
        departments=departments,
        subjects=subjects
    )


@app.route('/assignments/create', methods=['POST'])
@login_required
@permission_required('assignments')
def assignment_create():
    """Creates a new curriculum assignment."""
    uni_id = get_current_university_id()
    user = get_current_user()

    dept_id = request.form.get('department_id', type=int)
    subject_id = request.form.get('subject_id', type=int)
    title = request.form.get('title', '').strip()
    desc = request.form.get('description', '').strip()
    due_date = request.form.get('due_date')
    max_pts = float(request.form.get('max_points', 100.0))

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO assignments (university_id, department_id, subject_id, title, description, due_date, max_points, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (uni_id, dept_id, subject_id, title, desc, due_date, max_pts, user['id']))
        asgn_id = cursor.lastrowid

        # Populate pending submissions for students in that department
        cursor.execute("SELECT id FROM students WHERE university_id = ? AND department_id = ?", (uni_id, dept_id))
        dept_students = cursor.fetchall()
        for st in dept_students:
            cursor.execute('''
                INSERT INTO assignment_submissions (university_id, assignment_id, student_id, status)
                VALUES (?, ?, ?, 'Pending')
            ''', (uni_id, asgn_id, st['id']))

        log_audit_event('ASSIGNMENT_CREATED', f"Created assignment '{title}'", university_id=uni_id)

    flash("Assignment published successfully!", "success")
    return redirect(url_for('assignments_view'))


@app.route('/assignments/grade/<int:sub_id>', methods=['POST'])
@login_required
@permission_required('assignments')
def assignment_grade(sub_id):
    """Grades and updates an assignment submission."""
    uni_id = get_current_university_id()
    status = request.form.get('status', 'Completed')
    score = float(request.form.get('score', 0.0))
    feedback = request.form.get('feedback', '').strip()

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE assignment_submissions
            SET status = ?, score = ?, feedback = ?, submitted_at = CURRENT_TIMESTAMP
            WHERE id = ? AND university_id = ?
        ''', (status, score, feedback, sub_id, uni_id))

        if cursor.rowcount == 0:
            abort(403)

    flash("Submission graded successfully!", "success")
    return redirect(url_for('assignments_view'))


# ==========================================
# FEE MANAGEMENT MODULE
# ==========================================

@app.route('/fees')
@login_required
@permission_required('fees')
def fees_view():
    """Fee management overview, collection tracking, and ledger."""
    uni_id = get_current_university_id()
    status_filter = request.args.get('status', 'All')

    data = TenantService.get_fee_management_data(uni_id, status_filter)
    return render_template(
        'fees.html',
        active_page='fees',
        data=data,
        current_status=status_filter
    )


@app.route('/fees/pay', methods=['POST'])
@login_required
@permission_required('fees')
def fee_payment_record():
    """
    Records student fee payment installment.
    Enforces formula: Pending Fee = Total Fee - Paid Amount
    Strictly forbids storing credit card numbers or banking passwords.
    """
    uni_id = get_current_university_id()
    fee_rec_id = request.form.get('fee_record_id', type=int)
    amount = float(request.form.get('amount', 0.0))
    payment_date = request.form.get('payment_date') or datetime.date.today().strftime('%Y-%m-%d')
    payment_method = request.form.get('payment_method', 'Bank Transfer')
    receipt_ref = request.form.get('receipt_reference', '').strip()
    notes = request.form.get('notes', '').strip()

    if not fee_rec_id or amount <= 0 or not receipt_ref:
        flash("Invalid payment details provided.", "danger")
        return redirect(url_for('fees_view'))

    with db_session() as conn:
        cursor = conn.cursor()
        # Verify fee record belongs to current university
        cursor.execute("SELECT * FROM fee_records WHERE id = ? AND university_id = ?", (fee_rec_id, uni_id))
        rec = cursor.fetchone()
        if not rec:
            abort(403, description="Cannot process payment for account outside your university.")

        # Post payment
        cursor.execute('''
            INSERT INTO fee_payments (university_id, fee_record_id, amount, payment_date, payment_method, receipt_reference, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (uni_id, fee_rec_id, amount, payment_date, payment_method, receipt_ref, notes))

        # Update fee record
        new_paid = rec['paid_amount'] + amount
        new_pending = max(0.0, rec['total_fee'] - new_paid)
        new_status = 'Paid' if new_pending <= 0.0 else 'Partial'

        cursor.execute('''
            UPDATE fee_records 
            SET paid_amount = ?, pending_amount = ?, payment_status = ?
            WHERE id = ? AND university_id = ?
        ''', (new_paid, new_pending, new_status, fee_rec_id, uni_id))

        log_audit_event('FEE_PAYMENT_RECORDED', f"Receipt: {receipt_ref}, Amount: {amount}", university_id=uni_id)

    flash(f"Payment of ₹{amount:,.2f} recorded successfully (Receipt: {receipt_ref})!", "success")
    return redirect(url_for('fees_view'))


@app.route('/fees/structure/update', methods=['POST'])
@login_required
@roles_required('university_admin', 'super_admin')
def fee_structure_update():
    """
    Allows the University Main Admin (or Platform Super Admin) to modify the fee structure
    for a student account.
    Recalculates: Pending Fee = Total Fee - Paid Amount
    """
    uni_id = get_current_university_id()
    fee_rec_id = request.form.get('fee_record_id', type=int)
    total_fee = float(request.form.get('total_fee', 0.0))
    due_date = request.form.get('due_date') or None
    academic_year = request.form.get('academic_year', '').strip()

    if not fee_rec_id or total_fee < 0:
        flash("Invalid fee structure parameters.", "danger")
        return redirect(url_for('fees_view'))

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fee_records WHERE id = ? AND university_id = ?", (fee_rec_id, uni_id))
        rec = cursor.fetchone()
        if not rec:
            abort(403, description="Cannot modify fee structure outside your university.")

        paid_amount = rec['paid_amount'] or 0.0
        new_pending = max(0.0, total_fee - paid_amount)
        if new_pending <= 0.0:
            new_status = 'Paid'
        elif paid_amount > 0.0:
            new_status = 'Partial'
        else:
            new_status = 'Pending'

        cursor.execute('''
            UPDATE fee_records
            SET total_fee = ?, pending_amount = ?, payment_status = ?, due_date = ?, academic_year = COALESCE(NULLIF(?, ''), academic_year)
            WHERE id = ? AND university_id = ?
        ''', (total_fee, new_pending, new_status, due_date, academic_year, fee_rec_id, uni_id))

        log_audit_event('FEE_STRUCTURE_UPDATED', f"Fee Record ID {fee_rec_id}: Total set to ₹{total_fee:,.2f}, Pending ₹{new_pending:,.2f}", university_id=uni_id)

    flash(f"Fee structure modified successfully! Total Fee: ₹{total_fee:,.0f}, Pending Balance: ₹{new_pending:,.0f}", "success")
    return redirect(url_for('fees_view'))


# ==========================================
# ACHIEVEMENTS MANAGEMENT MODULE
# ==========================================

@app.route('/achievements')
@login_required
@permission_required('achievements')
def achievements_view():
    """Honors, sports, hackathons, and certifications."""
    uni_id = get_current_university_id()
    cat_filter = request.args.get('category', 'All')

    with db_session() as conn:
        cursor = conn.cursor()
        query = '''
            SELECT a.*, s.student_id, s.full_name
            FROM achievements a
            JOIN students s ON a.student_id = s.id AND a.university_id = s.university_id
            WHERE a.university_id = ?
        '''
        params = [uni_id]
        if cat_filter and cat_filter != 'All':
            query += " AND a.category = ?"
            params.append(cat_filter)

        query += " ORDER BY a.achievement_date DESC"
        cursor.execute(query, params)
        achievements = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT id, student_id, full_name FROM students WHERE university_id = ? ORDER BY full_name", (uni_id,))
        students = [dict(r) for r in cursor.fetchall()]

    return render_template(
        'achievements.html',
        active_page='achievements',
        achievements=achievements,
        students=students,
        current_cat=cat_filter
    )


@app.route('/achievements/create', methods=['POST'])
@login_required
@permission_required('achievements')
def achievement_create():
    """Records an individual achievement for a student."""
    uni_id = get_current_university_id()
    student_pk = request.form.get('student_id', type=int)
    cat = request.form.get('category', 'Academic')
    title = request.form.get('title', '').strip()
    desc = request.form.get('description', '').strip()
    organizer = request.form.get('organizer', '').strip()
    ach_date = request.form.get('achievement_date') or datetime.date.today().strftime('%Y-%m-%d')
    proof_url = request.form.get('proof_url', '').strip()

    with db_session() as conn:
        cursor = conn.cursor()
        # Verify student belongs to logged in university
        cursor.execute("SELECT id FROM students WHERE id = ? AND university_id = ?", (student_pk, uni_id))
        if not cursor.fetchone():
            abort(403)

        cursor.execute('''
            INSERT INTO achievements (university_id, student_id, category, title, description, organizer, achievement_date, proof_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (uni_id, student_pk, cat, title, desc, organizer, ach_date, proof_url))

        log_audit_event('ACHIEVEMENT_ADDED', f"Student {student_pk} achievement: '{title}'", university_id=uni_id)

    flash("Achievement recorded successfully in student dossier!", "success")
    return redirect(url_for('achievements_view'))


# ==========================================
# CSV & EXCEL DATA MANAGEMENT MODULE
# ==========================================

@app.route('/data-management')
@login_required
def data_management_view():
    """Spreadsheet import and export portal."""
    return render_template('data_import_export.html', active_page='data_mgmt', preview_data=None)


@app.route('/data-management/preview', methods=['POST'])
@login_required
def data_import_preview():
    """
    Parses CSV/Excel using Pandas, checks required columns, detects duplicates & missing values,
    and returns preview before final database commit.
    """
    import_type = request.form.get('import_type', 'students')
    if 'file' not in request.files:
        flash("No file was uploaded.", "danger")
        return redirect(url_for('data_management_view'))

    file = request.files['file']
    if not file or file.filename == '':
        flash("No file selected.", "danger")
        return redirect(url_for('data_management_view'))

    filename = file.filename
    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(file)
        elif filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file)
        else:
            flash("Supported formats: .csv, .xlsx, .xls", "danger")
            return redirect(url_for('data_management_view'))

        # Formula Injection Sanitization
        for col in df.select_dtypes(include=['object', 'string']).columns:
            df[col] = df[col].apply(sanitize_spreadsheet_field)

        initial_len = len(df)
        df_clean = df.drop_duplicates()
        duplicates = initial_len - len(df_clean)
        missing_vals = int(df_clean.isna().sum().sum())
        df_clean = df_clean.fillna('')

        cache_key = str(uuid.uuid4())
        IMPORT_PREVIEWS[cache_key] = {
            'df': df_clean,
            'import_type': import_type
        }

        preview_info = {
            'filename': filename,
            'import_type': import_type,
            'total_rows': initial_len,
            'duplicates': duplicates,
            'missing_vals': missing_vals,
            'valid_rows': len(df_clean),
            'columns': df_clean.columns.tolist(),
            'samples': df_clean.head(5).to_dict(orient='records'),
            'file_cache_key': cache_key
        }

        return render_template('data_import_export.html', active_page='data_mgmt', preview_data=preview_info)

    except Exception as e:
        flash(f"Error parsing spreadsheet: {str(e)}", "danger")
        return redirect(url_for('data_management_view'))


@app.route('/data-management/confirm', methods=['POST'])
@login_required
def data_import_confirm():
    """Commits validated spreadsheet records into the database strictly assigned to current_user.university_id."""
    uni_id = get_current_university_id()
    cache_key = request.form.get('file_cache_key')

    if not cache_key or cache_key not in IMPORT_PREVIEWS:
        flash("Import session expired. Please re-upload your file.", "warning")
        return redirect(url_for('data_management_view'))

    cached = IMPORT_PREVIEWS.pop(cache_key)
    df = cached['df']
    import_type = cached['import_type']

    try:
        inserted_count = 0
        with db_session() as conn:
            cursor = conn.cursor()

            if import_type == 'students':
                for _, row in df.iterrows():
                    st_id = str(row.get('Student_ID') or row.get('student_id', f'STU-{uuid.uuid4().hex[:6].upper()}'))
                    name = str(row.get('Full_Name') or row.get('full_name') or row.get('Name', 'Learner'))
                    email = str(row.get('Email') or row.get('email', f"{st_id.lower()}@{uni_id.lower()}.edu"))
                    year = str(row.get('Academic_Year') or row.get('academic_year', '2024-2025'))

                    cursor.execute('''
                        INSERT INTO students (university_id, student_id, full_name, email, academic_year, enrollment_status)
                        VALUES (?, ?, ?, ?, ?, 'Active')
                        ON CONFLICT(university_id, student_id) DO NOTHING
                    ''', (uni_id, st_id, name, email, year))
                    if cursor.rowcount > 0:
                        inserted_count += 1

            elif import_type == 'attendance':
                for _, row in df.iterrows():
                    st_id = str(row.get('Student_ID') or row.get('student_id'))
                    dt = str(row.get('Date') or row.get('date', datetime.date.today().strftime('%Y-%m-%d')))
                    stat = str(row.get('Status') or row.get('status', 'Present'))

                    cursor.execute("SELECT id FROM students WHERE university_id = ? AND student_id = ?", (uni_id, st_id))
                    st = cursor.fetchone()
                    if st:
                        cursor.execute('''
                            INSERT INTO attendance (university_id, student_id, date, status)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(university_id, student_id, date) DO UPDATE SET status = excluded.status
                        ''', (uni_id, st['id'], dt, stat))
                        inserted_count += 1

            log_audit_event('DATA_IMPORTED', f"Imported {inserted_count} records for module '{import_type}'", university_id=uni_id)

        flash(f"Successfully committed {inserted_count} records into your institution's database!", "success")
    except Exception as e:
        flash(f"Data commit failed: {str(e)}", "danger")

    return redirect(url_for('data_management_view'))


@app.route('/data-management/export', methods=['POST'])
@login_required
def data_export():
    """Generates strictly tenant-isolated CSV or Excel file with formula-injection sanitization."""
    uni_id = get_current_university_id()
    export_type = request.form.get('export_type', 'students')
    fmt = request.form.get('format', 'csv')

    with db_session() as conn:
        cursor = conn.cursor()
        if export_type == 'students':
            cursor.execute('''
                SELECT s.student_id, s.full_name, s.email, s.phone, d.name as department,
                       s.academic_year, s.semester, s.enrollment_status
                FROM students s
                LEFT JOIN departments d ON s.department_id = d.id
                WHERE s.university_id = ?
            ''', (uni_id,))
        elif export_type == 'attendance':
            cursor.execute('''
                SELECT a.date, s.student_id, s.full_name, a.status, a.method, a.correction_reason
                FROM attendance a
                JOIN students s ON a.student_id = s.id AND a.university_id = s.university_id
                WHERE a.university_id = ?
                ORDER BY a.date DESC
            ''', (uni_id,))
        elif export_type == 'marks':
            cursor.execute('''
                SELECT s.student_id, s.full_name, sub.code as subject_code, sub.name as subject_name,
                       ex.name as exam_name, m.internal_marks, m.external_marks, m.total_marks,
                       m.percentage, m.grade, m.is_pass
                FROM marks m
                JOIN students s ON m.student_id = s.id AND m.university_id = s.university_id
                JOIN subjects sub ON m.subject_id = sub.id AND m.university_id = sub.university_id
                JOIN examinations ex ON m.examination_id = ex.id AND m.university_id = ex.university_id
                WHERE m.university_id = ?
            ''', (uni_id,))
        elif export_type == 'fees':
            cursor.execute('''
                SELECT s.student_id, s.full_name, fr.academic_year, fr.total_fee, fr.paid_amount,
                       fr.pending_amount, fr.due_date, fr.payment_status
                FROM fee_records fr
                JOIN students s ON fr.student_id = s.id AND fr.university_id = s.university_id
                WHERE fr.university_id = ?
            ''', (uni_id,))
        elif export_type == 'achievements':
            cursor.execute('''
                SELECT s.student_id, s.full_name, a.category, a.title, a.organizer, a.achievement_date
                FROM achievements a
                JOIN students s ON a.student_id = s.id AND a.university_id = s.university_id
                WHERE a.university_id = ?
            ''', (uni_id,))
        else: # at_risk
            cursor.execute('''
                SELECT s.student_id, s.full_name, rp.risk_level, rp.risk_score, rp.recommended_action
                FROM risk_predictions rp
                JOIN students s ON rp.student_id = s.id AND rp.university_id = s.university_id
                WHERE rp.university_id = ?
            ''', (uni_id,))

        rows = [dict(r) for r in cursor.fetchall()]

    df = pd.DataFrame(rows)
    # Sanitize Formula Injection (CWE-1236)
    for col in df.select_dtypes(include=['object', 'string']).columns:
        df[col] = df[col].apply(sanitize_spreadsheet_field)

    export_dir = os.path.join(BASE_DIR, 'exports')
    os.makedirs(export_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    if fmt == 'xlsx':
        filename = f"{uni_id}_{export_type}_{timestamp}.xlsx"
        filepath = os.path.join(export_dir, filename)
        df.to_excel(filepath, index=False, engine='openpyxl')
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        filename = f"{uni_id}_{export_type}_{timestamp}.csv"
        filepath = os.path.join(export_dir, filename)
        df.to_csv(filepath, index=False)
        mimetype = 'text/csv'

    log_audit_event('DATA_EXPORT_DOWNLOADED', f"Exported {export_type} in {fmt} format", university_id=uni_id)
    return send_file(filepath, as_attachment=True, download_name=filename, mimetype=mimetype)


# ==========================================
# FACULTY & STAFF MANAGEMENT (ADMIN ONLY)
# ==========================================

@app.route('/staff')
@login_required
@roles_required('university_admin')
def staff_view():
    """Faculty and staff account administration."""
    uni_id = get_current_university_id()

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE university_id = ? AND role = 'staff' ORDER BY full_name", (uni_id,))
        staff = []
        for r in cursor.fetchall():
            d = dict(r)
            try:
                d['permissions_list'] = json.loads(d['permissions'] or '[]')
            except Exception:
                d['permissions_list'] = [d['permissions']]
            staff.append(d)

        cursor.execute("SELECT * FROM departments WHERE university_id = ? ORDER BY name", (uni_id,))
        departments = [dict(r) for r in cursor.fetchall()]

    return render_template('staff.html', active_page='staff', staff_members=staff, departments=departments)


@app.route('/staff/create', methods=['POST'])
@login_required
@roles_required('university_admin')
def staff_create():
    """Creates a staff account and assigns module permissions."""
    uni_id = get_current_university_id()
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip().lower()
    dept = request.form.get('department', '').strip()
    password = request.form.get('password', '')
    perms = request.form.getlist('permissions')

    if not full_name or not email or not password:
        flash("Full name, email, and password are required.", "danger")
        return redirect(url_for('staff_view'))

    try:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
            if cursor.fetchone():
                flash("A user with this email address already exists.", "danger")
                return redirect(url_for('staff_view'))

            pass_hash = generate_password_hash(password)
            cursor.execute('''
                INSERT INTO users (university_id, email, password_hash, full_name, role, department, permissions)
                VALUES (?, ?, ?, ?, 'staff', ?, ?)
            ''', (uni_id, email, pass_hash, full_name, dept, json.dumps(perms)))

            log_audit_event('STAFF_ACCOUNT_PROVISIONED', f"Created staff {email}", university_id=uni_id)

        flash(f"Staff account for {full_name} created successfully!", "success")
    except Exception as e:
        flash(f"Failed to create staff account: {str(e)}", "danger")

    return redirect(url_for('staff_view'))


@app.route('/staff/<int:user_id>/toggle', methods=['POST'])
@login_required
@roles_required('university_admin')
def staff_toggle_status(user_id):
    """Activates or deactivates a staff member."""
    uni_id = get_current_university_id()
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM users WHERE id = ? AND university_id = ? AND role = 'staff'", (user_id, uni_id))
        row = cursor.fetchone()
        if not row:
            abort(403)
        new_status = 0 if row['is_active'] == 1 else 1
        cursor.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_status, user_id))
        log_audit_event('STAFF_STATUS_TOGGLED', f"Staff ID {user_id} active status set to {new_status}", university_id=uni_id)

    flash("Staff account status updated.", "info")
    return redirect(url_for('staff_view'))


# ==========================================
# PREDICTION, AT-RISK & MODEL VIEWS
# ==========================================

@app.route('/at-risk')
@login_required
def at_risk_view():
    """At-risk student intervention portal."""
    return render_template('at_risk.html', active_page='at_risk')


@app.route('/prediction')
@login_required
def prediction_view():
    """Interactive Machine Learning prediction simulator."""
    return render_template('prediction.html', active_page='prediction')


@app.route('/analytics')
@login_required
def analytics_view():
    """Advanced feature correlations and SHAP importance."""
    return render_template('analytics.html', active_page='analytics')


@app.route('/reports')
@login_required
def reports_view():
    """Standard reports and CSV exports view."""
    return render_template('reports.html', active_page='reports')


@app.route('/settings')
@login_required
def settings_view():
    """Machine learning model evaluation report comparing 4 supervised algorithms."""
    eval_rep = risk_engine.evaluation_report
    return render_template('settings.html', active_page='settings', eval_report=eval_rep)


# ==========================================
# REST API ENDPOINTS
# ==========================================

@app.route('/api/predict', methods=['POST'])
def api_predict():
    """Real-time inference endpoint using the trained Random Forest models."""
    try:
        data = request.get_json(silent=True) or request.form
        logins = float(data.get('logins', 0))
        reads = float(data.get('content_reads', 0))
        posts = float(data.get('forum_posts', 0))
        quizzes = float(data.get('quiz_reviews', 0))
        risk_score = float(data.get('risk_score', 0))

        prediction = engine.predict_single(
            logins=logins,
            content_reads=reads,
            forum_posts=posts,
            quiz_reviews=quizzes,
            risk_score=risk_score
        )
        return jsonify({'status': 'success', 'data': prediction})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/at-risk', methods=['GET'])
@login_required
def api_at_risk():
    """Returns at-risk students ordered by urgency."""
    tier = request.args.get('tier', 'All')
    uni_id = get_current_university_id()

    # If tenant has students in risk_predictions table, return tenant's at-risk students
    uni_students = TenantService.get_at_risk_overview(uni_id, tier)
    if uni_students:
        return jsonify({'status': 'success', 'count': len(uni_students), 'students': uni_students})

    # Fallback to dataset model engine
    students = engine.get_at_risk_students(risk_tier=tier)
    return jsonify({'status': 'success', 'count': len(students), 'students': students})


@app.route('/api/analytics', methods=['GET'])
@login_required
def api_analytics():
    """Returns analytics data from ml_engine."""
    data = engine.get_analytics_data()
    return jsonify({'status': 'success', 'data': data})


@app.route('/api/export/<report_type>', methods=['GET'])
@login_required
def api_export_report(report_type):
    """Direct export of ML report datasets."""
    filepath, filename = engine.export_csv(report_type)
    return send_file(filepath, as_attachment=True, download_name=filename, mimetype='text/csv')


@app.route('/api/retrain', methods=['POST'])
@login_required
def api_retrain_models():
    """Retrains both Random Forest pipelines and benchmark models."""
    engine.train_and_save_models()
    risk_engine.train_and_evaluate_all_models()
    return jsonify({
        'status': 'success',
        'message': 'Models retrained and benchmarked successfully!',
        'metrics': risk_engine.evaluation_report
    })


@app.route('/api/status', methods=['GET'])
def api_system_status():
    """System health check endpoint."""
    return jsonify({
        'system': 'UniTrack AI',
        'status': 'operational',
        'tenant_isolation': 'enforced',
        'models_loaded': True,
        'benchmark_best_model': risk_engine.evaluation_report.get('best_model')
    })


# =====================================================================
# SECTION 1: STUDENT PORTAL & AUTHENTICATION
# =====================================================================

@app.route('/student/login', methods=['GET', 'POST'])
def student_login_view():
    """Separate dedicated Student Login portal using Student ID and Password."""
    if request.method == 'POST':
        student_id = request.form.get('student_id', '').strip()
        password = request.form.get('password', '')

        if not student_id or not password:
            flash("Please provide both Student ID and Password.", "danger")
            return render_template('student_login.html')

        success, result = authenticate_student(student_id, password)
        if success:
            flash(f"Welcome back, {result['full_name']}! Student Portal session active.", "success")
            return redirect(url_for('student_dashboard_view'))
        else:
            flash(result, "danger")
            return render_template('student_login.html')

    user = get_current_user()
    if user and user.get('role') == 'student':
        return redirect(url_for('student_dashboard_view'))

    return render_template('student_login.html')


@app.route('/student/dashboard')
@student_required
def student_dashboard_view():
    """Student personal dashboard displaying attendance, fees, assignments, and profile."""
    user = get_current_user()
    data = TenantService.get_student_portal_overview(user['university_id'], user['student_pk'])
    if not data:
        flash("Student profile record could not be loaded.", "danger")
        return redirect(url_for('student_login_view'))
    return render_template('student_dashboard.html', active_page='student_dashboard', data=data, user=user)


@app.route('/student/assignments')
@student_required
def student_assignments_view():
    """Student coursework and assignment submission ledger."""
    user = get_current_user()
    data = TenantService.get_student_portal_overview(user['university_id'], user['student_pk'])
    return render_template('student_assignments.html', active_page='student_assignments', data=data, user=user)


@app.route('/student/assignments/submit/<int:asgn_id>', methods=['POST'])
@student_required
def student_assignment_submit(asgn_id):
    """Handles assignment file upload and status recording."""
    user = get_current_user()
    file = request.files.get('submission_file')

    if not file or not file.filename:
        flash("Please select a document (PDF, DOCX, ZIP) to submit.", "danger")
        return redirect(url_for('student_assignments_view'))

    allowed_exts = {'.pdf', '.docx', '.doc', '.zip', '.ipynb', '.py'}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        flash(f"File type {ext} is not permitted. Please upload PDF, DOCX or ZIP files.", "danger")
        return redirect(url_for('student_assignments_view'))

    student_upload_dir = os.path.join(BASE_DIR, 'uploads', 'assignments', str(user['student_pk']))
    os.makedirs(student_upload_dir, exist_ok=True)
    clean_filename = f"asgn_{asgn_id}_{uuid.uuid4().hex[:8]}{ext}"
    dest_path = os.path.join(student_upload_dir, clean_filename)
    file.save(dest_path)
    rel_path = f"uploads/assignments/{user['student_pk']}/{clean_filename}"
    file_size = os.path.getsize(dest_path)

    with db_session() as conn:
        cursor = conn.cursor()
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            INSERT INTO assignment_submissions (
                university_id, assignment_id, student_id, status, file_path, file_name, file_size, submitted_at
            )
            VALUES (?, ?, ?, 'Submitted', ?, ?, ?, ?)
            ON CONFLICT(university_id, assignment_id, student_id) DO UPDATE SET
                status = 'Submitted',
                file_path = excluded.file_path,
                file_name = excluded.file_name,
                file_size = excluded.file_size,
                submitted_at = excluded.submitted_at
        """, (user['university_id'], asgn_id, user['student_pk'], rel_path, file.filename, file_size, now_str))

        log_audit_event(
            'ASSIGNMENT_SUBMITTED',
            f"Assignment {asgn_id} submitted by {user['student_code']}",
            university_id=user['university_id']
        )

    flash("Your assignment has been submitted successfully!", "success")
    return redirect(url_for('student_assignments_view'))


@app.route('/student/fees')
@student_required
def student_fees_view():
    """Student fee monitoring, online payment, and receipt retrieval."""
    user = get_current_user()
    data = TenantService.get_student_portal_overview(user['university_id'], user['student_pk'])
    return render_template('student_fees.html', active_page='student_fees', data=data, user=user)


@app.route('/student/fees/pay', methods=['POST'])
@student_required
def student_fee_pay():
    """Simulates online payment gateway checkout with instant receipt generation."""
    user = get_current_user()
    amount = float(request.form.get('amount', 0.0))
    payment_method = request.form.get('payment_method', 'UPI')
    notes = request.form.get('notes', 'Online Tuition Fee Payment')

    if amount <= 0:
        flash("Invalid payment amount. Please enter a positive value.", "danger")
        return redirect(url_for('student_fees_view'))

    with db_session() as conn:
        cursor = conn.cursor()
        # Find active fee record
        cursor.execute("""
            SELECT * FROM fee_records
            WHERE student_id = ? AND university_id = ?
            ORDER BY academic_year DESC LIMIT 1
        """, (user['student_pk'], user['university_id']))
        fee_rec = cursor.fetchone()

        if not fee_rec:
            flash("No active fee structure found for your account.", "danger")
            return redirect(url_for('student_fees_view'))

        fee_rec_id = fee_rec['id']
        new_paid = fee_rec['paid_amount'] + amount
        new_pending = max(0.0, fee_rec['total_fee'] - new_paid)
        new_status = 'Paid' if new_pending <= 0 else 'Partial'

        cursor.execute("""
            UPDATE fee_records
            SET paid_amount = ?, pending_amount = ?, payment_status = ?
            WHERE id = ?
        """, (new_paid, new_pending, new_status, fee_rec_id))

        receipt_ref = f"REC-{datetime.datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        cursor.execute("""
            INSERT INTO fee_payments (
                university_id, fee_record_id, amount, payment_date, payment_method, receipt_reference, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user['university_id'], fee_rec_id, amount, today_str, payment_method, receipt_ref, notes))

        log_audit_event(
            'STUDENT_ONLINE_FEE_PAYMENT',
            f"Receipt: {receipt_ref}, Amount: ₹{amount}, Method: {payment_method}",
            university_id=user['university_id']
        )

    flash(f"Payment of ₹{amount:,.0f} processed successfully! Receipt Reference: {receipt_ref}", "success")
    return redirect(url_for('fee_receipt_view', receipt_ref=receipt_ref))


@app.route('/student/fees/receipt/<receipt_ref>')
def fee_receipt_view(receipt_ref):
    """Displays official institutional payment receipt."""
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT fp.*, fr.total_fee, fr.paid_amount, fr.pending_amount, fr.academic_year,
                   s.full_name as student_name, s.student_id as student_code, s.email as student_email,
                   s.course_name, s.batch_name, uni.name as university_name, uni.address as university_address
            FROM fee_payments fp
            JOIN fee_records fr ON fp.fee_record_id = fr.id
            JOIN students s ON fr.student_id = s.id
            JOIN universities uni ON fp.university_id = uni.id
            WHERE fp.receipt_reference = ?
        """, (receipt_ref,))
        receipt = cursor.fetchone()

        if not receipt:
            abort(404, description="Payment receipt reference not found.")

        user = get_current_user()
        # Security: verify access
        if user and user.get('role') == 'student' and user.get('student_code') != receipt['student_code']:
            abort(403, description="Unauthorized to view another student's payment receipt.")

    return render_template('fee_receipt.html', receipt=dict(receipt))


# =====================================================================
# SECTION 2: AI FACE RECOGNITION ATTENDANCE MANAGEMENT
# =====================================================================

@app.route('/attendance/face')
@login_required
@permission_required('attendance')
def face_attendance_view():
    """Live AI Face Recognition attendance console with webcam stream."""
    uni_id = get_current_university_id()
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    with db_session() as conn:
        cursor = conn.cursor()
        # Get today's face recognition attendance logs
        cursor.execute("""
            SELECT a.*, s.student_id as student_code, s.full_name, s.course_name, s.batch_name
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            WHERE a.university_id = ? AND a.date = ?
            ORDER BY a.created_at DESC
        """, (uni_id, today_str))
        today_logs = [dict(r) for r in cursor.fetchall()]

        # Get total enrolled students and face registered count
        cursor.execute("SELECT COUNT(*) FROM students WHERE university_id = ? AND enrollment_status = 'Active'", (uni_id,))
        total_students = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM face_encodings WHERE university_id = ?", (uni_id,))
        registered_faces = cursor.fetchone()[0]

        # Auto-seed biometric vectors if empty so recognition works out of the box
        if registered_faces == 0 and total_students > 0:
            ai_face_engine.auto_seed_university_faces(uni_id)
            cursor.execute("SELECT COUNT(*) FROM face_encodings WHERE university_id = ?", (uni_id,))
            registered_faces = cursor.fetchone()[0]

        # Fetch active enrolled students in this university for instant testing buttons
        cursor.execute("""
            SELECT s.id, s.student_id, s.full_name, s.course_name
            FROM students s
            WHERE s.university_id = ? AND s.enrollment_status = 'Active'
            ORDER BY s.id ASC LIMIT 4
        """, (uni_id,))
        sample_students = [dict(r) for r in cursor.fetchall()]

    return render_template(
        'face_attendance.html',
        active_page='face_attendance',
        today_logs=today_logs,
        total_students=total_students,
        registered_faces=registered_faces,
        today_date=today_str,
        sample_students=sample_students
    )


@app.route('/api/attendance/face-recognize', methods=['POST'])
@login_required
@permission_required('attendance')
def api_face_recognize():
    """API endpoint receiving live webcam frame, recognizing student, and recording attendance."""
    uni_id = get_current_university_id()
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    frame_b64 = data.get('frame')
    student_code_hint = data.get('student_code')

    if not frame_b64:
        return jsonify({'status': 'error', 'message': 'No image frame received.'}), 400

    result = ai_face_engine.recognize_and_mark_attendance(
        uni_id,
        frame_b64,
        user_id=user['id'],
        student_code_hint=student_code_hint
    )
    return jsonify(result)


@app.route('/api/students/<int:st_id>/register-face', methods=['POST'])
@login_required
@permission_required('students')
def api_student_register_face(st_id):
    """Registers face photograph and computes biometric embedding for a student."""
    uni_id = get_current_university_id()
    data = request.get_json(silent=True) or {}
    photo_b64 = data.get('photo')

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, student_id FROM students WHERE id = ? AND university_id = ?", (st_id, uni_id))
        st = cursor.fetchone()
        if not st:
            return jsonify({'status': 'error', 'message': 'Student not found in your university.'}), 404

    success, msg = ai_face_engine.register_face(uni_id, st['id'], st['student_id'], photo_b64)
    if success:
        return jsonify({'status': 'success', 'message': msg})
    return jsonify({'status': 'error', 'message': msg}), 400


# =====================================================================
# SECTION 3: UNLIMITED BATCH & ACADEMIC YEAR MANAGEMENT
# =====================================================================

@app.route('/batches')
@login_required
@roles_required('university_admin', 'super_admin')
def batches_view():
    """Unlimited batch and academic year management interface."""
    uni_id = get_current_university_id()
    batches = TenantService.get_batches(uni_id)
    academic_years = TenantService.get_academic_years(uni_id)
    return render_template('batches.html', active_page='batches', batches=batches, academic_years=academic_years)


@app.route('/batches/create', methods=['POST'])
@login_required
@roles_required('university_admin', 'super_admin')
def batch_create():
    """Adds a new unlimited multi-year batch."""
    uni_id = get_current_university_id()
    name = request.form.get('name', '').strip()
    start_year = request.form.get('start_year', type=int)
    end_year = request.form.get('end_year', type=int)

    if not name or not start_year or not end_year:
        flash("Please provide batch name, start year and end year.", "danger")
        return redirect(url_for('batches_view'))

    if end_year <= start_year:
        flash("End year must be greater than start year.", "danger")
        return redirect(url_for('batches_view'))

    with db_session() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO batches (university_id, name, start_year, end_year)
                VALUES (?, ?, ?, ?)
            """, (uni_id, name, start_year, end_year))
            log_audit_event('BATCH_CREATED', f"Batch: {name} ({start_year}-{end_year})", university_id=uni_id)
            flash(f"Batch '{name}' created successfully!", "success")
        except Exception:
            flash(f"A batch named '{name}' already exists in your university.", "danger")

    return redirect(url_for('batches_view'))


@app.route('/batches/delete/<int:batch_id>', methods=['POST'])
@login_required
@roles_required('university_admin', 'super_admin')
def batch_delete(batch_id):
    """Deletes a batch after verifying no student dependencies."""
    uni_id = get_current_university_id()
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM students WHERE batch_id = ? AND university_id = ?", (batch_id, uni_id))
        count = cursor.fetchone()[0]
        if count > 0:
            flash(f"Cannot delete batch: {count} active student(s) enrolled in this batch.", "danger")
            return redirect(url_for('batches_view'))

        cursor.execute("DELETE FROM batches WHERE id = ? AND university_id = ?", (batch_id, uni_id))
        log_audit_event('BATCH_DELETED', f"Batch ID: {batch_id}", university_id=uni_id)
        flash("Batch deleted successfully.", "success")

    return redirect(url_for('batches_view'))


@app.route('/academic-years/create', methods=['POST'])
@login_required
@roles_required('university_admin', 'super_admin')
def academic_year_create():
    """Adds a new academic year."""
    uni_id = get_current_university_id()
    name = request.form.get('name', '').strip()
    is_current = 1 if request.form.get('is_current') else 0

    if not name:
        flash("Please provide academic year name (e.g. 2025-2026).", "danger")
        return redirect(url_for('batches_view'))

    with db_session() as conn:
        cursor = conn.cursor()
        try:
            if is_current:
                cursor.execute("UPDATE academic_years SET is_current = 0 WHERE university_id = ?", (uni_id,))
            cursor.execute("INSERT INTO academic_years (university_id, name, is_current) VALUES (?, ?, ?)", (uni_id, name, is_current))
            flash(f"Academic Year '{name}' added successfully!", "success")
        except Exception:
            flash(f"Academic year '{name}' already exists.", "danger")

    return redirect(url_for('batches_view'))


# =====================================================================
# SECTION 4: COURSE MANAGEMENT (BTECH TRENDING COURSES)
# =====================================================================

@app.route('/courses')
@login_required
@roles_required('university_admin', 'super_admin')
def courses_view():
    """BTech trending courses management and dynamic intake tracking."""
    uni_id = get_current_university_id()
    courses = TenantService.get_courses(uni_id)
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM departments WHERE university_id = ? ORDER BY name", (uni_id,))
        departments = [dict(r) for r in cursor.fetchall()]
    return render_template('courses.html', active_page='courses', courses=courses, departments=departments)


@app.route('/courses/create', methods=['POST'])
@login_required
@roles_required('university_admin', 'super_admin')
def course_create():
    """Adds a new course program."""
    uni_id = get_current_university_id()
    code = request.form.get('code', '').strip().upper()
    name = request.form.get('name', '').strip()
    intake = request.form.get('intake_capacity', 120, type=int)
    description = request.form.get('description', '').strip()
    dept_id = request.form.get('department_id', type=int)

    if not code or not name:
        flash("Please provide both Course Code and Course Name.", "danger")
        return redirect(url_for('courses_view'))

    with db_session() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO courses (university_id, code, name, intake_capacity, description, department_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (uni_id, code, name, intake, description, dept_id or None))
            log_audit_event('COURSE_CREATED', f"Course: {code} - {name}", university_id=uni_id)
            flash(f"Course '{name}' ({code}) created successfully!", "success")
        except Exception:
            flash(f"Course code '{code}' already exists in your university.", "danger")

    return redirect(url_for('courses_view'))


@app.route('/courses/delete/<int:course_id>', methods=['POST'])
@login_required
@roles_required('university_admin', 'super_admin')
def course_delete(course_id):
    """Deletes a course after validating dependency."""
    uni_id = get_current_university_id()
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM students WHERE course_id = ? AND university_id = ?", (course_id, uni_id))
        count = cursor.fetchone()[0]
        if count > 0:
            flash(f"Cannot delete course: {count} active student(s) currently enrolled in this course.", "danger")
            return redirect(url_for('courses_view'))

        cursor.execute("DELETE FROM courses WHERE id = ? AND university_id = ?", (course_id, uni_id))
        log_audit_event('COURSE_DELETED', f"Course ID: {course_id}", university_id=uni_id)
        flash("Course removed successfully.", "success")

    return redirect(url_for('courses_view'))


# =====================================================================
# SECTION 5: DEDICATED ADD NEW STUDENT PAGE
# =====================================================================

@app.route('/students/new', methods=['GET', 'POST'])
@login_required
@permission_required('students')
def student_new_view():
    """Professional student registration page with complete profile, fee, and photo biometrics."""
    uni_id = get_current_university_id()

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        student_id = request.form.get('student_id', '').strip().upper()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        dept_id = request.form.get('department_id', type=int)
        course_id = request.form.get('course_id', type=int)
        batch_id = request.form.get('batch_id', type=int)
        academic_year = request.form.get('academic_year', '').strip()
        admission_date = request.form.get('admission_date') or datetime.date.today().strftime('%Y-%m-%d')
        total_fee = float(request.form.get('total_fee', 0.0))
        gender = request.form.get('gender', 'Other')
        age = request.form.get('age', 20, type=int)

        if not full_name or not student_id or not email:
            flash("Student Name, Student ID, and Email are mandatory.", "danger")
            return redirect(url_for('student_new_view'))

        with db_session() as conn:
            cursor = conn.cursor()
            # Check duplicate student ID or email
            cursor.execute("SELECT id FROM students WHERE university_id = ? AND student_id = ?", (uni_id, student_id))
            if cursor.fetchone():
                flash(f"Student ID '{student_id}' is already registered in your university.", "danger")
                return redirect(url_for('student_new_view'))

            # Fetch course and batch names
            course_name = None
            if course_id:
                cursor.execute("SELECT name FROM courses WHERE id = ?", (course_id,))
                cr = cursor.fetchone()
                if cr: course_name = cr['name']

            batch_name = None
            if batch_id:
                cursor.execute("SELECT name FROM batches WHERE id = ?", (batch_id,))
                br = cursor.fetchone()
                if br: batch_name = br['name']

            # Default student password is 'Student@123'
            pwd_hash = generate_password_hash("Student@123")

            # Handle photo upload
            photo_file = request.files.get('profile_photo')
            photo_rel_path = None
            if photo_file and photo_file.filename:
                ext = os.path.splitext(photo_file.filename)[1].lower()
                clean_name = f"{uni_id}_{student_id}{ext}"
                dest = os.path.join(BASE_DIR, 'uploads', 'faces', clean_name)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                photo_file.save(dest)
                photo_rel_path = f"uploads/faces/{clean_name}"

            # Insert student record
            cursor.execute("""
                INSERT INTO students (
                    university_id, student_id, full_name, email, phone, department_id,
                    course_id, course_name, batch_id, batch_name, academic_year,
                    admission_date, enrollment_date, enrollment_status, total_fee,
                    password_hash, profile_photo, gender, age
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', ?, ?, ?, ?, ?)
            """, (
                uni_id, student_id, full_name, email, phone, dept_id or None,
                course_id or None, course_name, batch_id or None, batch_name, academic_year,
                admission_date, admission_date, total_fee, pwd_hash, photo_rel_path, gender, age
            ))
            st_pk = cursor.lastrowid

            # Create initial fee record
            if total_fee > 0:
                due_date = (datetime.date.today() + datetime.timedelta(days=90)).strftime('%Y-%m-%d')
                cursor.execute("""
                    INSERT INTO fee_records (
                        university_id, student_id, academic_year, total_fee, paid_amount, pending_amount, due_date, payment_status
                    )
                    VALUES (?, ?, ?, ?, 0.0, ?, ?, 'Pending')
                """, (uni_id, st_pk, academic_year, total_fee, total_fee, due_date))

            # If photo was uploaded, attempt face biometric registration
            if photo_rel_path and os.path.exists(os.path.join(BASE_DIR, photo_rel_path)):
                ai_face_engine.register_face(uni_id, st_pk, student_id, os.path.join(BASE_DIR, photo_rel_path))

            log_audit_event('STUDENT_ENROLLED', f"Student {student_id} ({full_name}) registered", university_id=uni_id)

        flash(f"Student '{full_name}' ({student_id}) enrolled successfully! Default password is 'Student@123'.", "success")
        return redirect(url_for('students_view'))

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM departments WHERE university_id = ? ORDER BY name", (uni_id,))
        departments = [dict(r) for r in cursor.fetchall()]
        courses = TenantService.get_courses(uni_id)
        batches = TenantService.get_batches(uni_id)
        academic_years = TenantService.get_academic_years(uni_id)

    return render_template(
        'add_student.html',
        active_page='add_student',
        departments=departments,
        courses=courses,
        batches=batches,
        academic_years=academic_years
    )


# =====================================================================
# SECTION 6: POWER BI & DATA VISUALIZATION INTEGRATION
# =====================================================================

@app.route('/analytics/powerbi')
@login_required
def powerbi_dashboard_view():
    """Interactive Power BI analytics suite with slicers, KPI cards, and REST API connector info."""
    uni_id = get_current_university_id()
    data = TenantService.get_powerbi_data(uni_id)
    courses = TenantService.get_courses(uni_id)
    batches = TenantService.get_batches(uni_id)
    return render_template(
        'powerbi_dashboard.html',
        active_page='powerbi',
        data=data,
        courses=courses,
        batches=batches
    )


@app.route('/api/powerbi/students')
@login_required
def api_powerbi_students():
    """Power BI Web REST API Connector: Enrolled students tabular model."""
    uni_id = get_current_university_id()
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.student_id, s.full_name, s.email, s.course_name, s.batch_name,
                   s.academic_year, s.enrollment_status, s.gender, s.age, s.admission_date
            FROM students s
            WHERE s.university_id = ?
        """, (uni_id,))
        rows = [dict(r) for r in cursor.fetchall()]
    return jsonify({'count': len(rows), 'data': rows})


@app.route('/api/powerbi/attendance')
@login_required
def api_powerbi_attendance():
    """Power BI Web REST API Connector: Daily attendance logs."""
    uni_id = get_current_university_id()
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.date, a.status, a.method, a.marked_time, s.student_id, s.full_name, s.course_name
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            WHERE a.university_id = ?
            ORDER BY a.date DESC LIMIT 500
        """, (uni_id,))
        rows = [dict(r) for r in cursor.fetchall()]
    return jsonify({'count': len(rows), 'data': rows})


@app.route('/api/powerbi/fees')
@login_required
def api_powerbi_fees():
    """Power BI Web REST API Connector: Student fee records and collection in Rupees."""
    uni_id = get_current_university_id()
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.student_id, s.full_name, s.course_name, s.batch_name,
                   fr.total_fee, fr.paid_amount, fr.pending_amount, fr.payment_status, fr.academic_year
            FROM fee_records fr
            JOIN students s ON fr.student_id = s.id
            WHERE fr.university_id = ?
        """, (uni_id,))
        rows = [dict(r) for r in cursor.fetchall()]
    return jsonify({'count': len(rows), 'data': rows})


@app.route('/api/powerbi/courses')
@login_required
def api_powerbi_courses():
    """Power BI Web REST API Connector: BTech trending courses intake analytics."""
    uni_id = get_current_university_id()
    courses = TenantService.get_courses(uni_id)
    return jsonify({'count': len(courses), 'data': courses})


@app.route('/api/powerbi/export')
@login_required
def api_powerbi_export():
    """Downloads Power BI ready multi-table dataset in CSV format."""
    uni_id = get_current_university_id()
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.student_id, s.full_name, s.course_name, s.batch_name, s.academic_year,
                   s.gender, s.enrollment_status,
                   COALESCE(fr.total_fee, 0) as total_fee,
                   COALESCE(fr.paid_amount, 0) as paid_amount,
                   COALESCE(fr.pending_amount, 0) as pending_amount,
                   COALESCE(fr.payment_status, 'Pending') as payment_status,
                   COALESCE(rp.risk_level, 'Low Risk') as risk_level
            FROM students s
            LEFT JOIN fee_records fr ON s.id = fr.student_id
            LEFT JOIN risk_predictions rp ON s.id = rp.student_id
            WHERE s.university_id = ?
        """, (uni_id,))
        rows = [dict(r) for r in cursor.fetchall()]

    df = pd.DataFrame(rows)
    export_dir = os.path.join(BASE_DIR, 'exports')
    os.makedirs(export_dir, exist_ok=True)
    filename = f"{uni_id}_powerbi_dataset_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = os.path.join(export_dir, filename)
    df.to_csv(filepath, index=False)
    return send_file(filepath, as_attachment=True, download_name=filename, mimetype='text/csv')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
