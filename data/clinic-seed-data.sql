-- Seed data for Clinical Intelligence Demo
-- Uses real NDC codes that exist in the FDA database

-- Doctors
INSERT INTO doctors (first_name, last_name, specialty, license_number, email) VALUES
('Sarah', 'Chen', 'Internal Medicine', 'MD-2019-04521', 'schen@clinic.local'),
('James', 'Rodriguez', 'Cardiology', 'MD-2015-03187', 'jrodriguez@clinic.local'),
('Emily', 'Patel', 'Endocrinology', 'MD-2017-05893', 'epatel@clinic.local'),
('Michael', 'Thompson', 'Family Medicine', 'MD-2020-06234', 'mthompson@clinic.local');

-- Patients (varied conditions and allergies to create interesting interaction scenarios)
INSERT INTO patients (first_name, last_name, date_of_birth, gender, email, phone, allergies, conditions) VALUES
('Jane', 'Doe', '1958-03-15', 'Female', 'jdoe@email.com', '555-0101', '{penicillin}', '{diabetes_type2,hypertension}'),
('Robert', 'Smith', '1965-07-22', 'Male', 'rsmith@email.com', '555-0102', '{}', '{hypertension,high_cholesterol}'),
('Maria', 'Garcia', '1972-11-08', 'Female', 'mgarcia@email.com', '555-0103', '{sulfa}', '{diabetes_type2,hypothyroidism}'),
('William', 'Johnson', '1950-01-30', 'Male', 'wjohnson@email.com', '555-0104', '{aspirin,ibuprofen}', '{hypertension,gerd,atrial_fibrillation}'),
('Lisa', 'Williams', '1980-06-12', 'Female', 'lwilliams@email.com', '555-0105', '{}', '{high_cholesterol,hypertension}'),
('David', 'Brown', '1945-09-03', 'Male', 'dbrown@email.com', '555-0106', '{codeine}', '{diabetes_type2,hypertension,high_cholesterol}'),
('Susan', 'Davis', '1968-12-25', 'Female', 'sdavis@email.com', '555-0107', '{latex}', '{hypothyroidism,gerd}'),
('Thomas', 'Wilson', '1955-04-18', 'Male', 'twilson@email.com', '555-0108', '{}', '{diabetes_type2,hypertension,gerd}'),
('Jennifer', 'Martinez', '1978-08-07', 'Female', 'jmartinez@email.com', '555-0109', '{penicillin,sulfa}', '{hypertension}'),
('Charles', 'Anderson', '1962-02-14', 'Male', 'canderson@email.com', '555-0110', '{}', '{diabetes_type2,high_cholesterol,hypertension}'),
('Patricia', 'Taylor', '1970-10-20', 'Female', 'ptaylor@email.com', '555-0111', '{}', '{hypothyroidism}'),
('Richard', 'Thomas', '1948-05-11', 'Male', 'rthomas@email.com', '555-0112', '{aspirin}', '{diabetes_type2,hypertension,atrial_fibrillation}');

-- Prescriptions using real NDC codes
-- Metformin NDC: 11788-037, Lisinopril: 68001-335, Atorvastatin: 70771-1446
-- Omeprazole: 85509-1396, Amlodipine: 68071-4251, Levothyroxine: 0378-1805

-- Patient 1 (Jane Doe): diabetes + hypertension
INSERT INTO prescriptions (patient_id, doctor_id, drug_ndc, drug_name, dosage, frequency, start_date, status) VALUES
(1, 3, '11788-037', 'Metformin', '500mg', 'twice daily', '2025-03-01', 'active'),
(1, 2, '68001-335', 'Lisinopril', '10mg', 'once daily', '2025-06-15', 'active');

-- Patient 2 (Robert Smith): hypertension + cholesterol
INSERT INTO prescriptions (patient_id, doctor_id, drug_ndc, drug_name, dosage, frequency, start_date, status) VALUES
(2, 2, '68071-4251', 'Amlodipine', '5mg', 'once daily', '2024-11-01', 'active'),
(2, 1, '70771-1446', 'Atorvastatin', '80mg', 'once daily at bedtime', '2024-11-01', 'active');

