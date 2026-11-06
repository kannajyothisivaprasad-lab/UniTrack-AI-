-- =====================================================================
-- UniTrack AI - Multi-University Management & Student Analytics System
-- Production MySQL 8.0+ Database Schema Definition
-- Engine: InnoDB | Character Set: utf8mb4 | Collation: utf8mb4_unicode_ci
-- =====================================================================

CREATE DATABASE IF NOT EXISTS `unitrack_ai`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `unitrack_ai`;

SET FOREIGN_KEY_CHECKS = 0;

-- 1. UNIVERSITIES TABLE
DROP TABLE IF EXISTS `universities`;
CREATE TABLE `universities` (
  `id` VARCHAR(64) NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `email` VARCHAR(255) NOT NULL,
  `address` TEXT NULL,
  `status` ENUM('pending', 'active', 'suspended', 'inactive') NOT NULL DEFAULT 'pending',
  `subscription_plan` VARCHAR(64) DEFAULT 'Standard',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `approved_at` TIMESTAMP NULL,
  `approved_by` VARCHAR(255) NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_uni_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. USERS (ADMINS & STAFF) TABLE
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NULL,
  `email` VARCHAR(255) NOT NULL,
  `password_hash` VARCHAR(255) NOT NULL,
  `full_name` VARCHAR(255) NOT NULL,
  `role` ENUM('super_admin', 'university_admin', 'staff', 'student') NOT NULL,
  `department` VARCHAR(255) NULL,
  `permissions` JSON NULL,
  `is_active` TINYINT(1) DEFAULT 1,
  `failed_logins` INT DEFAULT 0,
  `locked_until` TIMESTAMP NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_user_email` (`email`),
  KEY `idx_user_uni` (`university_id`),
  CONSTRAINT `fk_users_university` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. DEPARTMENTS TABLE
DROP TABLE IF EXISTS `departments`;
CREATE TABLE `departments` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NOT NULL,
  `code` VARCHAR(64) NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `head_of_dept` VARCHAR(255) NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_dept_uni_code` (`university_id`, `code`),
  CONSTRAINT `fk_dept_university` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. COURSES TABLE (BTECH TRENDING COURSES)
DROP TABLE IF EXISTS `courses`;
CREATE TABLE `courses` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NOT NULL,
  `code` VARCHAR(64) NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `description` TEXT NULL,
  `intake_capacity` INT DEFAULT 120,
  `department_id` INT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_course_uni_code` (`university_id`, `code`),
  KEY `idx_course_dept` (`department_id`),
  CONSTRAINT `fk_course_university` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_course_dept` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. BATCHES TABLE (UNLIMITED MULTI-YEAR BATCHES)
DROP TABLE IF EXISTS `batches`;
CREATE TABLE `batches` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NOT NULL,
  `name` VARCHAR(128) NOT NULL,
  `start_year` INT NOT NULL,
  `end_year` INT NOT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_batch_uni_name` (`university_id`, `name`),
  CONSTRAINT `fk_batch_university` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. ACADEMIC YEARS TABLE
DROP TABLE IF EXISTS `academic_years`;
CREATE TABLE `academic_years` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NOT NULL,
  `name` VARCHAR(128) NOT NULL,
  `is_current` TINYINT(1) DEFAULT 1,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_ay_uni_name` (`university_id`, `name`),
  CONSTRAINT `fk_ay_university` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. SECTIONS TABLE
DROP TABLE IF EXISTS `sections`;
CREATE TABLE `sections` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NOT NULL,
  `department_id` INT NOT NULL,
  `name` VARCHAR(128) NOT NULL,
  `academic_year` VARCHAR(64) NOT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_sec_uni_dept_name` (`university_id`, `department_id`, `name`, `academic_year`),
  KEY `idx_sec_dept` (`department_id`),
  CONSTRAINT `fk_sec_university` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_sec_department` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8. STUDENTS TABLE
DROP TABLE IF EXISTS `students`;
CREATE TABLE `students` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NOT NULL,
  `student_id` VARCHAR(64) NOT NULL,
  `full_name` VARCHAR(255) NOT NULL,
  `email` VARCHAR(255) NOT NULL,
  `phone` VARCHAR(64) NULL,
  `profile_photo` VARCHAR(255) NULL,
  `department_id` INT NULL,
  `section_id` INT NULL,
  `course_id` INT NULL,
  `course_name` VARCHAR(255) NULL,
  `batch_id` INT NULL,
  `batch_name` VARCHAR(128) NULL,
  `academic_year` VARCHAR(64) NOT NULL,
  `semester` INT DEFAULT 1,
  `admission_date` DATE NULL,
  `enrollment_date` DATE NULL,
  `enrollment_status` ENUM('Active', 'Inactive', 'Graduated', 'Suspended') DEFAULT 'Active',
  `gender` VARCHAR(32) NULL,
  `age` INT NULL,
  `total_fee` DECIMAL(12,2) DEFAULT 0.00,
  `password_hash` VARCHAR(255) NULL,
  `logins` INT DEFAULT 0,
  `content_reads` INT DEFAULT 0,
  `forum_posts` INT DEFAULT 0,
  `quiz_reviews` INT DEFAULT 0,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_student_uni_code` (`university_id`, `student_id`),
  KEY `idx_student_uni` (`university_id`),
  KEY `idx_student_dept` (`department_id`),
  KEY `idx_student_sec` (`section_id`),
  KEY `idx_student_course` (`course_id`),
  KEY `idx_student_batch` (`batch_id`),
  CONSTRAINT `fk_student_uni` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_student_dept` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_student_sec` FOREIGN KEY (`section_id`) REFERENCES `sections` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_student_course` FOREIGN KEY (`course_id`) REFERENCES `courses` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_student_batch` FOREIGN KEY (`batch_id`) REFERENCES `batches` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 9. FACE ENCODINGS TABLE (AI FACIAL RECOGNITION BIOMETRICS)
DROP TABLE IF EXISTS `face_encodings`;
CREATE TABLE `face_encodings` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NOT NULL,
  `student_id` INT NOT NULL,
  `student_code` VARCHAR(64) NOT NULL,
  `encoding_vector` JSON NOT NULL,
  `photo_path` VARCHAR(255) NULL,
  `registered_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_face_uni_student` (`university_id`, `student_id`),
  CONSTRAINT `fk_face_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_face_uni` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 10. SUBJECTS TABLE
DROP TABLE IF EXISTS `subjects`;
CREATE TABLE `subjects` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NOT NULL,
  `department_id` INT NULL,
  `code` VARCHAR(64) NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `credits` INT DEFAULT 3,
  `semester` INT DEFAULT 1,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_subject_uni_code` (`university_id`, `code`),
  CONSTRAINT `fk_subject_uni` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_subject_dept` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 11. EXAMINATIONS TABLE
DROP TABLE IF EXISTS `examinations`;
CREATE TABLE `examinations` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `exam_type` VARCHAR(64) NOT NULL,
  `academic_year` VARCHAR(64) NOT NULL,
  `semester` INT DEFAULT 1,
  `exam_date` DATE NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `fk_exam_uni` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 12. MARKS TABLE
DROP TABLE IF EXISTS `marks`;
CREATE TABLE `marks` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NOT NULL,
  `student_id` INT NOT NULL,
  `subject_id` INT NOT NULL,
  `examination_id` INT NOT NULL,
  `internal_marks` DECIMAL(5,2) DEFAULT 0.00,
  `external_marks` DECIMAL(5,2) DEFAULT 0.00,
  `total_marks` DECIMAL(5,2) NOT NULL,
  `max_marks` DECIMAL(5,2) NOT NULL DEFAULT 100.00,
  `pass_marks` DECIMAL(5,2) NOT NULL DEFAULT 40.00,
  `percentage` DECIMAL(5,2) NOT NULL,
  `grade` VARCHAR(8) NULL,
  `is_pass` TINYINT(1) NOT NULL DEFAULT 1,
  `entered_by` INT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_marks_uni_st_sub_ex` (`university_id`, `student_id`, `subject_id`, `examination_id`),
  CONSTRAINT `fk_marks_uni` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_marks_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_marks_subject` FOREIGN KEY (`subject_id`) REFERENCES `subjects` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_marks_exam` FOREIGN KEY (`examination_id`) REFERENCES `examinations` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 13. ATTENDANCE TABLE
DROP TABLE IF EXISTS `attendance`;
CREATE TABLE `attendance` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NOT NULL,
  `student_id` INT NOT NULL,
  `department_id` INT NULL,
  `section_id` INT NULL,
  `date` DATE NOT NULL,
  `status` ENUM('Present', 'Absent', 'Leave') NOT NULL,
  `marked_by` INT NULL,
  `correction_reason` TEXT NULL,
  `method` VARCHAR(64) DEFAULT 'manual', -- 'face_recognition', 'manual', 'rfid'
  `timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `marked_time` VARCHAR(32) NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_att_uni_student_date` (`university_id`, `student_id`, `date`),
  KEY `idx_att_date` (`date`),
  CONSTRAINT `fk_att_uni` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_att_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 14. ATTENDANCE AUDITS TABLE
DROP TABLE IF EXISTS `attendance_audits`;
CREATE TABLE `attendance_audits` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `attendance_id` INT NOT NULL,
  `university_id` VARCHAR(64) NOT NULL,
  `old_status` VARCHAR(32) NOT NULL,
  `new_status` VARCHAR(32) NOT NULL,
  `changed_by` INT NULL,
  `reason` TEXT NOT NULL,
  `timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `fk_att_audit_att` FOREIGN KEY (`attendance_id`) REFERENCES `attendance` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_att_audit_uni` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 15. ASSIGNMENTS TABLE
DROP TABLE IF EXISTS `assignments`;
CREATE TABLE `assignments` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NOT NULL,
  `department_id` INT NULL,
  `subject_id` INT NULL,
  `course_id` INT NULL,
  `batch_id` INT NULL,
  `academic_year` VARCHAR(64) NOT NULL,
  `title` VARCHAR(255) NOT NULL,
  `description` TEXT NULL,
  `file_path` VARCHAR(255) NULL,
  `file_name` VARCHAR(255) NULL,
  `due_date` DATE NOT NULL,
  `max_points` DECIMAL(5,2) DEFAULT 100.00,
  `created_by` INT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_asgn_uni` (`university_id`),
  KEY `idx_asgn_course` (`course_id`),
  KEY `idx_asgn_batch` (`batch_id`),
  CONSTRAINT `fk_asgn_uni` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_asgn_dept` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_asgn_sub` FOREIGN KEY (`subject_id`) REFERENCES `subjects` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 16. ASSIGNMENT SUBMISSIONS & MARKS TABLE
DROP TABLE IF EXISTS `assignment_submissions`;
CREATE TABLE `assignment_submissions` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NOT NULL,
  `assignment_id` INT NOT NULL,
  `student_id` INT NOT NULL,
  `status` ENUM('Completed', 'Pending', 'Missing', 'Late', 'Submitted') NOT NULL DEFAULT 'Submitted',
  `file_path` VARCHAR(255) NULL,
  `file_name` VARCHAR(255) NULL,
  `file_size` INT NULL,
  `submitted_at` TIMESTAMP NULL,
  `score` DECIMAL(5,2) NULL,
  `marks_awarded` DECIMAL(5,2) NULL,
  `feedback` TEXT NULL,
  `evaluated_by` INT NULL,
  `evaluated_at` TIMESTAMP NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_asgn_sub_uni_asgn_st` (`university_id`, `assignment_id`, `student_id`),
  CONSTRAINT `fk_sub_uni` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_sub_asgn` FOREIGN KEY (`assignment_id`) REFERENCES `assignments` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_sub_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 17. FEE RECORDS TABLE
DROP TABLE IF EXISTS `fee_records`;
CREATE TABLE `fee_records` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NOT NULL,
  `student_id` INT NOT NULL,
  `academic_year` VARCHAR(64) NOT NULL,
  `total_fee` DECIMAL(12,2) NOT NULL,
  `paid_amount` DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  `pending_amount` DECIMAL(12,2) NOT NULL,
  `due_date` DATE NULL,
  `payment_status` ENUM('Paid', 'Partial', 'Pending') NOT NULL DEFAULT 'Pending',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_fees_uni_st_ay` (`university_id`, `student_id`, `academic_year`),
  KEY `idx_fees_uni` (`university_id`),
  CONSTRAINT `fk_fees_uni` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_fees_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 18. FEE PAYMENTS & RECEIPTS TABLE
DROP TABLE IF EXISTS `fee_payments`;
CREATE TABLE `fee_payments` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NOT NULL,
  `fee_record_id` INT NOT NULL,
  `amount` DECIMAL(12,2) NOT NULL,
  `payment_date` DATE NOT NULL,
  `payment_method` VARCHAR(64) NOT NULL,
  `receipt_reference` VARCHAR(128) NOT NULL,
  `transaction_id` VARCHAR(128) NULL,
  `notes` TEXT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_fee_pay_receipt` (`receipt_reference`),
  KEY `idx_fee_pay_rec` (`fee_record_id`),
  CONSTRAINT `fk_pay_uni` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_pay_record` FOREIGN KEY (`fee_record_id`) REFERENCES `fee_records` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 19. AUDIT LOGS TABLE
DROP TABLE IF EXISTS `audit_logs`;
CREATE TABLE `audit_logs` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `university_id` VARCHAR(64) NULL,
  `user_id` INT NULL,
  `action` VARCHAR(128) NOT NULL,
  `details` TEXT NULL,
  `ip_address` VARCHAR(64) NULL,
  `timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_audit_uni` (`university_id`),
  KEY `idx_audit_action` (`action`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
