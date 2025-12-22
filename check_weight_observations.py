#!/usr/bin/env python3
"""
檢查 FHIR server 上的體重 Observation
"""
import requests
import json
from datetime import datetime

FHIR_BASE = "http://localhost:8080/fhir"

def check_weight_observations(patient_id=None):
    """檢查體重 Observation"""
    print("=" * 60)
    print("檢查體重 Observation (LOINC 29463-7)")
    print("=" * 60)
    
    # 構建查詢 URL
    if patient_id:
        url = f"{FHIR_BASE}/Observation?patient=Patient/{patient_id}&code=http://loinc.org|29463-7&_count=50"
        print(f"\n查詢病人: Patient/{patient_id}")
    else:
        url = f"{FHIR_BASE}/Observation?code=http://loinc.org|29463-7&_count=50"
        print(f"\n查詢所有病人的體重 Observation")
    
    print(f"URL: {url}\n")
    
    try:
        response = requests.get(url, headers={
            "Accept": "application/fhir+json"
        }, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ 錯誤: HTTP {response.status_code}")
            print(f"回應: {response.text[:500]}")
            return
        
        bundle = response.json()
        entries = bundle.get("entry", [])
        
        print(f"找到 {len(entries)} 筆體重 Observation\n")
        
        if not entries:
            print("⚠️  沒有找到任何體重 Observation")
            return
        
        # 顯示所有體重 Observation
        print("-" * 60)
        for i, entry in enumerate(entries, 1):
            obs = entry.get("resource", {})
            obs_id = obs.get("id", "unknown")
            
            # 取得病人 ID
            subject_ref = obs.get("subject", {}).get("reference", "")
            patient_id_from_obs = subject_ref.replace("Patient/", "") if subject_ref.startswith("Patient/") else "unknown"
            
            # 取得體重值
            vq = obs.get("valueQuantity", {})
            weight_value = vq.get("value", "N/A")
            weight_unit = vq.get("unit", "N/A")
            
            # 取得日期
            effective_date = obs.get("effectiveDateTime", obs.get("issued", "N/A"))
            last_updated = obs.get("meta", {}).get("lastUpdated", "N/A")
            
            # 取得狀態
            status = obs.get("status", "N/A")
            
            print(f"[{i}] Observation/{obs_id}")
            print(f"    病人: Patient/{patient_id_from_obs}")
            print(f"    體重: {weight_value} {weight_unit}")
            print(f"    測量日期: {effective_date}")
            print(f"    最後更新: {last_updated}")
            print(f"    狀態: {status}")
            print()
        
        # 按病人分組統計
        print("-" * 60)
        print("按病人分組統計:")
        print("-" * 60)
        
        patient_weights = {}
        for entry in entries:
            obs = entry.get("resource", {})
            subject_ref = obs.get("subject", {}).get("reference", "")
            patient_id_from_obs = subject_ref.replace("Patient/", "") if subject_ref.startswith("Patient/") else "unknown"
            
            if patient_id_from_obs not in patient_weights:
                patient_weights[patient_id_from_obs] = []
            
            vq = obs.get("valueQuantity", {})
            weight_value = vq.get("value")
            effective_date = obs.get("effectiveDateTime", obs.get("issued", ""))
            obs_id = obs.get("id", "unknown")
            
            patient_weights[patient_id_from_obs].append({
                "weight": weight_value,
                "date": effective_date,
                "id": obs_id
            })
        
        for pid, weights in patient_weights.items():
            print(f"\nPatient/{pid}: {len(weights)} 筆體重記錄")
            # 按日期排序（最新的在前）
            weights_sorted = sorted(weights, key=lambda x: x["date"] or "", reverse=True)
            for w in weights_sorted[:5]:  # 只顯示前5筆
                print(f"  - {w['weight']} kg (日期: {w['date']}, ID: {w['id']})")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ 連線錯誤: {e}")
    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
        import traceback
        traceback.print_exc()

def check_specific_patient(patient_id):
    """檢查特定病人的體重"""
    print(f"\n{'=' * 60}")
    print(f"檢查病人 Patient/{patient_id} 的體重")
    print(f"{'=' * 60}\n")
    
    # 先取得病人資訊
    try:
        patient_url = f"{FHIR_BASE}/Patient/{patient_id}"
        response = requests.get(patient_url, headers={"Accept": "application/fhir+json"}, timeout=10)
        if response.status_code == 200:
            patient = response.json()
            name = "未知"
            if patient.get('name') and len(patient['name']) > 0:
                name_obj = patient['name'][0]
                if 'text' in name_obj:
                    name = name_obj['text']
                elif 'family' in name_obj:
                    given = ' '.join(name_obj.get('given', []))
                    name = f"{name_obj['family']} {given}".strip()
            print(f"病人姓名: {name}")
            print(f"病人 ID: {patient.get('id')}")
            print(f"性別: {patient.get('gender', '未知')}")
            print(f"生日: {patient.get('birthDate', '未知')}")
            print()
        else:
            print(f"⚠️  無法取得病人資訊 (HTTP {response.status_code})")
    except Exception as e:
        print(f"⚠️  無法取得病人資訊: {e}")
    
    # 檢查體重
    check_weight_observations(patient_id)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        patient_id = sys.argv[1]
        check_specific_patient(patient_id)
    else:
        print("用法:")
        print("  python check_weight_observations.py              # 檢查所有病人的體重")
        print("  python check_weight_observations.py pat-001      # 檢查特定病人的體重")
        print()
        check_weight_observations()