-- Patient 3 (Maria Garcia): diabetes + hypothyroidism
INSERT INTO prescriptions (patient_id, doctor_id, drug_ndc, drug_name, dosage, frequency, start_date, status) VALUES
(3, 3, '11788-037', 'Metformin', '1000mg', 'twice daily', '2024-06-01', 'active'),
(3, 3, '0378-1805', 'Levothyroxine', '75mcg', 'once daily before breakfast', '2024-08-15', 'active');

-- Patient 4 (William Johnson): hypertension + GERD + atrial fibrillation (complex case)
INSERT INTO prescriptions (patient_id, doctor_id, drug_ndc, drug_name, dosage, frequency, start_date, status) VALUES
(4, 2, '68001-335', 'Lisinopril', '20mg', 'once daily', '2024-01-15', 'active'),
(4, 1, '85509-1396', 'Omeprazole', '20mg', 'once daily before breakfast', '2024-03-01', 'active'),
(4, 2, '68071-4251', 'Amlodipine', '10mg', 'once daily', '2024-06-01', 'active');

-- Patient 5 (Lisa Williams): cholesterol + hypertension
INSERT INTO prescriptions (patient_id, doctor_id, drug_ndc, drug_name, dosage, frequency, start_date, status) VALUES
(5, 1, '70771-1446', 'Atorvastatin', '40mg', 'once daily at bedtime', '2025-01-10', 'active'),
(5, 2, '68071-4251', 'Amlodipine', '5mg', 'once daily', '2025-01-10', 'active');

-- Patient 6 (David Brown): diabetes + hypertension + cholesterol (most meds)
INSERT INTO prescriptions (patient_id, doctor_id, drug_ndc, drug_name, dosage, frequency, start_date, status) VALUES
(6, 3, '11788-037', 'Metformin', '850mg', 'twice daily', '2023-09-01', 'active'),
(6, 2, '68001-335', 'Lisinopril', '10mg', 'once daily', '2023-09-01', 'active'),
(6, 1, '70771-1446', 'Atorvastatin', '40mg', 'once daily at bedtime', '2023-12-01', 'active');

-- Patient 7 (Susan Davis): hypothyroidism + GERD
INSERT INTO prescriptions (patient_id, doctor_id, drug_ndc, drug_name, dosage, frequency, start_date, status) VALUES
(7, 3, '0378-1805', 'Levothyroxine', '50mcg', 'once daily before breakfast', '2024-05-01', 'active'),
(7, 1, '85509-1396', 'Omeprazole', '20mg', 'once daily', '2024-07-15', 'active');

-- Patient 8 (Thomas Wilson): diabetes + hypertension + GERD
INSERT INTO prescriptions (patient_id, doctor_id, drug_ndc, drug_name, dosage, frequency, start_date, status) VALUES
(8, 3, '11788-037', 'Metformin', '1000mg', 'twice daily', '2024-02-01', 'active'),
(8, 2, '68001-335', 'Lisinopril', '10mg', 'once daily', '2024-04-01', 'active'),
(8, 1, '85509-1396', 'Omeprazole', '20mg', 'once daily', '2024-06-01', 'active');

-- Patient 9 (Jennifer Martinez): hypertension only
INSERT INTO prescriptions (patient_id, doctor_id, drug_ndc, drug_name, dosage, frequency, start_date, status) VALUES
(9, 4, '68071-4251', 'Amlodipine', '5mg', 'once daily', '2025-02-01', 'active');

-- Patient 10 (Charles Anderson): diabetes + cholesterol + hypertension
INSERT INTO prescriptions (patient_id, doctor_id, drug_ndc, drug_name, dosage, frequency, start_date, status) VALUES
(10, 3, '11788-037', 'Metformin', '500mg', 'twice daily', '2025-01-01', 'active'),
(10, 1, '70771-1446', 'Atorvastatin', '20mg', 'once daily at bedtime', '2025-01-01', 'active'),
(10, 2, '68001-335', 'Lisinopril', '5mg', 'once daily', '2025-02-15', 'active');

