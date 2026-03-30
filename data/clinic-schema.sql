-- Clinical Intelligence Demo Database
-- Schema for a small medical clinic

CREATE TABLE doctors (
    doctor_id SERIAL PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    specialty VARCHAR(100) NOT NULL,
    license_number VARCHAR(50) NOT NULL,
    email VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE patients (
    patient_id SERIAL PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    date_of_birth DATE NOT NULL,
    gender VARCHAR(20),
    email VARCHAR(200),
    phone VARCHAR(20),
    allergies TEXT[] DEFAULT '{}',
    conditions TEXT[] DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE prescriptions (
    prescription_id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(patient_id),
    doctor_id INTEGER NOT NULL REFERENCES doctors(doctor_id),
    drug_ndc VARCHAR(20) NOT NULL,
    drug_name VARCHAR(200) NOT NULL,
    dosage VARCHAR(100) NOT NULL,
    frequency VARCHAR(100) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'discontinued')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE visits (
    visit_id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(patient_id),
    doctor_id INTEGER NOT NULL REFERENCES doctors(doctor_id),
    visit_date DATE NOT NULL,
    reason VARCHAR(500),
    notes TEXT,
    diagnosis VARCHAR(500),
    follow_up_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE outcomes (
    outcome_id SERIAL PRIMARY KEY,
    prescription_id INTEGER NOT NULL REFERENCES prescriptions(prescription_id),
    patient_id INTEGER NOT NULL REFERENCES patients(patient_id),
    observation_date DATE NOT NULL,
    metric VARCHAR(100) NOT NULL,
    value VARCHAR(100) NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pharmacy_inventory (
    inventory_id SERIAL PRIMARY KEY,
    drug_ndc VARCHAR(20) NOT NULL,
    drug_name VARCHAR(200) NOT NULL,
    quantity_on_hand INTEGER NOT NULL DEFAULT 0,
    reorder_level INTEGER NOT NULL DEFAULT 10,
    last_restocked DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Local drug interaction table (curated by clinic, supplements FDA label text)
CREATE TABLE drug_interactions (
    interaction_id SERIAL PRIMARY KEY,
    drug_a_ndc VARCHAR(20) NOT NULL,
    drug_a_name VARCHAR(200) NOT NULL,
    drug_b_ndc VARCHAR(20) NOT NULL,
    drug_b_name VARCHAR(200) NOT NULL,
    severity VARCHAR(20) NOT NULL
        CHECK (severity IN ('mild', 'moderate', 'severe')),
    description TEXT NOT NULL,
    clinical_recommendation TEXT,
    source VARCHAR(100) DEFAULT 'clinic_formulary'
);

-- Indexes for common queries
CREATE INDEX idx_prescriptions_patient ON prescriptions(patient_id);
CREATE INDEX idx_prescriptions_doctor ON prescriptions(doctor_id);
CREATE INDEX idx_prescriptions_ndc ON prescriptions(drug_ndc);
CREATE INDEX idx_prescriptions_status ON prescriptions(status);
CREATE INDEX idx_visits_patient ON visits(patient_id);
CREATE INDEX idx_visits_doctor ON visits(doctor_id);
CREATE INDEX idx_outcomes_patient ON outcomes(patient_id);
CREATE INDEX idx_outcomes_prescription ON outcomes(prescription_id);
CREATE INDEX idx_pharmacy_ndc ON pharmacy_inventory(drug_ndc);
CREATE INDEX idx_interactions_drug_a ON drug_interactions(drug_a_ndc);
CREATE INDEX idx_interactions_drug_b ON drug_interactions(drug_b_ndc);
