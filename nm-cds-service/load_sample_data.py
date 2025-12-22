"""
Load sample FHIR data for SMART App testing
Run: python load_sample_data.py
"""
import requests
import json
from datetime import datetime, timedelta

FHIR_BASE_URL = "http://localhost:8080/fhir"


def create_resource(resource_type, data):
    """Create a FHIR resource"""
    url = f"{FHIR_BASE_URL}/{resource_type}"
    headers = {"Content-Type": "application/fhir+json"}
    response = requests.post(url, json=data, headers=headers)
    if response.status_code in [200, 201]:
        result = response.json()
        print(f"[OK] Created {resource_type}/{result.get('id')}")
        return result
    else:
        print(f"[FAIL] {resource_type}: {response.status_code} - {response.text[:200]}")
        return None


def load_practitioners():
    """Create Practitioner resources"""
    print("\n--- Creating Practitioners ---")
    
    practitioners = [
        {
            "resourceType": "Practitioner",
            "active": True,
            "name": [{"use": "official", "family": "Wang", "given": ["David"], "prefix": ["Dr."]}],
            "gender": "male",
            "telecom": [{"system": "phone", "value": "02-12345678", "use": "work"}],
            "qualification": [{
                "code": {
                    "coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0360", "code": "MD", "display": "Doctor of Medicine"}]
                }
            }]
        },
        {
            "resourceType": "Practitioner",
            "active": True,
            "name": [{"use": "official", "family": "Lee", "given": ["Sarah"], "prefix": ["Dr."]}],
            "gender": "female",
            "telecom": [{"system": "phone", "value": "02-87654321", "use": "work"}]
        }
    ]
    
    created = []
    for p in practitioners:
        result = create_resource("Practitioner", p)
        if result:
            created.append(result)
    return created


def load_patients():
    """Create Patient resources"""
    print("\n--- Creating Patients ---")
    
    patients = [
        {
            "resourceType": "Patient",
            "active": True,
            "name": [{"use": "official", "family": "Chen", "given": ["Michael"], "text": "Michael Chen"}],
            "gender": "male",
            "birthDate": "1985-03-15",
            "telecom": [{"system": "phone", "value": "0912-345-678", "use": "mobile"}],
            "address": [{"use": "home", "text": "123 Main Street, Taipei", "city": "Taipei", "country": "TW"}]
        },
        {
            "resourceType": "Patient",
            "active": True,
            "name": [{"use": "official", "family": "Lin", "given": ["Emily"], "text": "Emily Lin"}],
            "gender": "female",
            "birthDate": "1990-07-22",
            "telecom": [{"system": "phone", "value": "0923-456-789", "use": "mobile"}],
            "address": [{"use": "home", "text": "456 Oak Avenue, New Taipei", "city": "New Taipei", "country": "TW"}]
        },
        {
            "resourceType": "Patient",
            "active": True,
            "name": [{"use": "official", "family": "Zhang", "given": ["William"], "text": "William Zhang"}],
            "gender": "male",
            "birthDate": "1978-11-08",
            "telecom": [{"system": "email", "value": "william.zhang@example.com"}]
        }
    ]
    
    created = []
    for p in patients:
        result = create_resource("Patient", p)
        if result:
            created.append(result)
    return created


def load_encounters(patient_ids):
    """Create Encounter resources for each patient"""
    print("\n--- Creating Encounters ---")
    
    created = []
    for pid in patient_ids:
        encounter = {
            "resourceType": "Encounter",
            "status": "finished",
            "class": {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": "AMB",
                "display": "ambulatory"
            },
            "type": [{
                "coding": [{
                    "system": "http://snomed.info/sct",
                    "code": "308335008",
                    "display": "Patient encounter procedure"
                }],
                "text": "Outpatient visit"
            }],
            "subject": {"reference": f"Patient/{pid}"},
            "period": {
                "start": "2024-12-19T09:00:00+08:00",
                "end": "2024-12-19T10:00:00+08:00"
            }
        }
        result = create_resource("Encounter", encounter)
        if result:
            created.append(result)
    return created


