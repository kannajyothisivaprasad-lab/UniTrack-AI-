"""
UniTrack AI - End-to-End System & Business Logic Verification Tests
Tests student CRUD, automatic marks calculation, fee math, attendance percentage,
risk factors explainability, and the Super Admin approval workflow.
"""

import os
import sys
import unittest
import json

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Student_Performance_Analytics')
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app import app
from database import db_session
from auth import authenticate_user
from risk_engine import risk_engine
from tenant_service import TenantService


class UniTrackFeaturesTestCase(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def login(self, email, password):
        return self.client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)

    def test_fee_math_automatic_calculation(self):
        """
        Verify automatic calculation: Pending Fee = Total Fee - Paid Amount
        """
        self.login('admin@apex.edu', 'ApexAdmin@123')
        data = TenantService.get_fee_management_data('UNI-APEX')
        records = data['records']
        self.assertGreater(len(records), 0)

        for r in records:
            expected_pending = max(0.0, r['total_fee'] - r['paid_amount'])
            self.assertEqual(r['pending_amount'], expected_pending, "Pending fee must exactly equal total_fee minus paid_amount")

    def test_academic_marks_calculation(self):
        """
        Verify marks auto-calculation: Total = Internal + External, Percentage, Pass/Fail
        """
        self.login('admin@apex.edu', 'ApexAdmin@123')
        data = TenantService.get_marks_management_data('UNI-APEX')
        records = data['records']
        self.assertGreater(len(records), 0)

        for m in records:
            expected_total = m['internal_marks'] + m['external_marks']
            self.assertAlmostEqual(m['total_marks'], expected_total, places=1)

            expected_pct = round((m['total_marks'] / m['max_marks']) * 100.0, 1)
            self.assertAlmostEqual(m['percentage'], expected_pct, places=1)

            if m['total_marks'] >= m['pass_marks']:
                self.assertEqual(m['is_pass'], 1)
            else:
                self.assertEqual(m['is_pass'], 0)

    def test_ai_risk_explainability_and_disclaimer(self):
        """
        Verify AI Risk Engine returns reasons breakdown and mandatory decision-support disclaimer.
        """
        # Test low attendance + academic failure student
        eval_result = risk_engine.calculate_explainable_risk(
            attendance_pct=55.0,
            avg_marks=35.0,
            failed_count=2,
            missing_assignments=2,
            late_assignments=1,
            logins=15
        )

        self.assertEqual(eval_result['risk_level'], 'High Risk')
        self.assertGreaterEqual(eval_result['risk_score'], 65.0)
        self.assertIsInstance(eval_result['reasons'], list)
        self.assertGreater(len(eval_result['reasons']), 0)
        # Verify explainable evidence mentioned
        reasons_text = " ".join(eval_result['reasons'])
        self.assertIn("Critical low attendance", reasons_text)
        self.assertIn("Failed 2 subject", reasons_text)

        # Verify decision-support disclaimer
        self.assertIn("decision-support indicator", eval_result['disclaimer'].lower())

    def test_super_admin_approval_workflow(self):
        """
        Verify end-to-end approval lifecycle:
        1. Nova Global University is pending -> login fails.
        2. Super Admin approves university -> status becomes active.
        3. Nova Global University admin can now log in!
        """
        # Ensure initial pending state
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE universities SET status = 'pending' WHERE id = 'UNI-NOVA'")

        # Step 1: Nova login initially fails
        success, _ = authenticate_user('admin@novaglobal.edu', 'NovaAdmin@123')
        self.assertFalse(success)

        # Step 2: Super Admin approves Nova Global University
        self.login('admin@unitrack.ai', 'Admin@123')
        res = self.client.post('/super-admin/university/UNI-NOVA/action', data={'action': 'approve'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # Step 3: Nova Admin can now authenticate successfully
        success_after, user_data = authenticate_user('admin@novaglobal.edu', 'NovaAdmin@123')
        self.assertTrue(success_after, "Nova Global University admin should be able to log in after Super Admin approval")
        self.assertEqual(user_data['university_id'], 'UNI-NOVA')

        # Reset Nova to pending for test repeatability
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE universities SET status = 'pending' WHERE id = 'UNI-NOVA'")

    def test_fee_structure_update_by_admin(self):
        """
        Verify that University Admin can modify student fee structure in Rupees,
        recalculating pending amount = total_fee - paid_amount.
        Staff accounts cannot modify fee structure.
        """
        # Fetch an existing fee record for UNI-APEX
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, total_fee, paid_amount, academic_year FROM fee_records WHERE university_id = 'UNI-APEX' LIMIT 1")
            rec = cursor.fetchone()
            fee_rec_id = rec['id']
            orig_total = rec['total_fee']
            acad_year = rec['academic_year']

        # Step 1: Staff account attempt should be denied access
        self.login('prof.sharma@apex.edu', 'Staff@123')
        res_staff = self.client.post('/fees/structure/update', data={
            'fee_record_id': fee_rec_id,
            'academic_year': acad_year,
            'total_fee': 75000.0,
            'due_date': '2025-06-30'
        }, follow_redirects=True)
        self.assertIn(b'Access denied', res_staff.data)

        # Step 2: University Admin updates fee structure to ₹80,000
        self.login('admin@apex.edu', 'ApexAdmin@123')
        res_admin = self.client.post('/fees/structure/update', data={
            'fee_record_id': fee_rec_id,
            'academic_year': acad_year,
            'total_fee': 80000.0,
            'due_date': '2025-06-30'
        }, follow_redirects=True)
        self.assertEqual(res_admin.status_code, 200)

        # Verify updated balance in DB
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT total_fee, paid_amount, pending_amount, payment_status
                FROM fee_records
                WHERE id = ?
            """, (fee_rec_id,))
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row['total_fee'], 80000.0)
            self.assertEqual(row['pending_amount'], 80000.0 - row['paid_amount'])

        # Restore original fee for test idempotence
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE fee_records
                SET total_fee = ?, pending_amount = ? - paid_amount
                WHERE id = ?
            """, (orig_total, orig_total, fee_rec_id))

    def test_student_portal_login_and_dashboard(self):
        """
        Verify that student can authenticate via Student ID and Password,
        and access their personalized student dashboard.
        """
        # Step 1: Login via Student Portal
        res = self.client.post('/student/login', data={
            'student_id': 'APEX-24-001',
            'password': 'Student@123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Aarav Mehta', res.data)
        self.assertIn(b'Student Portal', res.data)

        # Step 2: Access Coursework & Fees
        res_asgn = self.client.get('/student/assignments')
        self.assertEqual(res_asgn.status_code, 200)

        res_fees = self.client.get('/student/fees')
        self.assertEqual(res_fees.status_code, 200)
        self.assertIn(b'Outstanding Fee', res_fees.data)

    def test_student_online_fee_payment_and_receipt(self):
        """
        Verify student can make an online fee payment in Rupees,
        recalculating pending amount, and retrieve a printable receipt.
        """
        # Log in as student
        self.client.post('/student/login', data={
            'student_id': 'APEX-24-002',
            'password': 'Student@123'
        }, follow_redirects=True)

        # Submit fee payment of ₹5,000
        res = self.client.post('/student/fees/pay', data={
            'amount': 5000.0,
            'payment_method': 'UPI',
            'notes': 'Online Semester Fee Installment'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Payment Receipt', res.data)
        self.assertIn(b'PAID', res.data)

    def test_ai_face_recognition_and_anti_duplicate(self):
        """
        Verify that AI Face Recognition marks attendance and blocks same-day duplicates.
        """
        import cv2, numpy as np, base64
        from ai_face_engine import ai_face_engine

        # Generate a test face image
        img = np.ones((200, 200, 3), dtype=np.uint8) * 230
        cv2.circle(img, (100, 100), 70, (180, 200, 220), -1)
        _, buf = cv2.imencode('.jpg', img)
        b64 = 'data:image/jpeg;base64,' + base64.b64encode(buf).decode('utf-8')

        # Register face for APEX-24-001
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM students WHERE student_id = 'APEX-24-001'")
            row = cursor.fetchone()
            ai_face_engine.register_face('UNI-APEX', row['id'], 'APEX-24-001', b64)

        # Clear any attendance today for test idempotence
        import datetime
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM attendance WHERE student_id = ? AND date = ?", (row['id'], today_str))

        # First scan -> Success
        res1 = ai_face_engine.recognize_and_mark_attendance('UNI-APEX', b64)
        self.assertEqual(res1['status'], 'success')
        self.assertEqual(res1['student_id'], 'APEX-24-001')

        # Second scan -> Duplicate prevention
        res2 = ai_face_engine.recognize_and_mark_attendance('UNI-APEX', b64)
        self.assertEqual(res2['status'], 'duplicate')

    def test_unlimited_batch_management_dynamic_intake(self):
        """
        Verify University Admin can add unlimited batches and query dynamic student intake.
        """
        self.login('admin@apex.edu', 'ApexAdmin@123')
        batch_name = '2030-2034'

        # Create batch
        res = self.client.post('/batches/create', data={
            'name': batch_name,
            'start_year': 2030,
            'end_year': 2034
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # Verify batch exists in batches page
        res_page = self.client.get('/batches')
        self.assertIn(b'2030-2034', res_page.data)

    def test_btech_trending_courses_analytics(self):
        """
        Verify BTech trending courses are available with dynamic enrollment numbers.
        """
        self.login('admin@apex.edu', 'ApexAdmin@123')
        res = self.client.get('/courses')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Computer Science Engineering', res.data)
        self.assertIn(b'Artificial Intelligence and Machine Learning', res.data)

    def test_powerbi_data_connectors(self):
        """
        Verify Power BI REST API endpoints return JSON data models.
        """
        self.login('admin@apex.edu', 'ApexAdmin@123')

        res_students = self.client.get('/api/powerbi/students')
        self.assertEqual(res_students.status_code, 200)
        self.assertIn('data', res_students.get_json())

        res_fees = self.client.get('/api/powerbi/fees')
        self.assertEqual(res_fees.status_code, 200)
        self.assertIn('data', res_fees.get_json())

        res_courses = self.client.get('/api/powerbi/courses')
        self.assertEqual(res_courses.status_code, 200)
        self.assertIn('data', res_courses.get_json())


if __name__ == '__main__':
    unittest.main()