-- Patient 11 (Patricia Taylor): hypothyroidism only
INSERT INTO prescriptions (patient_id, doctor_id, drug_ndc, drug_name, dosage, frequency, start_date, status) VALUES
(11, 3, '0378-1805', 'Levothyroxine', '100mcg', 'once daily before breakfast', '2024-01-01', 'active');

-- Patient 12 (Richard Thomas): diabetes + hypertension + atrial fibrillation
INSERT INTO prescriptions (patient_id, doctor_id, drug_ndc, drug_name, dosage, frequency, start_date, status) VALUES
(12, 3, '11788-037', 'Metformin', '750mg', 'twice daily', '2024-03-01', 'active'),
(12, 2, '68001-335', 'Lisinopril', '20mg', 'once daily', '2024-03-01', 'active'),
(12, 2, '68071-4251', 'Amlodipine', '5mg', 'once daily', '2024-06-01', 'active');

-- Some completed/discontinued prescriptions for history
INSERT INTO prescriptions (patient_id, doctor_id, drug_ndc, drug_name, dosage, frequency, start_date, end_date, status) VALUES
(1, 3, '11788-037', 'Metformin', '250mg', 'once daily', '2024-09-01', '2025-02-28', 'completed'),
(6, 2, '68071-4251', 'Amlodipine', '5mg', 'once daily', '2023-06-01', '2023-08-31', 'discontinued');

-- Visits
INSERT INTO visits (patient_id, doctor_id, visit_date, reason, notes, diagnosis, follow_up_date) VALUES
(1, 3, '2025-03-01', 'Initial diabetes management', 'Patient presents with elevated HbA1c of 8.1%. Started on Metformin.', 'Type 2 Diabetes Mellitus', '2025-06-01'),
(1, 3, '2025-06-01', 'Diabetes follow-up', 'HbA1c improved to 7.2%. Continue current regimen.', 'Type 2 Diabetes Mellitus - improving', '2025-09-01'),
(1, 2, '2025-06-15', 'Hypertension management', 'BP 148/92. Starting Lisinopril.', 'Essential Hypertension', '2025-09-15'),
(2, 2, '2024-11-01', 'Annual cardiovascular review', 'BP 155/95, LDL 185. Starting Amlodipine and Atorvastatin.', 'Hypertension with Hyperlipidemia', '2025-05-01'),
(4, 2, '2024-06-01', 'BP not controlled', 'Adding Amlodipine to existing Lisinopril. Monitor closely.', 'Resistant Hypertension', '2024-09-01'),
(6, 3, '2023-09-01', 'New patient - multiple conditions', 'Complex patient with diabetes, hypertension, and cholesterol. Starting comprehensive management.', 'Type 2 DM, HTN, Hyperlipidemia', '2023-12-01'),
(7, 3, '2024-07-15', 'GERD symptoms with levothyroxine', 'Patient reports acid reflux. Note: omeprazole may reduce levothyroxine absorption. Counsel on timing.', 'GERD - monitor thyroid levels', '2024-10-15'),
(12, 2, '2024-06-01', 'BP still elevated', 'Adding Amlodipine. Patient on Metformin and Lisinopril already. Three drug regimen - monitor closely.', 'HTN not at goal', '2024-09-01');

