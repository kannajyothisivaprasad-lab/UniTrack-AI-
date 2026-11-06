"""
UniTrack AI - Automated Testing & Tenant Isolation Test Suite
Proves strict tenant separation, role-based authorization, account status enforcement,
and security protections.
"""

import os
import sys
import unittest
import json

# Setup paths
APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Student_Performance_Analytics')
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app import app
from database import db_session
from auth import authenticate_user
from tenant_service import sanitize_spreadsheet_field


class UniTrackIsolationTestCase(unittest.TestCase):

    def setUp(self):
        """Configure test client and testing environment."""
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def login_client(self, email, password):
        """Helper to log in a user and persist session cookie in test client."""
        response = self.client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)
        return response

    # ========================================================
    # 1. MULTI-TENANT ISOLATION TESTS
    # ========================================================

    def test_university_a_cannot_access_university_b_student_dossier(self):
        """
        PROVE: University A ('UNI-APEX') cannot access University B ('UNI-PACIFIC')
        student records via direct URL manipulation.
        """
        # Find a student ID belonging to University B (UNI-PACIFIC)
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, student_id FROM students WHERE university_id = 'UNI-PACIFIC' LIMIT 1")
            pacific_student = cursor.fetchone()
            self.assertIsNotNone(pacific_student, "Pacific student should exist in database")
            pacific_student_pk = pacific_student['id']

        # Log in as University A Admin (Dr. Rajesh Sharma, Apex)
        self.login_client('admin@apex.edu', 'ApexAdmin@123')

        # Attempt to access Pacific Student's 360 profile directly via manipulated URL
        res = self.client.get(f'/students/{pacific_student_pk}')

        # Must return 403 Forbidden!
        self.assertEqual(res.status_code, 403, "University A must be forbidden from accessing University B student dossier")

    def test_university_a_cannot_view_university_b_fees(self):
        """
        PROVE: University A fee view contains ZERO records or revenue from University B.
        """
        # Log in as University A Admin
        self.login_client('admin@apex.edu', 'ApexAdmin@123')

        res = self.client.get('/fees')
        self.assertEqual(res.status_code, 200)

        # Response HTML must not contain University B students (PAC-24-101, Liam O'Connor)
        self.assertNotIn(b'PAC-24-101', res.data, "University B student fee records must NOT appear in University A fee ledger")
        self.assertNotIn(b"Liam O'Connor", res.data)

        # But MUST contain Apex students (APEX-24-001, Aarav Mehta)
        self.assertIn(b'APEX-24-001', res.data)

    def test_university_a_cannot_view_university_b_attendance(self):
        """
        PROVE: University A attendance sheet strictly filters out University B students.
        """
        self.login_client('admin@apex.edu', 'ApexAdmin@123')

        res = self.client.get('/attendance')
        self.assertEqual(res.status_code, 200)

        # Pacific student must not be listed in attendance sheet
        self.assertNotIn(b'PAC-24-101', res.data)
        # Apex student must be listed
        self.assertIn(b'APEX-24-001', res.data)

    def test_university_a_export_is_strictly_isolated(self):
        """
        PROVE: University A data export only contains University A records.
        """
        self.login_client('admin@apex.edu', 'ApexAdmin@123')

        res = self.client.post('/data-management/export', data={'export_type': 'students', 'format': 'csv'})
        self.assertEqual(res.status_code, 200)

        csv_text = res.data.decode('utf-8')
        self.assertIn('APEX-24-001', csv_text, "Apex student must be in Apex export")
        self.assertNotIn('PAC-24-101', csv_text, "Pacific student must NOT be in Apex export")

    # ========================================================
    # 2. ROLE-BASED ACCESS CONTROL (RBAC) TESTS
    # ========================================================

    def test_staff_cannot_access_university_admin_pages(self):
        """
        PROVE: University Staff cannot access admin-only pages such as /staff.
        """
        # Log in as Staff (Prof. Ananya Sharma)
        self.login_client('prof.sharma@apex.edu', 'Staff@123')

        # Try to access Admin-only staff provisioning page
        res = self.client.get('/staff', follow_redirects=True)
        # Should be redirected away with warning
        self.assertIn(b'Access denied', res.data, "Staff should be denied access to admin-only staff page")

    def test_non_super_admin_cannot_access_platform_portal(self):
        """
        PROVE: University Admin and Staff cannot access /super-admin.
        """
        self.login_client('admin@apex.edu', 'ApexAdmin@123')
        res = self.client.get('/super-admin', follow_redirects=True)
        self.assertIn(b'Access denied', res.data, "University admin must not access platform super admin portal")

    # ========================================================
    # 3. ACCOUNT STATUS & REGISTRATION TESTS
    # ========================================================

    def test_pending_university_cannot_log_in(self):
        """
        PROVE: Registered university pending approval cannot log in.
        """
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE universities SET status = 'pending' WHERE id = 'UNI-NOVA'")

        success, message = authenticate_user('admin@novaglobal.edu', 'NovaAdmin@123')
        self.assertFalse(success, "Pending university admin must not be allowed to log in")
        self.assertIn("pending", message.lower())

    def test_suspended_university_cannot_log_in(self):
        """
        PROVE: Suspended university accounts are strictly blocked from logging in.
        """
        # Temporarily mark UNI-PACIFIC as suspended in database
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE universities SET status = 'suspended' WHERE id = 'UNI-PACIFIC'")

        success, message = authenticate_user('admin@pacific.edu', 'PacificAdmin@123')
        self.assertFalse(success, "Suspended university accounts must be blocked")
        self.assertIn("suspended", message.lower())

        # Restore Pacific university to active
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE universities SET status = 'active' WHERE id = 'UNI-PACIFIC'")

    # ========================================================
    # 4. SPREADSHEET FORMULA INJECTION SANITIZATION
    # ========================================================

    def test_formula_injection_prevention(self):
        """
        PROVE: Formula injection characters (=, +, -, @) are sanitized with leading quote.
        """
        dangerous_payload = "=cmd|' /C calc'!A0"
        sanitized = sanitize_spreadsheet_field(dangerous_payload)
        self.assertEqual(sanitized, "'=cmd|' /C calc'!A0")

        plus_payload = "+1+2"
        self.assertEqual(sanitize_spreadsheet_field(plus_payload), "'+1+2")

        safe_text = "Standard text"
        self.assertEqual(sanitize_spreadsheet_field(safe_text), "Standard text")


if __name__ == '__main__':
    unittest.main()
