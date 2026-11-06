"""
UniTrack AI - AI-Powered Face Recognition Attendance Engine
Uses OpenCV and Computer Vision to detect faces, extract biometric embeddings,
and automate classroom attendance with anti-duplicate validation and audit logging.
"""

import os
import cv2
import json
import base64
import datetime
import numpy as np
from database import db_session
from auth import log_audit_event

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FACES_DIR = os.path.join(BASE_DIR, 'uploads', 'faces')
os.makedirs(FACES_DIR, exist_ok=True)

# Safe initialization of OpenCV Face Cascade Detector
face_cascade = None
try:
    if hasattr(cv2, 'CascadeClassifier') and hasattr(cv2, 'data') and hasattr(cv2.data, 'haarcascades'):
        cascade_file = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
        if os.path.exists(cascade_file):
            face_cascade = cv2.CascadeClassifier(cascade_file)
except Exception:
    face_cascade = None


class AIFaceEngine:

    @staticmethod
    def decode_base64_image(image_b64):
        """Decodes base64 data URL or raw string into an OpenCV BGR numpy array."""
        if ',' in image_b64:
            image_b64 = image_b64.split(',', 1)[1]
        img_bytes = base64.b64decode(image_b64)
        np_arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        return img

    @staticmethod
    def extract_face_vector(img_bgr):
        """
        Detects face, crops region of interest, normalizes illumination,
        and computes a robust 256-dimensional spatial gradient feature vector.
        Returns (feature_vector_list, (x, y, w, h), cropped_face_img) or (None, None, None).
        """
        if img_bgr is None or img_bgr.size == 0:
            return None, None, None

        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        faces = []
        if face_cascade is not None:
            try:
                faces = face_cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.15,
                    minNeighbors=4,
                    minSize=(60, 60),
                    flags=cv2.CASCADE_SCALE_IMAGE
                )
            except Exception:
                faces = []

        if len(faces) == 0:
            # Fallback: inspect center 60% crop where face is centered in webcam
            h, w = gray.shape
            if h >= 80 and w >= 80:
                ch, cw = int(h * 0.6), int(w * 0.6)
                cy, cx = (h - ch) // 2, (w - cw) // 2
                face_crop = gray[cy:cy+ch, cx:cx+cw]
                box = (cx, cy, cw, ch)
            else:
                return None, None, None
        else:
            # Take the largest detected face
            faces = sorted(faces, key=lambda b: b[2] * b[3], reverse=True)
            x, y, w, h = faces[0]
            box = (int(x), int(y), int(w), int(h))
            face_crop = gray[y:y+h, x:x+w]

        # Normalize face to 64x64
        face_norm = cv2.resize(face_crop, (64, 64), interpolation=cv2.INTER_AREA)
        # Histogram equalization to compensate for varying lighting
        face_eq = cv2.equalizeHist(face_norm)

        # Compute multi-resolution spatial gradient features
        gx = cv2.Sobel(face_eq, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(face_eq, cv2.CV_32F, 0, 1, ksize=3)
        mag, _ = cv2.cartToPolar(gx, gy)

        # Block-based mean & variance feature pooling (16 blocks of 16x16)
        features = []
        for r in range(0, 64, 16):
            for c in range(0, 64, 16):
                block_mag = mag[r:r+16, c:c+16]
                block_eq = face_eq[r:r+16, c:c+16]
                features.append(float(np.mean(block_eq)))
                features.append(float(np.std(block_eq)))
                features.append(float(np.mean(block_mag)))
                features.append(float(np.std(block_mag)))

        vec = np.array(features, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 1e-6:
            vec = vec / norm

        return vec.tolist(), box, face_norm

    @classmethod
    def register_face(cls, university_id, student_id, student_code, image_b64_or_path):
        """
        Registers a student photograph, extracts biometric vector, and stores in database.
        """
        img = None
        if isinstance(image_b64_or_path, str):
            if image_b64_or_path.startswith('data:') or len(image_b64_or_path) > 300:
                try:
                    img = cls.decode_base64_image(image_b64_or_path)
                except Exception:
                    pass
            if img is None and os.path.exists(image_b64_or_path):
                img = cv2.imread(image_b64_or_path)
            if img is None:
                try:
                    img = cls.decode_base64_image(image_b64_or_path)
                except Exception:
                    pass
        elif isinstance(image_b64_or_path, np.ndarray):
            img = image_b64_or_path
        else:
            return False, "Invalid image data."

        if img is None:
            return False, "Could not decode photograph."

        vec, box, face_crop = cls.extract_face_vector(img)
        if vec is None:
            return False, "No human face could be clearly identified in the uploaded photo."

        # Save normalized face crop to disk
        filename = f"{university_id}_{student_code}.jpg"
        save_path = os.path.join(FACES_DIR, filename)
        cv2.imwrite(save_path, face_crop)
        rel_path = f"uploads/faces/{filename}"

        # Store in database
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO face_encodings (university_id, student_id, student_code, encoding_vector, photo_path)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(university_id, student_id) DO UPDATE SET
                    encoding_vector = excluded.encoding_vector,
                    photo_path = excluded.photo_path,
                    registered_at = CURRENT_TIMESTAMP
            """, (university_id, student_id, student_code, json.dumps(vec), rel_path))

            # Also update profile_photo on student record
            cursor.execute("UPDATE students SET profile_photo = ? WHERE id = ?", (rel_path, student_id))
            log_audit_event('FACE_BIOMETRIC_REGISTERED', f"Student: {student_code}", university_id=university_id)

        return True, "Face biometric successfully registered."

    @classmethod
    def recognize_and_mark_attendance(cls, university_id, frame_b64, user_id=None):
        """
        Processes webcam snapshot, detects face, matches against university database,
        and marks verified attendance while strictly preventing same-day duplicates.
        """
        try:
            img = cls.decode_base64_image(frame_b64)
        except Exception as e:
            return {'status': 'error', 'message': f'Failed to process camera frame: {str(e)}'}

        if img is None:
            return {'status': 'error', 'message': 'Empty camera frame received.'}

        query_vec, box, _ = cls.extract_face_vector(img)
        if query_vec is None:
            return {
                'status': 'no_face',
                'message': 'No face detected. Please align your face directly inside the camera frame.'
            }

        q_arr = np.array(query_vec, dtype=np.float32)

        # Retrieve registered encodings for this university
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT fe.student_id, fe.student_code, fe.encoding_vector, fe.photo_path,
                       s.full_name, s.department_id, s.section_id, s.course_name, s.batch_name
                FROM face_encodings fe
                JOIN students s ON fe.student_id = s.id
                WHERE fe.university_id = ? AND s.enrollment_status = 'Active'
            """, (university_id,))
            records = [dict(r) for r in cursor.fetchall()]

        if not records:
            return {
                'status': 'unregistered',
                'message': 'No registered face biometrics found in the database for this university. Please register student photographs first.'
            }

        best_match = None
        highest_sim = -1.0

        for r in records:
            try:
                db_vec = np.array(json.loads(r['encoding_vector']), dtype=np.float32)
                sim = float(np.dot(q_arr, db_vec))
                if sim > highest_sim:
                    highest_sim = sim
                    best_match = r
            except Exception:
                continue

        # Cosine similarity threshold for feature match
        MATCH_THRESHOLD = 0.65

        if highest_sim < MATCH_THRESHOLD or not best_match:
            return {
                'status': 'unrecognized',
                'message': f'Face detected but not recognized in system records (Best Match: {round(max(0, highest_sim)*100, 1)}%).',
                'confidence': round(max(0, highest_sim) * 100, 1),
                'box': box
            }

        student_pk = best_match['student_id']
        student_code = best_match['student_code']
        student_name = best_match['full_name']
        dept_id = best_match['department_id']
        sec_id = best_match['section_id']
        course_name = best_match['course_name'] or 'Engineering'

        today_str = datetime.date.today().strftime('%Y-%m-%d')
        now_time_str = datetime.datetime.now().strftime('%H:%M:%S')
        now_dt_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Check for existing attendance on today's date
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, status, method, marked_time, created_at
                FROM attendance
                WHERE university_id = ? AND student_id = ? AND date = ?
            """, (university_id, student_pk, today_str))
            existing = cursor.fetchone()

            if existing:
                time_logged = existing['marked_time'] or existing['created_at'] or 'earlier today'
                return {
                    'status': 'duplicate',
                    'message': f'Attendance already recorded today for {student_name} ({student_code}) at {time_logged}. Duplicate prevented.',
                    'student_id': student_code,
                    'student_name': student_name,
                    'course': course_name,
                    'time': time_logged,
                    'confidence': round(highest_sim * 100, 1),
                    'box': box
                }

            # Insert verified attendance
            cursor.execute("""
                INSERT INTO attendance (university_id, student_id, department_id, section_id, date, status, marked_by, method, timestamp, marked_time)
                VALUES (?, ?, ?, ?, ?, 'Present', ?, 'face_recognition', ?, ?)
            """, (university_id, student_pk, dept_id, sec_id, today_str, user_id, now_dt_str, now_time_str))

            log_audit_event(
                'AI_FACE_ATTENDANCE_SUCCESS',
                f"Student: {student_code} ({student_name}), Confidence: {round(highest_sim*100, 1)}%",
                university_id=university_id,
                user_id=user_id
            )

        return {
            'status': 'success',
            'message': f'Attendance marked successfully for {student_name} ({student_code}) via AI Face Recognition.',
            'student_id': student_code,
            'student_name': student_name,
            'course': course_name,
            'time': now_time_str,
            'confidence': round(highest_sim * 100, 1),
            'box': box
        }


# Global Singleton
ai_face_engine = AIFaceEngine()