-- Outcomes (treatment observations)
INSERT INTO outcomes (prescription_id, patient_id, observation_date, metric, value, notes) VALUES
(1, 1, '2025-06-01', 'HbA1c', '7.2', 'Improved from 8.1 at baseline'),
(1, 1, '2025-09-01', 'HbA1c', '6.9', 'Continued improvement'),
(2, 1, '2025-09-15', 'blood_pressure', '132/84', 'Improved from 148/92'),
(3, 2, '2025-05-01', 'blood_pressure', '128/82', 'Well controlled'),
(4, 2, '2025-05-01', 'LDL', '118', 'Down from 185'),
(5, 3, '2024-12-01', 'HbA1c', '7.5', 'Improved from 8.8'),
(5, 3, '2025-03-01', 'HbA1c', '6.8', 'At target'),
(6, 3, '2024-11-15', 'TSH', '3.2', 'Within normal range'),
(6, 3, '2025-02-15', 'TSH', '4.8', 'Slightly elevated - may need dose adjustment'),
(13, 6, '2024-03-01', 'HbA1c', '7.8', 'Improved from 9.2'),
(13, 6, '2024-09-01', 'HbA1c', '7.1', 'Continued improvement'),
(14, 6, '2024-03-01', 'blood_pressure', '138/88', 'Improved but not at goal'),
(14, 6, '2024-09-01', 'blood_pressure', '128/80', 'At goal');

-- Pharmacy inventory
INSERT INTO pharmacy_inventory (drug_ndc, drug_name, quantity_on_hand, reorder_level, last_restocked) VALUES
('11788-037', 'Metformin 500mg', 240, 50, '2025-03-15'),
('68001-335', 'Lisinopril 10mg', 180, 40, '2025-03-10'),
('70771-1446', 'Atorvastatin 80mg', 90, 30, '2025-03-01'),
('85509-1396', 'Omeprazole 20mg', 150, 30, '2025-03-12'),
('68071-4251', 'Amlodipine 5mg', 200, 40, '2025-03-15'),
('0378-1805', 'Levothyroxine 75mcg', 60, 20, '2025-02-28');

-- Drug interactions (curated by clinic pharmacist)
INSERT INTO drug_interactions (drug_a_ndc, drug_a_name, drug_b_ndc, drug_b_name, severity, description, clinical_recommendation) VALUES
('11788-037', 'Metformin', '68001-335', 'Lisinopril', 'mild', 'Lisinopril may enhance the hypoglycemic effect of Metformin. Risk of hypoglycemia slightly increased.', 'Monitor blood glucose more frequently when initiating combination. Generally safe and commonly prescribed together.'),
('0378-1805', 'Levothyroxine', '85509-1396', 'Omeprazole', 'moderate', 'Omeprazole reduces gastric acid, which may decrease levothyroxine absorption. May lead to subtherapeutic thyroid levels.', 'Take levothyroxine at least 30-60 minutes before omeprazole. Monitor TSH levels every 6-8 weeks after starting combination.'),
('70771-1446', 'Atorvastatin', '68071-4251', 'Amlodipine', 'moderate', 'Amlodipine may increase atorvastatin plasma concentrations via CYP3A4 inhibition. Increased risk of myopathy and rhabdomyolysis.', 'Limit atorvastatin dose to 20mg daily when combined with amlodipine. Monitor for muscle pain or weakness.'),
('11788-037', 'Metformin', '85509-1396', 'Omeprazole', 'mild', 'Omeprazole may slightly increase metformin absorption. Clinical significance is generally low.', 'No dose adjustment typically needed. Monitor blood glucose if symptoms occur.'),
('68001-335', 'Lisinopril', '68071-4251', 'Amlodipine', 'mild', 'Additive hypotensive effect. This combination is frequently prescribed intentionally for blood pressure control.', 'Monitor blood pressure regularly. Watch for dizziness or lightheadedness, especially when standing.'),
('11788-037', 'Metformin', '70771-1446', 'Atorvastatin', 'mild', 'Statins may slightly increase blood glucose levels. May partially counteract metformin effect.', 'Monitor HbA1c. Benefits of statin therapy generally outweigh the small glycemic effect.'),
('68001-335', 'Lisinopril', '85509-1396', 'Omeprazole', 'mild', 'Omeprazole may slightly reduce the antihypertensive effect of Lisinopril through magnesium depletion with long-term use.', 'Monitor blood pressure and magnesium levels with long-term concurrent use.');
