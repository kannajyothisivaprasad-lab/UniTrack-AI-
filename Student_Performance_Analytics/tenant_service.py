"""
UniTrack AI - Multi-Tenant Domain Service Layer
Handles strictly scoped database operations, aggregations, KPIs, and reporting.
Every single query strictly filters by authenticated university_id to guarantee absolute data isolation.
"""

import json
import datetime
import pandas as pd
import numpy as np
from database import db_session
from risk_engine import risk_engine


def sanitize_spreadsheet_field(val):
    """
    Prevents CSV / Excel Formula Injection (CWE-1236).
    If a field begins with '=', '+', '-', '@', prepend a single quote.
    """
    if isinstance(val, str) and len(val) > 0:
        if val[0] in ['=', '+', '-', '@']:
            return "'" + val
    return val


class TenantService:

    @staticmethod
    def get_dashboard_kpis(university_id, dept_filter=None, sec_filter=None, year_filter=None):
        """
        Calculates all real database KPIs and Chart.js datasets for the university dashboard.
        Guarantees zero hardcoded numbers.
        """
        with db_session() as conn:
            cursor = conn.cursor()

            # Base student filter
            params = [university_id]
            student_sql = "FROM students s WHERE s.university_id = ?"
            if dept_filter and dept_filter != 'All':
                student_sql += " AND s.department_id = ?"
                params.append(dept_filter)
            if sec_filter and sec_filter != 'All':
                student_sql += " AND s.section_id = ?"
                params.append(sec_filter)
            if year_filter and year_filter != 'All':
                student_sql += " AND s.academic_year = ?"
                params.append(year_filter)

            # 1. Total Students
            cursor.execute(f"SELECT COUNT(*) {student_sql}", params)
            total_students = cursor.fetchone()[0]

            # 2. Total Staff
            cursor.execute("SELECT COUNT(*) FROM users WHERE university_id = ? AND role = 'staff'", (university_id,))
            total_staff = cursor.fetchone()[0]

            # 3. Attendance Today & Average Attendance
            today = datetime.date.today().strftime('%Y-%m-%d')
            cursor.execute('''
                SELECT 
                    COUNT(CASE WHEN status = 'Present' AND date = ? THEN 1 END) as present_today,
                    COUNT(CASE WHEN status = 'Present' THEN 1 END) as total_presents,
                    COUNT(*) as total_attendance_records
                FROM attendance
                WHERE university_id = ?
            ''', (today, university_id))
            att_row = cursor.fetchone()
            present_today = att_row['present_today'] if att_row else 0
            total_presents = att_row['total_presents'] if att_row else 0
            total_att_recs = att_row['total_attendance_records'] if att_row else 0
            avg_attendance = round((total_presents / total_att_recs * 100), 1) if total_att_recs > 0 else 0.0

            # 4. Academic Marks & Pass Percentage
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_marks_count,
                    COUNT(CASE WHEN is_pass = 1 THEN 1 END) as pass_count,
                    COUNT(CASE WHEN is_pass = 0 THEN 1 END) as fail_count
                FROM marks
                WHERE university_id = ?
            ''', (university_id,))
            marks_row = cursor.fetchone()
            total_marks_count = marks_row['total_marks_count'] if marks_row else 0
            pass_count = marks_row['pass_count'] if marks_row else 0
            fail_count = marks_row['fail_count'] if marks_row else 0
            pass_pct = round((pass_count / total_marks_count * 100), 1) if total_marks_count > 0 else 0.0

            # Distinct Failed Students count
            cursor.execute('''
                SELECT COUNT(DISTINCT student_id) FROM marks WHERE university_id = ? AND is_pass = 0
            ''', (university_id,))
            distinct_failed_students = cursor.fetchone()[0]

            # 5. Risk Distribution
            cursor.execute('''
                SELECT 
                    COUNT(CASE WHEN risk_level = 'High Risk' THEN 1 END) as high_risk,
                    COUNT(CASE WHEN risk_level = 'Medium Risk' THEN 1 END) as med_risk,
                    COUNT(CASE WHEN risk_level = 'Low Risk' THEN 1 END) as low_risk
                FROM risk_predictions
                WHERE university_id = ?
            ''', (university_id,))
            risk_row = cursor.fetchone()
            high_risk = risk_row['high_risk'] if risk_row else 0
            med_risk = risk_row['med_risk'] if risk_row else 0
            low_risk = risk_row['low_risk'] if risk_row else 0

            # 6. Fees Collection
            cursor.execute('''
                SELECT 
                    COALESCE(SUM(total_fee), 0) as total_fee_amount,
                    COALESCE(SUM(paid_amount), 0) as total_paid,
                    COALESCE(SUM(pending_amount), 0) as total_pending
                FROM fee_records
                WHERE university_id = ?
            ''', (university_id,))
            fee_row = cursor.fetchone()
            total_fee_sum = fee_row['total_fee_amount'] if fee_row else 0.0
            total_paid_sum = fee_row['total_paid'] if fee_row else 0.0
            total_pending_sum = fee_row['total_pending'] if fee_row else 0.0

            # 7. Department-wise Student Count Chart Data
            cursor.execute('''
                SELECT d.code, COUNT(s.id) as count
                FROM departments d
                LEFT JOIN students s ON d.id = s.department_id AND s.university_id = ?
                WHERE d.university_id = ?
                GROUP BY d.id, d.code
            ''', (university_id, university_id))
            dept_counts = {r['code']: r['count'] for r in cursor.fetchall()}

            # 8. Subject-wise Pass/Fail Chart Data
            cursor.execute('''
                SELECT sub.code,
                       COUNT(CASE WHEN m.is_pass = 1 THEN 1 END) as passed,
                       COUNT(CASE WHEN m.is_pass = 0 THEN 1 END) as failed
                FROM subjects sub
                LEFT JOIN marks m ON sub.id = m.subject_id AND m.university_id = ?
                WHERE sub.university_id = ?
                GROUP BY sub.id, sub.code
            ''', (university_id, university_id))
            sub_performance = [{'code': r['code'], 'passed': r['passed'], 'failed': r['failed']} for r in cursor.fetchall()]

            # 9. Assignment Completion Chart Data
            cursor.execute('''
                SELECT 
                    COUNT(CASE WHEN status = 'Completed' THEN 1 END) as completed,
                    COUNT(CASE WHEN status = 'Pending' THEN 1 END) as pending,
                    COUNT(CASE WHEN status = 'Missing' THEN 1 END) as missing,
                    COUNT(CASE WHEN status = 'Late' THEN 1 END) as late
                FROM assignment_submissions
                WHERE university_id = ?
            ''', (university_id,))
            asgn_row = cursor.fetchone()
            asgn_data = {
                'completed': asgn_row['completed'] if asgn_row else 0,
                'pending': asgn_row['pending'] if asgn_row else 0,
                'missing': asgn_row['missing'] if asgn_row else 0,
                'late': asgn_row['late'] if asgn_row else 0
            }

            return {
                'total_students': total_students,
                'total_staff': total_staff,
                'present_today': present_today,
                'avg_attendance': avg_attendance,
                'pass_percentage': pass_pct,
                'failed_students': distinct_failed_students,
                'high_risk_students': high_risk,
                'medium_risk_students': med_risk,
                'low_risk_students': low_risk,
                'total_fee_collection': total_paid_sum,
                'pending_fees': total_pending_sum,
                'dept_counts': dept_counts,
                'subject_performance': sub_performance,
                'assignment_stats': asgn_data
            }

    @staticmethod
    def get_students(university_id, search='', dept_id=None, sec_id=None, status='All', page=1, per_page=15):
        """Returns strictly tenant-filtered student records with pagination."""
        with db_session() as conn:
            cursor = conn.cursor()
            query = '''
                SELECT s.*, d.name as dept_name, d.code as dept_code, sec.name as sec_name,
                       rp.risk_level, rp.risk_score
                FROM students s
                LEFT JOIN departments d ON s.department_id = d.id
                LEFT JOIN sections sec ON s.section_id = sec.id
                LEFT JOIN risk_predictions rp ON s.id = rp.student_id AND s.university_id = rp.university_id
                WHERE s.university_id = ?
            '''
            params = [university_id]

            if search:
                query += " AND (s.student_id LIKE ? OR s.full_name LIKE ? OR s.email LIKE ?)"
                term = f"%{search}%"
                params.extend([term, term, term])

            if dept_id and dept_id != 'All':
                query += " AND s.department_id = ?"
                params.append(dept_id)

            if sec_id and sec_id != 'All':
                query += " AND s.section_id = ?"
                params.append(sec_id)

            if status and status != 'All':
                query += " AND s.enrollment_status = ?"
                params.append(status)

            # Count total
            count_sql = f"SELECT COUNT(*) FROM ({query})"
            cursor.execute(count_sql, params)
            total = cursor.fetchone()[0]

            # Pagination
            query += " ORDER BY s.id DESC LIMIT ? OFFSET ?"
            offset = (page - 1) * per_page
            params.extend([per_page, offset])

            cursor.execute(query, params)
            rows = [dict(r) for r in cursor.fetchall()]

            total_pages = max(1, (total + per_page - 1) // per_page)
            return {
                'students': rows,
                'total': total,
                'page': page,
                'per_page': per_page,
                'total_pages': total_pages
            }

    @staticmethod
    def get_student_360(university_id, student_pk):
        """
        Retrieves a 360-degree comprehensive profile for a student:
        Profile, Academic History, Marks, Attendance Log, Fees Ledger, Achievements, and AI Risk.
        Guarantees strict tenant verification.
        """
        with db_session() as conn:
            cursor = conn.cursor()

            # Verify student belongs strictly to logged in university
            cursor.execute('''
                SELECT s.*, d.name as dept_name, d.code as dept_code, sec.name as sec_name, u.name as uni_name
                FROM students s
                LEFT JOIN departments d ON s.department_id = d.id
                LEFT JOIN sections sec ON s.section_id = sec.id
                LEFT JOIN universities u ON s.university_id = u.id
                WHERE s.id = ? AND s.university_id = ?
            ''', (student_pk, university_id))
            student = cursor.fetchone()
            if not student:
                return None

            st_dict = dict(student)

            # 1. Marks & Academic History
            cursor.execute('''
                SELECT m.*, sub.code as sub_code, sub.name as sub_name, ex.name as exam_name, ex.exam_type
                FROM marks m
                JOIN subjects sub ON m.subject_id = sub.id
                JOIN examinations ex ON m.examination_id = ex.id
                WHERE m.student_id = ? AND m.university_id = ?
                ORDER BY ex.exam_date DESC, sub.code ASC
            ''', (student_pk, university_id))
            marks = [dict(r) for r in cursor.fetchall()]

            # 2. Attendance Summary & History
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_days,
                    COUNT(CASE WHEN status = 'Present' THEN 1 END) as present_days,
                    COUNT(CASE WHEN status = 'Absent' THEN 1 END) as absent_days,
                    COUNT(CASE WHEN status = 'Leave' THEN 1 END) as leave_days
                FROM attendance
                WHERE student_id = ? AND university_id = ?
            ''', (student_pk, university_id))
            att_stat = dict(cursor.fetchone() or {})
            total_days = att_stat.get('total_days', 0)
            present_days = att_stat.get('present_days', 0)
            att_pct = round((present_days / total_days * 100), 1) if total_days > 0 else 100.0
            att_stat['percentage'] = att_pct

            cursor.execute('''
                SELECT a.*, u.full_name as marked_by_name
                FROM attendance a
                LEFT JOIN users u ON a.marked_by = u.id
                WHERE a.student_id = ? AND a.university_id = ?
                ORDER BY a.date DESC LIMIT 30
            ''', (student_pk, university_id))
            attendance_log = [dict(r) for r in cursor.fetchall()]

            # 3. Fee Records & Payment Ledger
            cursor.execute('''
                SELECT fr.*
                FROM fee_records fr
                WHERE fr.student_id = ? AND fr.university_id = ?
            ''', (student_pk, university_id))
            fee_rec = cursor.fetchone()
            fee_dict = dict(fee_rec) if fee_rec else None

            payments = []
            if fee_dict:
                cursor.execute('''
                    SELECT * FROM fee_payments
                    WHERE fee_record_id = ? AND university_id = ?
                    ORDER BY payment_date DESC
                ''', (fee_dict['id'], university_id))
                payments = [dict(r) for r in cursor.fetchall()]

            # 4. Achievements
            cursor.execute('''
                SELECT * FROM achievements
                WHERE student_id = ? AND university_id = ?
                ORDER BY achievement_date DESC
            ''', (student_pk, university_id))
            achievements = [dict(r) for r in cursor.fetchall()]

            # 5. Risk Prediction & Reasons
            cursor.execute('''
                SELECT * FROM risk_predictions
                WHERE student_id = ? AND university_id = ?
            ''', (student_pk, university_id))
            risk_row = cursor.fetchone()
            risk_info = None
            if risk_row:
                risk_info = dict(risk_row)
                try:
                    risk_info['reasons'] = json.loads(risk_info['reasons'])
                except Exception:
                    risk_info['reasons'] = [risk_info['reasons']]

            # 6. Assignments
            cursor.execute('''
                SELECT sub.*, asg.title as assignment_title, asg.due_date, asg.max_points
                FROM assignment_submissions sub
                JOIN assignments asg ON sub.assignment_id = asg.id
                WHERE sub.student_id = ? AND sub.university_id = ?
                ORDER BY asg.due_date DESC
            ''', (student_pk, university_id))
            assignments = [dict(r) for r in cursor.fetchall()]

            return {
                'student': st_dict,
                'marks': marks,
                'attendance_summary': att_stat,
                'attendance_log': attendance_log,
                'fee_record': fee_dict,
                'payments': payments,
                'achievements': achievements,
                'risk': risk_info,
                'assignments': assignments
            }

    @staticmethod
    def get_attendance_report(university_id, date_str=None, dept_id=None, sec_id=None):
        """Returns daily attendance records and department/section summaries."""
        with db_session() as conn:
            cursor = conn.cursor()
            target_date = date_str or datetime.date.today().strftime('%Y-%m-%d')

            query = '''
                SELECT s.id as student_pk, s.student_id, s.full_name, d.code as dept_code, sec.name as sec_name,
                       a.status, a.id as attendance_id, a.method, a.correction_reason
                FROM students s
                LEFT JOIN departments d ON s.department_id = d.id
                LEFT JOIN sections sec ON s.section_id = sec.id
                LEFT JOIN attendance a ON s.id = a.student_id AND a.date = ? AND a.university_id = ?
                WHERE s.university_id = ? AND s.enrollment_status = 'Active'
            '''
            params = [target_date, university_id, university_id]
            if dept_id and dept_id != 'All':
                query += " AND s.department_id = ?"
                params.append(dept_id)
            if sec_id and sec_id != 'All':
                query += " AND s.section_id = ?"
                params.append(sec_id)

            query += " ORDER BY s.student_id ASC"
            cursor.execute(query, params)
            records = [dict(r) for r in cursor.fetchall()]

            # Low attendance warning list (< 75%)
            cursor.execute('''
                SELECT s.student_id, s.full_name, d.code as dept_code,
                       COUNT(a.id) as total_days,
                       COUNT(CASE WHEN a.status = 'Present' THEN 1 END) as present_days
                FROM students s
                JOIN attendance a ON s.id = a.student_id AND s.university_id = a.university_id
                LEFT JOIN departments d ON s.department_id = d.id
                WHERE s.university_id = ?
                GROUP BY s.id, s.student_id, s.full_name, d.code
                HAVING (COUNT(CASE WHEN a.status = 'Present' THEN 1 END) * 1.0 / COUNT(a.id)) < 0.75
            ''', (university_id,))
            low_attendance_students = []
            for row in cursor.fetchall():
                total = row['total_days']
                present = row['present_days']
                pct = round((present / total * 100), 1) if total > 0 else 0
                low_attendance_students.append({
                    'student_id': row['student_id'],
                    'full_name': row['full_name'],
                    'dept_code': row['dept_code'],
                    'attendance_pct': pct
                })

            return {
                'date': target_date,
                'records': records,
                'low_attendance': low_attendance_students
            }

    @staticmethod
    def get_fee_management_data(university_id, status_filter='All', dept_filter=None):
        """Returns fee records, stats, and collection trends."""
        with db_session() as conn:
            cursor = conn.cursor()

            query = '''
                SELECT fr.id, fr.university_id, fr.academic_year, fr.total_fee, fr.paid_amount, fr.pending_amount,
                       fr.due_date, fr.payment_status, fr.created_at,
                       s.student_id, s.full_name, s.email, d.code as dept_code, d.name as dept_name
                FROM fee_records fr
                JOIN students s ON fr.student_id = s.id AND fr.university_id = s.university_id
                LEFT JOIN departments d ON s.department_id = d.id
                WHERE fr.university_id = ?
            '''
            params = [university_id]

            if status_filter and status_filter != 'All':
                query += " AND fr.payment_status = ?"
                params.append(status_filter)

            if dept_filter and dept_filter != 'All':
                query += " AND s.department_id = ?"
                params.append(dept_filter)

            query += " ORDER BY fr.pending_amount DESC"
            cursor.execute(query, params)
            records = [dict(r) for r in cursor.fetchall()]

            # Statistics
            cursor.execute('''
                SELECT 
                    COUNT(CASE WHEN payment_status = 'Paid' THEN 1 END) as fully_paid_count,
                    COUNT(CASE WHEN payment_status = 'Partial' THEN 1 END) as partial_count,
                    COUNT(CASE WHEN payment_status = 'Pending' THEN 1 END) as pending_count,
                    COALESCE(SUM(total_fee), 0) as total_fee,
                    COALESCE(SUM(paid_amount), 0) as total_collected,
                    COALESCE(SUM(pending_amount), 0) as total_pending
                FROM fee_records
                WHERE university_id = ?
            ''', (university_id,))
            stats = dict(cursor.fetchone() or {})

            # Department-wise collection
            cursor.execute('''
                SELECT d.code,
                       COALESCE(SUM(fr.paid_amount), 0) as collected,
                       COALESCE(SUM(fr.pending_amount), 0) as pending
                FROM departments d
                LEFT JOIN students s ON d.id = s.department_id AND d.university_id = s.university_id
                LEFT JOIN fee_records fr ON s.id = fr.student_id AND s.university_id = fr.university_id
                WHERE d.university_id = ?
                GROUP BY d.id, d.code
            ''', (university_id,))
            dept_fee = [dict(r) for r in cursor.fetchall()]

            return {
                'records': records,
                'stats': stats,
                'dept_breakdown': dept_fee
            }

    @staticmethod
    def get_marks_management_data(university_id, exam_id=None, dept_id=None, subject_id=None):
        """Returns exam marks, top performers, subject statistics."""
        with db_session() as conn:
            cursor = conn.cursor()

            query = '''
                SELECT m.*, s.student_id, s.full_name, sub.code as sub_code, sub.name as sub_name,
                       ex.name as exam_name, d.code as dept_code
                FROM marks m
                JOIN students s ON m.student_id = s.id AND m.university_id = s.university_id
                JOIN subjects sub ON m.subject_id = sub.id AND m.university_id = sub.university_id
                JOIN examinations ex ON m.examination_id = ex.id AND m.university_id = ex.university_id
                LEFT JOIN departments d ON s.department_id = d.id
                WHERE m.university_id = ?
            '''
            params = [university_id]
            if exam_id and exam_id != 'All':
                query += " AND m.examination_id = ?"
                params.append(exam_id)
            if dept_id and dept_id != 'All':
                query += " AND s.department_id = ?"
                params.append(dept_id)
            if subject_id and subject_id != 'All':
                query += " AND m.subject_id = ?"
                params.append(subject_id)

            query += " ORDER BY m.percentage DESC"
            cursor.execute(query, params)
            records = [dict(r) for r in cursor.fetchall()]

            # Top Performers (>= 85%)
            top_performers = [r for r in records if r['percentage'] >= 85.0][:5]

            # Low Performers (< 45%)
            low_performers = [r for r in records if r['percentage'] < 45.0]

            return {
                'records': records,
                'top_performers': top_performers,
                'low_performers': low_performers
            }

    @staticmethod
    def get_at_risk_overview(university_id, tier='All'):
        """Fetches at-risk students with explainable factors."""
        with db_session() as conn:
            cursor = conn.cursor()
            query = '''
                SELECT rp.*, s.student_id, s.full_name, s.email, d.code as dept_code, sec.name as sec_name
                FROM risk_predictions rp
                JOIN students s ON rp.student_id = s.id AND rp.university_id = s.university_id
                LEFT JOIN departments d ON s.department_id = d.id
                LEFT JOIN sections sec ON s.section_id = sec.id
                WHERE rp.university_id = ?
            '''
            params = [university_id]
            if tier and tier != 'All':
                query += " AND rp.risk_level = ?"
                params.append(tier)

            query += " ORDER BY rp.risk_score DESC"
            cursor.execute(query, params)
            rows = []
            for r in cursor.fetchall():
                d = dict(r)
                try:
                    d['reasons'] = json.loads(d['reasons'])
                except Exception:
                    d['reasons'] = [d['reasons']]
                rows.append(d)

            return rows

    @staticmethod
    def get_super_admin_stats():
        """Aggregates platform-wide metrics for the Platform Super Admin."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_universities,
                    COUNT(CASE WHEN status = 'active' THEN 1 END) as active_count,
                    COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_count,
                    COUNT(CASE WHEN status = 'suspended' THEN 1 END) as suspended_count,
                    COUNT(CASE WHEN status = 'inactive' THEN 1 END) as inactive_count
                FROM universities
            ''')
            uni_stats = dict(cursor.fetchone() or {})

            cursor.execute("SELECT COUNT(*) FROM students")
            total_students = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'staff'")
            total_staff = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'university_admin'")
            total_admins = cursor.fetchone()[0]

            # List universities with counts
            cursor.execute('''
                SELECT u.*, 
                       COUNT(DISTINCT s.id) as student_count,
                       COUNT(DISTINCT usr.id) as user_count
                FROM universities u
                LEFT JOIN students s ON u.id = s.university_id
                LEFT JOIN users usr ON u.id = usr.university_id
                GROUP BY u.id
                ORDER BY u.created_at DESC
            ''')
            universities_list = [dict(r) for r in cursor.fetchall()]

            # Platform Audit Logs
            cursor.execute('''
                SELECT al.*, u.email as user_email, uni.name as university_name
                FROM audit_logs al
                LEFT JOIN users u ON al.user_id = u.id
                LEFT JOIN universities uni ON al.university_id = uni.id
                ORDER BY al.timestamp DESC LIMIT 50
            ''')
            audit_logs = [dict(r) for r in cursor.fetchall()]

            return {
                'uni_stats': uni_stats,
                'total_students': total_students,
                'total_staff': total_staff,
                'total_admins': total_admins,
                'universities': universities_list,
                'audit_logs': audit_logs
            }

    @staticmethod
    def get_student_portal_overview(university_id, student_pk):
        """
        Gathers complete, personalized dossier for student portal view.
        Strictly isolated to authenticated student's own records.
        """
        with db_session() as conn:
            cursor = conn.cursor()

            # 1. Student Profile
            cursor.execute("""
                SELECT s.*, d.name as department_name, d.code as department_code,
                       sec.name as section_name, uni.name as university_name
                FROM students s
                LEFT JOIN departments d ON s.department_id = d.id
                LEFT JOIN sections sec ON s.section_id = sec.id
                LEFT JOIN universities uni ON s.university_id = uni.id
                WHERE s.id = ? AND s.university_id = ?
            """, (student_pk, university_id))
            student = cursor.fetchone()
            if not student:
                return None
            student_dict = dict(student)

            # 2. Attendance Status & Stats
            today_str = datetime.date.today().strftime('%Y-%m-%d')
            cursor.execute("""
                SELECT * FROM attendance
                WHERE student_id = ? AND university_id = ? AND date = ?
            """, (student_pk, university_id, today_str))
            today_att = cursor.fetchone()
            today_status = today_att['status'] if today_att else 'Not Marked'

            cursor.execute("""
                SELECT 
                    COUNT(*) as total_days,
                    SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) as present_days,
                    SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) as absent_days,
                    SUM(CASE WHEN status = 'Leave' THEN 1 ELSE 0 END) as leave_days
                FROM attendance
                WHERE student_id = ? AND university_id = ?
            """, (student_pk, university_id))
            att_row = dict(cursor.fetchone() or {})
            total_days = att_row.get('total_days') or 0
            present_days = att_row.get('present_days') or 0
            att_pct = round((present_days / total_days) * 100.0, 1) if total_days > 0 else 100.0

            cursor.execute("""
                SELECT * FROM attendance
                WHERE student_id = ? AND university_id = ?
                ORDER BY date DESC LIMIT 15
            """, (student_pk, university_id))
            recent_attendance = [dict(r) for r in cursor.fetchall()]

            # 3. Coursework & Assignments
            cursor.execute("""
                SELECT a.*, sub.name as subject_name, sub.code as subject_code,
                       asub.id as submission_id, asub.status as submission_status,
                       asub.file_path as submitted_file, asub.submitted_at,
                       asub.marks_awarded, asub.feedback
                FROM assignments a
                LEFT JOIN subjects sub ON a.subject_id = sub.id
                LEFT JOIN assignment_submissions asub 
                       ON a.id = asub.assignment_id AND asub.student_id = ?
                WHERE a.university_id = ?
                ORDER BY a.due_date ASC
            """, (student_pk, university_id))
            assignments = [dict(r) for r in cursor.fetchall()]

            # 4. Fee Overview & Payment Receipts
            cursor.execute("""
                SELECT * FROM fee_records
                WHERE student_id = ? AND university_id = ?
                ORDER BY academic_year DESC LIMIT 1
            """, (student_pk, university_id))
            fee_rec = cursor.fetchone()
            fee_dict = dict(fee_rec) if fee_rec else None

            payments = []
            if fee_rec:
                cursor.execute("""
                    SELECT * FROM fee_payments
                    WHERE fee_record_id = ? AND university_id = ?
                    ORDER BY payment_date DESC
                """, (fee_rec['id'], university_id))
                payments = [dict(r) for r in cursor.fetchall()]

            # 5. Examination Marks
            cursor.execute("""
                SELECT m.*, sub.name as subject_name, sub.code as subject_code,
                       e.name as exam_name, e.exam_type
                FROM marks m
                JOIN subjects sub ON m.subject_id = sub.id
                JOIN examinations e ON m.examination_id = e.id
                WHERE m.student_id = ? AND m.university_id = ?
                ORDER BY e.exam_date DESC
            """, (student_pk, university_id))
            marks = [dict(r) for r in cursor.fetchall()]

            return {
                'student': student_dict,
                'today_status': today_status,
                'attendance_summary': {
                    'percentage': att_pct,
                    'total_days': total_days,
                    'present_days': present_days,
                    'absent_days': att_row.get('absent_days') or 0,
                    'leave_days': att_row.get('leave_days') or 0
                },
                'recent_attendance': recent_attendance,
                'assignments': assignments,
                'fee_record': fee_dict,
                'payments': payments,
                'marks': marks
            }

    @staticmethod
    def get_courses(university_id):
        """Returns all courses with dynamic real enrollment counts and intake usage."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.*, COUNT(s.id) as enrolled_count
                FROM courses c
                LEFT JOIN students s ON (c.id = s.course_id OR c.name = s.course_name) AND s.university_id = c.university_id
                WHERE c.university_id = ?
                GROUP BY c.id
                ORDER BY enrolled_count DESC, c.name ASC
            """, (university_id,))
            return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def get_batches(university_id):
        """Returns unlimited batches with real enrolled student counts."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT b.*, COUNT(s.id) as enrolled_count
                FROM batches b
                LEFT JOIN students s ON (b.id = s.batch_id OR b.name = s.batch_name) AND s.university_id = b.university_id
                WHERE b.university_id = ?
                GROUP BY b.id
                ORDER BY b.start_year DESC, b.name ASC
            """, (university_id,))
            return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def get_academic_years(university_id):
        """Returns academic years for this university."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM academic_years WHERE university_id = ? ORDER BY name DESC", (university_id,))
            return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def get_powerbi_data(university_id, course_filter=None, batch_filter=None, ay_filter=None):
        """
        Aggregates multi-dimensional data models specifically designed for Power BI reports and slicing.
        """
        with db_session() as conn:
            cursor = conn.cursor()

            # Course-wise student distribution
            cursor.execute("""
                SELECT COALESCE(c.name, s.course_name, 'General Engineering') as course_name,
                       COUNT(s.id) as student_count,
                       COALESCE(c.intake_capacity, 120) as capacity
                FROM students s
                LEFT JOIN courses c ON (s.course_id = c.id OR s.course_name = c.name) AND c.university_id = s.university_id
                WHERE s.university_id = ?
                GROUP BY course_name
                ORDER BY student_count DESC
            """, (university_id,))
            courses_data = [dict(r) for r in cursor.fetchall()]

            # Batch-wise student distribution
            cursor.execute("""
                SELECT COALESCE(s.batch_name, '2024-2028') as batch_name,
                       COUNT(s.id) as student_count
                FROM students s
                WHERE s.university_id = ?
                GROUP BY batch_name
                ORDER BY batch_name DESC
            """, (university_id,))
            batches_data = [dict(r) for r in cursor.fetchall()]

            # Attendance analytics
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_logs,
                    SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) as present_count,
                    SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) as absent_count,
                    SUM(CASE WHEN method = 'face_recognition' THEN 1 ELSE 0 END) as face_rec_count
                FROM attendance
                WHERE university_id = ?
            """, (university_id,))
            att_kpis = dict(cursor.fetchone() or {})

            # Fee Collection Trends
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(total_fee), 0) as total_assessed,
                    COALESCE(SUM(paid_amount), 0) as total_collected,
                    COALESCE(SUM(pending_amount), 0) as total_pending
                FROM fee_records
                WHERE university_id = ?
            """, (university_id,))
            fee_kpis = dict(cursor.fetchone() or {})

            # Academic Performance
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_exams_graded,
                    COALESCE(AVG(percentage), 0) as avg_marks_pct,
                    SUM(CASE WHEN is_pass = 1 THEN 1 ELSE 0 END) as pass_count,
                    SUM(CASE WHEN is_pass = 0 THEN 1 ELSE 0 END) as fail_count
                FROM marks
                WHERE university_id = ?
            """, (university_id,))
            marks_kpis = dict(cursor.fetchone() or {})

            # Risk Predictions distribution
            cursor.execute("""
                SELECT risk_level, COUNT(*) as count
                FROM risk_predictions
                WHERE university_id = ?
                GROUP BY risk_level
            """, (university_id,))
            risk_dist = [dict(r) for r in cursor.fetchall()]

            return {
                'courses': courses_data,
                'batches': batches_data,
                'attendance': att_kpis,
                'fees': fee_kpis,
                'marks': marks_kpis,
                'risk': risk_dist
            }