def load_observations(patient_ids):
    """Create Observation resources"""
    print("\n--- Creating Observations ---")
    
    observations_data = [
        # Vital Signs
        {
            "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6", "display": "Systolic blood pressure"}], "text": "Systolic Blood Pressure"},
            "value": {"value": 120, "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"},
            "category_code": "vital-signs"
        },
        {
            "code": {"coding": [{"system": "http://loinc.org", "code": "8462-4", "display": "Diastolic blood pressure"}], "text": "Diastolic Blood Pressure"},
            "value": {"value": 80, "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"},
            "category_code": "vital-signs"
        },
        {
            "code": {"coding": [{"system": "http://loinc.org", "code": "8310-5", "display": "Body temperature"}], "text": "Body Temperature"},
            "value": {"value": 36.5, "unit": "Cel", "system": "http://unitsofmeasure.org", "code": "Cel"},
            "category_code": "vital-signs"
        },
        {
            "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4", "display": "Heart rate"}], "text": "Heart Rate"},
            "value": {"value": 72, "unit": "/min", "system": "http://unitsofmeasure.org", "code": "/min"},
            "category_code": "vital-signs"
        },
        {
            "code": {"coding": [{"system": "http://loinc.org", "code": "39156-5", "display": "Body mass index (BMI)"}], "text": "BMI"},
            "value": {"value": 22.5, "unit": "kg/m2", "system": "http://unitsofmeasure.org", "code": "kg/m2"},
            "category_code": "vital-signs"
        },
        # Laboratory
        {
            "code": {"coding": [{"system": "http://loinc.org", "code": "2339-0", "display": "Glucose [Mass/volume] in Blood"}], "text": "Blood Glucose"},
            "value": {"value": 95, "unit": "mg/dL", "system": "http://unitsofmeasure.org", "code": "mg/dL"},
            "category_code": "laboratory"
        },
        {
            "code": {"coding": [{"system": "http://loinc.org", "code": "2093-3", "display": "Cholesterol [Mass/volume] in Serum or Plasma"}], "text": "Total Cholesterol"},
            "value": {"value": 180, "unit": "mg/dL", "system": "http://unitsofmeasure.org", "code": "mg/dL"},
            "category_code": "laboratory"
        },
    ]
    
    created = []
    for i, pid in enumerate(patient_ids):
        # Each patient gets different observations
        obs_subset = observations_data[i * 2: i * 2 + 3] if i < len(patient_ids) else observations_data[:2]
        if not obs_subset:
            obs_subset = observations_data[:2]
            
        for obs_data in obs_subset:
            observation = {
                "resourceType": "Observation",
                "status": "final",
                "category": [{
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": obs_data["category_code"],
                        "display": obs_data["category_code"].replace("-", " ").title()
                    }]
                }],
                "code": obs_data["code"],
                "subject": {"reference": f"Patient/{pid}"},
                "effectiveDateTime": datetime.now().isoformat(),
                "valueQuantity": obs_data["value"]
            }
            result = create_resource("Observation", observation)
            if result:
                created.append(result)
    
    return created


def load_pediatric_patients():
    """建立兒科病人（用於核醫檢查測試）"""
    print("\n--- Creating Pediatric Patients for NM CDS Testing ---")
    
    # 計算生日（確保是兒科病人）
    today = datetime.now()
    pediatric_patients = [
        {
            "resourceType": "Patient",
            "active": True,
            "name": [{"use": "official", "family": "Wu", "given": ["Alex"], "text": "Alex Wu"}],
            "gender": "male",
            "birthDate": (today - timedelta(days=365*8)).strftime("%Y-%m-%d"),  # 8歲
            "telecom": [{"system": "phone", "value": "0911-111-111", "use": "mobile"}],
            "address": [{"use": "home", "text": "789 Pediatric St, Taipei", "city": "Taipei", "country": "TW"}]
        },
        {
            "resourceType": "Patient",
            "active": True,
            "name": [{"use": "official", "family": "Huang", "given": ["Sophie"], "text": "Sophie Huang"}],
            "gender": "female",
            "birthDate": (today - timedelta(days=365*5)).strftime("%Y-%m-%d"),  # 5歲
            "telecom": [{"system": "phone", "value": "0912-222-222", "use": "mobile"}],
            "address": [{"use": "home", "text": "321 Child Ave, New Taipei", "city": "New Taipei", "country": "TW"}]
        },
        {
            "resourceType": "Patient",
            "active": True,
            "name": [{"use": "official", "family": "Liu", "given": ["Ryan"], "text": "Ryan Liu"}],
            "gender": "male",
            "birthDate": (today - timedelta(days=365*12)).strftime("%Y-%m-%d"),  # 12歲
            "telecom": [{"system": "phone", "value": "0913-333-333", "use": "mobile"}],
            "address": [{"use": "home", "text": "654 Youth Rd, Taipei", "city": "Taipei", "country": "TW"}]
        }
    ]
    
    created = []
    for p in pediatric_patients:
        result = create_resource("Patient", p)
        if result:
            created.append(result)
    return created


def load_weight_observations(patient_ids, include_stale=False):
    """建立體重 Observation（LOINC 29463-7）"""
    print("\n--- Creating Weight Observations (LOINC 29463-7) ---")
    
    # 體重資料（根據年齡合理）
    weight_data = [
        {"value": 25.0, "days_ago": 0},      # 8歲，25kg，今天
        {"value": 18.0, "days_ago": 0},      # 5歲，18kg，今天
        {"value": 40.0, "days_ago": 0},      # 12歲，40kg，今天
    ]
    
    # 如果需要，加入過舊的體重資料
    if include_stale:
        weight_data.extend([
            {"value": 24.5, "days_ago": 120},  # 過舊（>90天）
            {"value": 17.8, "days_ago": 100},  # 過舊（>90天）
        ])
    
    created = []
    for i, pid in enumerate(patient_ids):
        if i < len(weight_data):
            wd = weight_data[i]
            effective_date = (datetime.now() - timedelta(days=wd["days_ago"])).isoformat()
            
            observation = {
                "resourceType": "Observation",
                "status": "final",
                "category": [{
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "vital-signs",
                        "display": "Vital Signs"
                    }]
                }],
                "code": {
                    "coding": [{
                        "system": "http://loinc.org",
                        "code": "29463-7",
                        "display": "Body weight"
                    }],
                    "text": "Body weight"
                },
                "subject": {"reference": f"Patient/{pid}"},
                "effectiveDateTime": effective_date,
                "valueQuantity": {
                    "value": wd["value"],
                    "unit": "kg",
                    "system": "http://unitsofmeasure.org",
                    "code": "kg"
                }
            }
            result = create_resource("Observation", observation)
            if result:
                created.append(result)
    
    return created


def load_service_requests(patient_ids, practitioner_ids=None):
    """建立核醫檢查 ServiceRequest"""
    print("\n--- Creating Nuclear Medicine ServiceRequests ---")
    
    # 檢查類型對應
    study_codes = [
        {"code": "BONE_SCAN", "display": "Bone Scan (99mTc-MDP)"},
        {"code": "MAG3", "display": "Renal Scan (99mTc-MAG3)"},
        {"code": "DMSA", "display": "Renal Cortical Scan (99mTc-DMSA)"},
        {"code": "MIBG", "display": "MIBG Scan (123I-MIBG)"},
        {"code": "FDG_PET", "display": "FDG PET Scan (18F-FDG)"},
    ]
    
    # 使用第一個 Practitioner 作為 requester，如果沒有則不指定
    requester_ref = None
    if practitioner_ids and len(practitioner_ids) > 0:
        requester_ref = f"Practitioner/{practitioner_ids[0]}"
    
    created = []
    for i, pid in enumerate(patient_ids):
        # 每個病人分配不同的檢查
        study_idx = i % len(study_codes)
        study = study_codes[study_idx]
        
        service_request = {
            "resourceType": "ServiceRequest",
            "status": "active",
            "intent": "order",
            "code": {
                "coding": [{
                    "code": study["code"],
                    "display": study["display"],
                    "system": "http://example.org/nuclear-medicine"
                }],
                "text": study["display"]
            },
            "subject": {"reference": f"Patient/{pid}"},
            "authoredOn": datetime.now().isoformat()
        }
        
        # 只有在有 Practitioner 時才添加 requester
        if requester_ref:
            service_request["requester"] = {"reference": requester_ref}
        
        result = create_resource("ServiceRequest", service_request)
        if result:
            created.append(result)
    
    return created


def main():
    print("=" * 60)
    print("Loading Sample FHIR Data for SMART App Testing")
    print(f"FHIR Server: {FHIR_BASE_URL}")
    print("=" * 60)
    
    # Check server connectivity
    try:
        response = requests.get(f"{FHIR_BASE_URL}/metadata", timeout=10)
        if response.status_code != 200:
            print(f"[ERROR] Cannot connect to FHIR server: {response.status_code}")
            return
        print("[OK] Connected to FHIR server")
    except Exception as e:
        print(f"[ERROR] Cannot connect to FHIR server: {e}")
        print("Make sure Docker containers are running: docker compose up -d")
        return
    
    # Load data
    practitioners = load_practitioners()
    practitioner_ids = [p.get("id") for p in practitioners if p]
    patients = load_patients()
    
    patient_ids = [p.get("id") for p in patients if p]
    
    if patient_ids:
        encounters = load_encounters(patient_ids)
        observations = load_observations(patient_ids)
    
    # Load nuclear medicine test data
    pediatric_patients = load_pediatric_patients()
    pediatric_patient_ids = [p.get("id") for p in pediatric_patients if p]
    
    if pediatric_patient_ids:
        weight_observations = load_weight_observations(pediatric_patient_ids, include_stale=True)
        service_requests = load_service_requests(pediatric_patient_ids, practitioner_ids)
    
    # Summary
    print("\n" + "=" * 60)
    print("Sample Data Loaded Successfully!")
    print("=" * 60)
    print(f"\nCreated Resources:")
    print(f"  - Practitioners: {len(practitioners)}")
    print(f"  - Patients: {len(patients)}")
    print(f"  - Pediatric Patients (NM): {len(pediatric_patients)}")
    print(f"  - Encounters: {len(patient_ids)}")
    print(f"  - Observations: {len(patient_ids) * 2 + 1}")
    print(f"  - Weight Observations (NM): {len(weight_observations) if pediatric_patient_ids else 0}")
    print(f"  - ServiceRequests (NM): {len(service_requests) if pediatric_patient_ids else 0}")
    
    print(f"\nPatient IDs for testing:")
    for p in patients:
        if p:
            name = p.get("name", [{}])[0].get("text", "Unknown")
            print(f"  - Patient/{p.get('id')}: {name}")
    
    if pediatric_patients:
        print(f"\nPediatric Patient IDs for NM CDS testing:")
        for p in pediatric_patients:
            if p:
                name = p.get("name", [{}])[0].get("text", "Unknown")
                birth_date = p.get("birthDate", "Unknown")
                print(f"  - Patient/{p.get('id')}: {name} (Birth: {birth_date})")
    
    print(f"\nView data at:")
    print(f"  - Patients: {FHIR_BASE_URL}/Patient")
    print(f"  - Practitioners: {FHIR_BASE_URL}/Practitioner")
    print(f"  - Observations: {FHIR_BASE_URL}/Observation")
    print(f"  - Encounters: {FHIR_BASE_URL}/Encounter")
    print(f"  - ServiceRequests: {FHIR_BASE_URL}/ServiceRequest")
    
    print(f"\nTo test your SMART Apps:")
    print(f"  1. Open http://localhost:4000 (SMART Launcher)")
    print(f"  2. Select R4, choose a Patient")
    print(f"  3. Flask App Launch URL: http://localhost:5000/launch")
    print(f"  4. NM CDS App Launch URL: http://localhost:8000/launch")
    print(f"  5. Click Launch")


if __name__ == "__main__":
    main()


