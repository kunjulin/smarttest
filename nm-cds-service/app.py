"""
核醫檢查 CDS Service (North American Consensus 2024)
FastAPI 後端服務，支援 SMART on FHIR 授權
"""
import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from dateutil.parser import isoparse
from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

APP_TITLE = "NM Pediatric Dose CDS (NA Consensus 2024)"
RULES_PATH = os.getenv("RULES_PATH", "rules.json")

# 注意：如果使用 SMART Launcher，應該使用 SMART Launcher 的 FHIR 端點
# SMART Launcher 的 FHIR 端點：http://localhost:4000/v/r4/fhir
# 直接 HAPI FHIR 端點：http://localhost:8080/fhir（不支援 SMART on FHIR）
DEFAULT_FHIR_BASE = os.getenv("FHIR_BASE", "http://localhost:4000/v/r4/fhir")
FHIR_TIMEOUT_SEC = float(os.getenv("FHIR_TIMEOUT_SEC", "10"))

WEIGHT_LOOKBACK_DAYS = int(os.getenv("WEIGHT_LOOKBACK_DAYS", "90"))
WEIGHT_STALE_AS_MISSING = os.getenv("WEIGHT_STALE_AS_MISSING", "false").lower() == "true"

# SMART on FHIR 設定
CLIENT_ID = os.getenv("CLIENT_ID", "nm-cds-client")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/callback")
SCOPE = "launch/patient patient/Patient.read patient/Observation.read patient/Observation.write patient/ServiceRequest.read patient/MedicationRequest.write openid fhirUser"

# Session 管理（生產環境應使用 Redis 等）
sessions: Dict[str, Dict[str, Any]] = {}

# FastAPI 應用
app = FastAPI(title=APP_TITLE, docs_url="/docs", redoc_url="/redoc")

# 模板和靜態檔案
templates = Jinja2Templates(directory="templates")
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception:
    logger.warning("Static files directory not found, skipping static mount")

# ----------------------------
# Models
# ----------------------------
class Protocol(BaseModel):
    mag3_with_flow: bool = False
    fdg_region: str = Field(default="body", pattern="^(body|brain)$")
    fdg_strategy: str = Field(default="low", pattern="^(low|mid|high)$")


class RecommendRequest(BaseModel):
    fhirBase: Optional[str] = None
    patientId: str
    serviceRequestId: str
    protocol: Protocol = Protocol()


class Recommendation(BaseModel):
    recommendedMBq: float
    ruleMBqPerKg: Optional[float] = None
    ruleMBqPerKgRange: Optional[Tuple[float, float]] = None
    minMBq: float
    maxMBq: float
    clampReason: str
    rawCalculatedMBq: float


class RecommendResponse(BaseModel):
    status: str
    guideline: str
    ruleSetVersion: str
    studyKey: Optional[str] = None
    studyType: Optional[str] = None
    radiopharmaceutical: Optional[Dict[str, str]] = None
    inputs: Dict[str, Any] = {}
    recommendation: Optional[Recommendation] = None
    warnings: List[str] = []
    missing: List[str] = []
    message: Optional[str] = None


class CreateMedRequest(BaseModel):
    fhirBase: Optional[str] = None
    patientId: str
    serviceRequestId: str
    recommendedMBq: float
    radiopharmCode: str
    radiopharmDisplay: str
    note: str = ""
    overrideReason: Optional[str] = None


# ----------------------------
# Helpers
# ----------------------------
@dataclass
class Rule:
    key: str
    radiopharm: Dict[str, str]
    min_mbq: float
    max_mbq: float
    mbq_per_kg: Optional[float] = None
    mbq_per_kg_range: Optional[Tuple[float, float]] = None


def load_rules() -> Dict[str, Any]:
    """載入規則配置"""
    rules_file = os.path.join(os.path.dirname(__file__), RULES_PATH)
    with open(rules_file, "r", encoding="utf-8") as f:
        return json.load(f)


RULES = load_rules()
RULESET_VERSION = RULES.get("version", "unknown")
logger.info(f"Loaded rules version: {RULESET_VERSION}")


def fhir_get(base: str, path: str, token: Optional[str] = None) -> Dict[str, Any]:
    """FHIR GET 請求"""
    url = base.rstrip("/") + "/" + path.lstrip("/")
    headers = {"Accept": "application/fhir+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    try:
        logger.debug(f"FHIR GET: {url} (token: {'present' if token else 'missing'})")
        r = requests.get(url, timeout=FHIR_TIMEOUT_SEC, headers=headers)
        
        if r.status_code >= 400:
            error_detail = r.text[:500] if r.text else "No error details"
            logger.error(f"FHIR GET failed {r.status_code}: {url}")
            logger.error(f"Error response: {error_detail}")
            
            # 檢查是否是權限問題
            if r.status_code == 403 or r.status_code == 401:
                error_detail += "\n\n可能原因：缺少 Observation.read 權限。請重新進行 SMART 授權。"
            
            raise HTTPException(
                status_code=502,
                detail=f"FHIR GET failed {r.status_code}: {url} :: {error_detail}"
            )
        
        result = r.json()
        logger.debug(f"FHIR GET successful: {url}")
        return result
    except requests.exceptions.RequestException as e:
        logger.error(f"FHIR GET request exception: {e}")
        raise HTTPException(status_code=502, detail=f"FHIR request failed: {str(e)}")


def fhir_post(base: str, resource_type: str, resource: Dict[str, Any], token: Optional[str] = None) -> Dict[str, Any]:
    """FHIR POST 請求"""
    url = base.rstrip("/") + "/" + resource_type
    headers = {
        "Content-Type": "application/fhir+json",
        "Accept": "application/fhir+json"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    try:
        logger.info(f"FHIR POST to {url} with resource type {resource_type}")
        r = requests.post(url, timeout=FHIR_TIMEOUT_SEC, headers=headers, json=resource)
        if r.status_code >= 400:
            error_detail = r.text[:500] if r.text else "No error details"
            logger.error(f"FHIR POST failed {r.status_code}: {url} - {error_detail}")
            raise HTTPException(
                status_code=502,
                detail=f"FHIR POST failed {r.status_code}: {url} :: {error_detail}"
            )
        result = r.json()
        logger.info(f"FHIR POST successful: {resource_type}/{result.get('id', 'unknown')}")
        return result
    except requests.exceptions.RequestException as e:
        logger.error(f"FHIR POST request exception: {e}")
        raise HTTPException(status_code=502, detail=f"FHIR request failed: {str(e)}")


def now_utc() -> datetime:
    """取得當前 UTC 時間"""
    return datetime.now(timezone.utc)


def parse_fhir_datetime(s: str) -> datetime:
    """解析 FHIR datetime 字串，確保返回 aware datetime"""
    dt = isoparse(s)
    # 如果是 naive datetime，假設為 UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def choose_range_value(low: float, high: float, strategy: str) -> float:
    """根據策略選擇範圍值"""
    if strategy == "low":
        return low
    if strategy == "high":
        return high
    return (low + high) / 2.0


def clamp(value: float, min_v: float, max_v: float) -> Tuple[float, str]:
    """限制值在範圍內"""
    if value < min_v:
        return min_v, "min"
    if value > max_v:
        return max_v, "max"
    return value, "none"


def extract_sr_code(sr: Dict[str, Any]) -> Optional[str]:
    """從 ServiceRequest 提取 code"""
    code = sr.get("code", {})
    codings = code.get("coding", [])
    if not codings:
        return None
    return codings[0].get("code")


def map_sr_to_study_key(sr_code: str, protocol: Protocol) -> Optional[str]:
    """將 ServiceRequest code 映射到 study key"""
    mapping = RULES.get("mapping", {}).get("ServiceRequest.code", {})
    base_key = mapping.get(sr_code)
    if base_key is None:
        return None

    # protocol-dependent mapping
    if sr_code == "MAG3":
        return "MAG3_WITH_FLOW" if protocol.mag3_with_flow else "MAG3_NO_FLOW"
    if sr_code == "FDG_PET":
        return "FDG_BRAIN" if protocol.fdg_region == "brain" else "FDG_BODY"
    return base_key


def get_rule(study_key: str) -> Rule:
    """取得規則"""
    spec = RULES["studies"].get(study_key)
    if not spec:
        raise HTTPException(status_code=400, detail=f"Unknown study_key: {study_key}")
    mbq_per_kg = spec.get("mbq_per_kg")
    rng = spec.get("mbq_per_kg_range")
    mbq_per_kg_range = tuple(rng) if rng else None
    return Rule(
        key=study_key,
        radiopharm=spec["radiopharm"],
        min_mbq=float(spec["min_mbq"]),
        max_mbq=float(spec["max_mbq"]),
        mbq_per_kg=float(mbq_per_kg) if mbq_per_kg is not None else None,
        mbq_per_kg_range=mbq_per_kg_range,
    )


def find_latest_weight_observation(base: str, patient_id: str, token: Optional[str] = None, recently_created_obs_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """尋找最新的體重 Observation（按 effectiveDateTime 排序）
    
    Args:
        base: FHIR base URL
        patient_id: Patient ID (without "Patient/" prefix)
        token: Access token
        recently_created_obs_id: Optional Observation ID that was recently created (to handle indexing delays)
    """
    # LOINC 29463-7 是體重
    logger.info(f"Searching for weight observations for Patient/{patient_id}")
    if recently_created_obs_id:
        logger.info(f"Will check for recently created Observation/{recently_created_obs_id}")
    
    # 取得所有體重 Observation（不依賴伺服器排序，我們自己排序）
    entries = []
    
    # 嘗試查詢所有體重 Observation
    # 先嘗試不使用 code 參數查詢（因為某些 FHIR server 的 code 參數可能不穩定）
    try:
        # 直接查詢所有 Observation，然後手動過濾
        q = f"Observation?patient=Patient/{patient_id}&_count=100"
        logger.info(f"Querying weight observations: {q}")
        bundle = fhir_get(base, q, token)
        entries_all = bundle.get("entry", [])
        logger.info(f"Found {len(entries_all)} total observations for Patient/{patient_id}")
        
        # 手動過濾 LOINC 29463-7
        entries = []
        for e in entries_all:
            obs = e.get("resource", {})
            codings = obs.get("code", {}).get("coding", [])
            for coding in codings:
                if coding.get("system") == "http://loinc.org" and coding.get("code") == "29463-7":
                    entries.append(e)
                    break
        
        logger.info(f"✓ Filtered to {len(entries)} weight observations (LOINC 29463-7)")
        
        # 如果沒有找到，嘗試使用 code 參數查詢作為備選
        if not entries:
            logger.warning(f"No observations found without code filter, trying with code filter...")
            q2 = f"Observation?patient=Patient/{patient_id}&code=http://loinc.org|29463-7&_count=100"
            bundle2 = fhir_get(base, q2, token)
            entries = bundle2.get("entry", [])
            logger.info(f"✓ Found {len(entries)} weight observations with code filter")
    except HTTPException as e:
        logger.error(f"HTTPException querying weight observations: {e.detail}")
        return None
    except Exception as e:
        logger.error(f"Failed to query weight observations: {e}", exc_info=True)
        return None
    
    # 如果有最近建立的 Observation，確保它被包含（處理索引延遲）
    if recently_created_obs_id:
        try:
            direct_obs = fhir_get(base, f"Observation/{recently_created_obs_id}", token)
            codings = direct_obs.get("code", {}).get("coding", [])
            is_weight = any(c.get("system") == "http://loinc.org" and c.get("code") == "29463-7" for c in codings)
            subject_ref = direct_obs.get("subject", {}).get("reference", "")
            is_correct_patient = subject_ref == f"Patient/{patient_id}" or subject_ref.endswith(f"/{patient_id}")
            
            if is_weight and is_correct_patient:
                # 檢查是否已經在 entries 中
                already_in_entries = any(e.get("resource", {}).get("id") == recently_created_obs_id for e in entries)
                if not already_in_entries:
                    logger.info(f"✓ Adding recently created Observation/{recently_created_obs_id} to results (not found in query)")
                    entries.append({"resource": direct_obs})
        except Exception as e:
            logger.debug(f"Could not fetch recently created Observation/{recently_created_obs_id}: {e}")
    
    # 收集所有有效的體重 Observation
    valid_obs = []
    for e in entries:
        obs = e.get("resource", {})
        vq = obs.get("valueQuantity")
        if vq and isinstance(vq.get("value"), (int, float)):
            unit = vq.get("unit", "").lower()
            if "kg" in unit or vq.get("code", "").lower() == "kg":
                valid_obs.append(obs)
    
    if not valid_obs:
        logger.warning(f"No valid weight observations (with kg unit) found for Patient/{patient_id}")
        return None
    
    # 按 effectiveDateTime 排序（最新的在前）
    # 如果沒有 effectiveDateTime，使用 issued 或 meta.lastUpdated
    def get_sort_key(obs):
        # 優先使用 effectiveDateTime
        dt_str = obs.get("effectiveDateTime")
        if not dt_str:
            dt_str = obs.get("issued")
        if not dt_str:
            dt_str = obs.get("meta", {}).get("lastUpdated", "")
        
        try:
            if dt_str:
                parsed = isoparse(dt_str)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
        except Exception as e:
            logger.debug(f"Failed to parse datetime '{dt_str}': {e}")
        
        # 如果無法解析，返回最小日期（會排到最後）
        return datetime.min.replace(tzinfo=timezone.utc)
    
    # 排序：最新的在前（先按 effectiveDateTime，如果相同則按 lastUpdated）
    def get_full_sort_key(obs):
        effective_dt = get_sort_key(obs)
        # 如果 effectiveDateTime 相同，使用 lastUpdated 作為次要排序
        last_updated_str = obs.get("meta", {}).get("lastUpdated", "")
        try:
            if last_updated_str:
                last_updated_dt = isoparse(last_updated_str)
                if last_updated_dt.tzinfo is None:
                    last_updated_dt = last_updated_dt.replace(tzinfo=timezone.utc)
                return (effective_dt, last_updated_dt)
        except:
            pass
        return (effective_dt, datetime.min.replace(tzinfo=timezone.utc))
    
    valid_obs.sort(key=get_full_sort_key, reverse=True)
    
    # 記錄所有體重的資訊（用於除錯）
    logger.info(f"All weight observations for Patient/{patient_id} (total: {len(valid_obs)}):")
    for i, obs in enumerate(valid_obs[:10]):  # 記錄前10個
        weight_val = obs.get('valueQuantity', {}).get('value')
        obs_date = obs.get('effectiveDateTime', obs.get('issued', 'N/A'))
        last_updated = obs.get('meta', {}).get('lastUpdated', 'N/A')
        obs_id = obs.get('id', 'unknown')
        logger.info(f"  [{i+1}] {weight_val} kg (effectiveDate: {obs_date}, lastUpdated: {last_updated}, id: {obs_id})")
    
    # 返回最新的（第一個）
    if not valid_obs:
        logger.error(f"No valid weight observations found for Patient/{patient_id}")
        return None
    
    latest = valid_obs[0]
    weight_val = latest.get('valueQuantity', {}).get('value')
    obs_date = latest.get('effectiveDateTime', latest.get('issued', 'N/A'))
    last_updated = latest.get('meta', {}).get('lastUpdated', 'N/A')
    obs_id = latest.get('id', 'unknown')
    logger.info(f"✓ Selected latest weight Observation: {weight_val} kg (effectiveDate: {obs_date}, lastUpdated: {last_updated}, id: {obs_id})")
    
    return latest


def weight_is_stale(weight_dt: datetime) -> bool:
    """檢查體重是否過舊"""
    # 確保兩個 datetime 都是 aware（有時區資訊）
    now = now_utc()
    if weight_dt.tzinfo is None:
        # 如果是 naive，假設為 UTC
        weight_dt = weight_dt.replace(tzinfo=timezone.utc)
    elif weight_dt.tzinfo != now.tzinfo:
        # 如果時區不同，轉換為 UTC
        weight_dt = weight_dt.astimezone(timezone.utc)
    
    delta_days = (now - weight_dt).days
    return delta_days > WEIGHT_LOOKBACK_DAYS


def get_smart_configuration(fhir_base_url: str) -> Optional[Dict[str, str]]:
    """取得 SMART Configuration"""
    error_details = []
    
    # 嘗試 .well-known/smart-configuration
    try:
        config_url = f"{fhir_base_url}/.well-known/smart-configuration"
        logger.info(f"嘗試取得 SMART Configuration: {config_url}")
        response = requests.get(config_url, timeout=10)
        logger.info(f"回應狀態碼: {response.status_code}")
        if response.status_code == 200:
            config = response.json()
            logger.info(f"成功取得 SMART Configuration")
            return config
        else:
            error_details.append(f".well-known/smart-configuration 返回狀態碼 {response.status_code}: {response.text[:200]}")
    except requests.exceptions.ConnectionError as e:
        error_msg = f"無法連接到 {config_url} - 請確認 SMART Launcher 服務正在運行 (http://localhost:4000)"
        logger.error(error_msg)
        error_details.append(error_msg)
    except requests.exceptions.Timeout as e:
        error_msg = f"連接超時: {config_url}"
        logger.error(error_msg)
        error_details.append(error_msg)
    except Exception as e:
        error_msg = f"無法取得 smart-configuration: {type(e).__name__}: {str(e)}"
        logger.error(error_msg)
        error_details.append(error_msg)
    
    # 嘗試從 CapabilityStatement 取得
    try:
        metadata_url = f"{fhir_base_url}/metadata"
        logger.info(f"嘗試從 metadata 取得 OAuth 端點: {metadata_url}")
        response = requests.get(metadata_url, timeout=10)
        logger.info(f"metadata 回應狀態碼: {response.status_code}")
        if response.status_code == 200:
            metadata = response.json()
            for rest in metadata.get('rest', []):
                security = rest.get('security', {})
                for ext in security.get('extension', []):
                    if ext.get('url') == 'http://fhir-registry.smarthealthit.org/StructureDefinition/oauth-uris':
                        config = {}
                        for sub_ext in ext.get('extension', []):
                            if sub_ext.get('url') == 'authorize':
                                config['authorization_endpoint'] = sub_ext.get('valueUri')
                            elif sub_ext.get('url') == 'token':
                                config['token_endpoint'] = sub_ext.get('valueUri')
                        if config:
                            logger.info(f"從 metadata 成功取得 OAuth 端點")
                            return config
    except requests.exceptions.ConnectionError as e:
        error_msg = f"無法連接到 {metadata_url} - 請確認 SMART Launcher 服務正在運行 (http://localhost:4000)"
        logger.error(error_msg)
        error_details.append(error_msg)
    except Exception as e:
        error_msg = f"無法從 metadata 取得 OAuth 端點: {type(e).__name__}: {str(e)}"
        logger.error(error_msg)
        error_details.append(error_msg)
    
    # 如果都失敗了，記錄所有錯誤
    if error_details:
        logger.error("所有嘗試都失敗了:")
        for detail in error_details:
            logger.error(f"  - {detail}")
    
    return None


def get_token_from_request(request: Request) -> Optional[str]:
    """從請求中取得 access token"""
    # 先嘗試從 Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    
    # 再嘗試從 session
    session_id = request.cookies.get("session_id")
    if session_id and session_id in sessions:
        return sessions[session_id].get("access_token")
    
    return None


# ----------------------------
# FastAPI Routes
# ----------------------------
@app.get("/health")
def health():
    """健康檢查"""
    return {"ok": True, "ruleset": RULESET_VERSION}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主頁面"""
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in sessions:
        return templates.TemplateResponse("launch.html", {"request": request})
    
    session_data = sessions[session_id]
    access_token = session_data.get("access_token")
    fhir_base = session_data.get("fhir_base_url", DEFAULT_FHIR_BASE)
    patient_id = session_data.get("patient_id")
    
    if not access_token or not patient_id:
        return templates.TemplateResponse("launch.html", {"request": request})
    
    # 取得病人資訊
    patient_info = {}
    service_requests = []
    weight_info = {}
    error = None
    
    try:
        # 取得病人
        patient = fhir_get(fhir_base, f"Patient/{patient_id}", access_token)
        name = "未知"
        if patient.get('name') and len(patient['name']) > 0:
            name_obj = patient['name'][0]
            if 'text' in name_obj:
                name = name_obj['text']
            elif 'family' in name_obj:
                given = ' '.join(name_obj.get('given', []))
                name = f"{name_obj['family']} {given}".strip()
        
        patient_info = {
            'name': name,
            'gender': patient.get('gender', '未知'),
            'id': patient.get('id', '未知'),
            'birthDate': patient.get('birthDate', '')
        }
        
        # 取得 ServiceRequest（使用 _lastUpdated 排序，因為 ServiceRequest 不支援 date 排序）
        sr_bundle = fhir_get(fhir_base, f"ServiceRequest?patient={patient_id}&status=active&_sort=-_lastUpdated&_count=10", access_token)
        if sr_bundle.get('entry'):
            service_requests = [e['resource'] for e in sr_bundle['entry']]
        
        # 取得體重
        # 檢查 session 中是否有最近建立的 Observation ID（用於處理索引延遲）
        recently_created_obs_id = session_data.get("recently_created_weight_obs_id")
        if recently_created_obs_id:
            logger.info(f"Found recently created Observation ID in session: {recently_created_obs_id}")
        
        weight_obs = find_latest_weight_observation(fhir_base, patient_id, access_token, recently_created_obs_id)
        
        # 不清除最近建立的 Observation ID，保留給後續計算使用
        # 它會在下次建立新 Observation 時被覆蓋，或在 session 過期時自動清除
        
        if weight_obs:
            vq = weight_obs.get("valueQuantity", {})
            weight_date = weight_obs.get('effectiveDateTime') or weight_obs.get('issued') or weight_obs.get('meta', {}).get('lastUpdated', '')
            weight_info = {
                'value': vq.get('value'),
                'unit': vq.get('unit', 'kg'),
                'date': weight_date,
                'observationId': weight_obs.get('id')
            }
            logger.info(f"Displaying weight for patient {patient_id}: {weight_info['value']} {weight_info['unit']} (date: {weight_date}, observationId: {weight_obs.get('id')})")
        else:
            logger.warning(f"No weight found for patient {patient_id} - showing input form")
    
    except Exception as e:
        error = f"發生錯誤: {str(e)}"
        logger.error(error, exc_info=True)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "patient_info": patient_info,
        "service_requests": service_requests,
        "weight_info": weight_info,
        "error": error,
        "fhir_base": fhir_base
    })


def normalize_fhir_base_url(url: str) -> str:
    """正規化 FHIR base URL，處理容器內部和主機的差異
    將主機地址 (localhost:4000) 轉換為容器內部地址 (smart-launcher:80)
    用於容器內部服務之間的通信
    """
    original_url = url
    url = url.rstrip('/')
    
    # 如果在容器內運行，將 localhost:4000 替換為 smart-launcher:80（容器內部通訊）
    if 'localhost:4000' in url or '127.0.0.1:4000' in url:
        # 檢查是否在 Docker 容器中運行
        is_in_container = (
            os.path.exists('/.dockerenv') or 
            os.getenv('FHIR_BASE', '').startswith('http://smart-launcher') or
            os.getenv('FHIR_BASE', '').startswith('http://hapi-fhir')
        )
        
        if is_in_container:
            # 在容器中運行，使用容器名稱
            url = url.replace('http://localhost:4000', 'http://smart-launcher:80')
            url = url.replace('http://127.0.0.1:4000', 'http://smart-launcher:80')
            logger.info(f"檢測到容器環境，將 FHIR URL 從 {original_url} 轉換為容器內部地址: {url}")
        else:
            logger.debug(f"在主機環境運行，保持原始 URL: {url}")
    
    return url


def normalize_url_for_browser(url: str) -> str:
    """正規化 URL，將容器內部地址轉換為主機地址
    用於返回給瀏覽器的 URL（authorization_endpoint, token_endpoint 等）
    瀏覽器在主機上運行，無法解析容器名稱
    """
    if not url:
        return url
    
    original_url = url
    # 將容器內部地址轉換為主機地址
    # 注意：SMART Launcher 可能返回 http://smart-launcher 或 http://smart-launcher:80
    # 都需要轉換為 http://localhost:4000
    if 'smart-launcher' in url:
        # 先處理帶端口號的情況
        url = url.replace('http://smart-launcher:80', 'http://localhost:4000')
        # 再處理不帶端口號的情況（預設端口是 80，對外映射到 4000）
        url = url.replace('http://smart-launcher', 'http://localhost:4000')
    
    if url != original_url:
        logger.info(f"將瀏覽器 URL 從 {original_url} 轉換為主機地址: {url}")
    
    return url

@app.get("/launch", response_class=HTMLResponse)
async def launch_page(request: Request):
    """SMART 啟動頁面"""
    # 產生 session ID
    session_id = secrets.token_urlsafe(32)
    
    # 從 URL 參數取得 launch 和 iss
    launch_param = request.query_params.get('launch')
    iss_param = request.query_params.get('iss')
    
    fhir_base_url = iss_param if iss_param else DEFAULT_FHIR_BASE
    # 正規化 URL，處理容器內部和主機的差異
    fhir_base_url = normalize_fhir_base_url(fhir_base_url)
    
    # 取得 SMART Configuration
    smart_config = get_smart_configuration(fhir_base_url)
    
    if not smart_config:
        error_html = f"""
        <html>
        <head><title>SMART Configuration 錯誤</title></head>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h1>無法取得 SMART Configuration</h1>
            <p><strong>FHIR 伺服器 URL:</strong> {fhir_base_url}</p>
            <h2>可能的解決方案：</h2>
            <ol>
                <li><strong>確認 SMART Launcher 服務正在運行：</strong>
                    <ul>
                        <li>執行 <code>docker ps</code> 確認 <code>smart-launcher</code> 容器正在運行</li>
                        <li>確認服務可訪問：<a href="http://localhost:4000/v/r4/fhir/.well-known/smart-configuration" target="_blank">http://localhost:4000/v/r4/fhir/.well-known/smart-configuration</a></li>
                    </ul>
                </li>
                <li><strong>檢查 FHIR_BASE 環境變數：</strong>
                    <ul>
                        <li>如果使用 SMART Launcher，應設定為 <code>http://localhost:4000/v/r4/fhir</code></li>
                        <li>如果直接連接 HAPI FHIR（不支援 SMART），應使用 <code>http://localhost:8080/fhir</code></li>
                        <li>當前預設值：{DEFAULT_FHIR_BASE}</li>
                    </ul>
                </li>
                <li><strong>檢查網路連接：</strong>
                    <ul>
                        <li>如果應用程式在 Docker 容器中運行，請使用容器名稱而非 localhost</li>
                        <li>確認防火牆沒有阻擋連接</li>
                    </ul>
                </li>
                <li><strong>檢查服務日誌：</strong>
                    <ul>
                        <li>執行 <code>docker logs smart-launcher</code> 查看 SMART Launcher 的日誌</li>
                        <li>執行 <code>docker logs nm-cds-service</code> 查看本服務的日誌</li>
                        <li>執行 <code>docker logs hapi-fhir-r4</code> 查看 HAPI FHIR 的日誌</li>
                    </ul>
                </li>
            </ol>
            <p><a href="/launch">重新嘗試</a> | <a href="/">返回首頁</a></p>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=500)
    
    auth_endpoint = smart_config.get('authorization_endpoint')
    if not auth_endpoint:
        return HTMLResponse(content="無法取得授權端點 (authorization_endpoint)", status_code=500)
    
    token_endpoint = smart_config.get('token_endpoint')
    
    # 正規化端點 URL（處理容器內部和主機的差異）
    # 重要：授權端點和 token 端點需要從瀏覽器訪問，所以必須轉換為主機地址 (localhost:4000)
    # 而 FHIR base URL 需要從容器內部訪問，所以使用容器名稱 (smart-launcher:80)
    auth_endpoint_for_browser = normalize_url_for_browser(auth_endpoint)
    token_endpoint_for_browser = normalize_url_for_browser(token_endpoint) if token_endpoint else None
    
    # 儲存 session
    # 注意：token_endpoint 需要從容器內部訪問（callback 時），所以保持原始值或容器地址
    # 但我們需要在 callback 時也處理 URL 轉換
    sessions[session_id] = {
        'fhir_base_url': fhir_base_url,
        'token_endpoint': token_endpoint,  # 保持原始值，callback 時會處理
        'oauth_state': secrets.token_urlsafe(32),
        'launch': launch_param
    }
    
    # 建立授權 URL（使用主機地址，供瀏覽器使用）
    from urllib.parse import urlencode
    auth_params = {
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPE,
        'state': sessions[session_id]['oauth_state'],
        'aud': normalize_url_for_browser(fhir_base_url)  # aud 參數也應該使用主機地址
    }
    
    if launch_param:
        auth_params['launch'] = launch_param
    
    auth_url = f"{auth_endpoint_for_browser}?{urlencode(auth_params)}"
    
    response = templates.TemplateResponse("launch.html", {
        "request": request,
        "auth_url": auth_url
    })
    response.set_cookie(key="session_id", value=session_id, httponly=True)
    return response


@app.get("/callback")
async def callback(request: Request):
    """OAuth2 回調處理"""
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in sessions:
        return HTMLResponse(content="無效的 session", status_code=400)
    
    session_data = sessions[session_id]
    
    # 驗證 state
    state = request.query_params.get('state')
    if state != session_data.get('oauth_state'):
        return HTMLResponse(content="無效的 state 參數", status_code=400)
    
    code = request.query_params.get('code')
    if not code:
        return HTMLResponse(content="授權失敗，未取得 code", status_code=400)
    
    token_endpoint = session_data.get('token_endpoint')
    if not token_endpoint:
        return HTMLResponse(content="無法取得 token endpoint", status_code=400)
    
    # 正規化 token_endpoint：callback 是在容器內部調用的，所以需要容器地址
    # 如果 token_endpoint 是主機地址，需要轉換為容器地址
    token_endpoint_normalized = normalize_fhir_base_url(token_endpoint)
    if 'smart-launcher' not in token_endpoint_normalized:
        # 如果還沒有轉換，確保使用容器地址
        token_endpoint_normalized = token_endpoint_normalized.replace('http://localhost:4000', 'http://smart-launcher:80')
        token_endpoint_normalized = token_endpoint_normalized.replace('http://127.0.0.1:4000', 'http://smart-launcher:80')
    
    logger.info(f"使用 token_endpoint: {token_endpoint_normalized} (原始: {token_endpoint})")
    
    # 取得 token
    token_data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID
    }
    
    try:
        response = requests.post(token_endpoint_normalized, data=token_data)
        response.raise_for_status()
        token_info = response.json()
        
        # 儲存 token
        session_data['access_token'] = token_info.get('access_token')
        session_data['patient_id'] = token_info.get('patient')
        
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/", status_code=302)
    
    except Exception as e:
        logger.error(f"無法取得 Token: {e}", exc_info=True)
        return HTMLResponse(content=f"無法取得 Token: {str(e)}", status_code=500)


@app.post("/cds/nm-dose/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest, authorization: Optional[str] = Header(None), request: Request = None):
    """計算建議活度"""
    try:
        token = None
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]
        elif request:
            token = get_token_from_request(request)
        
        if not token:
            logger.warning("No access token found in request")
            return RecommendResponse(
                status="error",
                guideline="North American Consensus Guidelines 2024 update",
                ruleSetVersion=RULESET_VERSION,
                message="No access token found. Please ensure you are logged in via SMART on FHIR."
            )
        
        fhir_base = (req.fhirBase or DEFAULT_FHIR_BASE).rstrip("/")
        
        # 1) 讀取 ServiceRequest
        sr = fhir_get(fhir_base, f"ServiceRequest/{req.serviceRequestId}", token)
        sr_code = extract_sr_code(sr)
        if not sr_code:
            return RecommendResponse(
                status="missing_data",
                guideline="North American Consensus Guidelines 2024 update",
                ruleSetVersion=RULESET_VERSION,
                missing=["ServiceRequest.code"],
                message="ServiceRequest has no code.coding; cannot infer study type."
            )
        
        # 2) 映射到 study key
        study_key = map_sr_to_study_key(sr_code, req.protocol)
        if not study_key:
            return RecommendResponse(
                status="error",
                guideline="North American Consensus Guidelines 2024 update",
                ruleSetVersion=RULESET_VERSION,
                message=f"Unsupported ServiceRequest.code: {sr_code}"
            )
        
        rule = get_rule(study_key)
        
        # 3) 取得最新體重
        # 檢查 session 中是否有最近建立的 Observation ID（用於處理索引延遲）
        recently_created_obs_id = None
        if request:
            session_id = request.cookies.get("session_id")
            if session_id and session_id in sessions:
                recently_created_obs_id = sessions[session_id].get("recently_created_weight_obs_id")
                if recently_created_obs_id:
                    logger.info(f"Found recently created Observation ID in session for calculation: {recently_created_obs_id}")
        
        wobs = find_latest_weight_observation(fhir_base, req.patientId, token, recently_created_obs_id)
        if not wobs:
            return RecommendResponse(
                status="missing_data",
                guideline="North American Consensus Guidelines 2024 update",
                ruleSetVersion=RULESET_VERSION,
                studyKey=study_key,
                studyType=sr_code,
                radiopharmaceutical=rule.radiopharm,
                missing=["weightKg"],
                message="No body weight Observation found (LOINC 29463-7)."
            )
        
        vq = wobs["valueQuantity"]
        weight_kg = float(vq["value"])
        wdt_raw = wobs.get("effectiveDateTime") or wobs.get("issued")
        weight_dt = parse_fhir_datetime(wdt_raw) if wdt_raw else None
        
        warnings: List[str] = []
        missing: List[str] = []
        
        # 檢查體重是否過舊
        if weight_dt:
            if weight_is_stale(weight_dt):
                if WEIGHT_STALE_AS_MISSING:
                    return RecommendResponse(
                        status="missing_data",
                        guideline="North American Consensus Guidelines 2024 update",
                        ruleSetVersion=RULESET_VERSION,
                        studyKey=study_key,
                        studyType=sr_code,
                        radiopharmaceutical=rule.radiopharm,
                        missing=["weightKg"],
                        message=f"Body weight is older than {WEIGHT_LOOKBACK_DAYS} days; please update weight."
                    )
                else:
                    warnings.append(f"Body weight is older than {WEIGHT_LOOKBACK_DAYS} days; consider updating weight.")
        
        # 4) 計算 MBq
        if rule.mbq_per_kg is not None:
            raw = weight_kg * rule.mbq_per_kg
            rec, clamp_reason = clamp(raw, rule.min_mbq, rule.max_mbq)
            rec_obj = Recommendation(
                recommendedMBq=round(rec, 1),
                ruleMBqPerKg=rule.mbq_per_kg,
                minMBq=rule.min_mbq,
                maxMBq=rule.max_mbq,
                clampReason=clamp_reason,
                rawCalculatedMBq=round(raw, 2),
            )
        else:
            low, high = rule.mbq_per_kg_range  # type: ignore
            chosen = choose_range_value(low, high, req.protocol.fdg_strategy)
            raw = weight_kg * chosen
            rec, clamp_reason = clamp(raw, rule.min_mbq, rule.max_mbq)
            rec_obj = Recommendation(
                recommendedMBq=round(rec, 1),
                ruleMBqPerKgRange=(low, high),
                minMBq=rule.min_mbq,
                maxMBq=rule.max_mbq,
                clampReason=clamp_reason,
                rawCalculatedMBq=round(raw, 2),
            )
            warnings.append(f"FDG strategy='{req.protocol.fdg_strategy}' selected within MBq/kg range.")
        
        # 取得考量因素和文獻資料
        study_spec = RULES["studies"].get(study_key, {})
        considerations = study_spec.get("considerations", [])
        references = study_spec.get("references", [])
        guideline_info = RULES.get("guideline", {})
        
        # 記錄使用的體重資訊
        weight_info_display = {
            "value": weight_kg,
            "unit": "kg",
            "date": weight_dt.isoformat() if weight_dt else None,
            "observationId": wobs.get("id")
        }
        logger.info(f"Using weight for calculation: {weight_kg} kg (date: {weight_dt.isoformat() if weight_dt else 'N/A'}, observationId: {wobs.get('id')})")
        
        return RecommendResponse(
            status="ok",
            guideline="North American Consensus Guidelines 2024 update",
            ruleSetVersion=RULESET_VERSION,
            studyKey=study_key,
            studyType=sr_code,
            radiopharmaceutical=rule.radiopharm,
            inputs={
                "weightKg": weight_kg,
                "weightDate": weight_dt.isoformat() if weight_dt else None,
                "weightInfo": weight_info_display,
                "serviceRequestCode": sr_code,
                "protocol": req.protocol.model_dump(),
                "considerations": considerations,
                "references": references,
                "guideline": guideline_info
            },
            recommendation=rec_obj,
            warnings=warnings,
        )
    except HTTPException as e:
        # 重新拋出 HTTPException（FastAPI 會自動處理為 JSON）
        raise e
    except Exception as e:
        # 捕獲所有其他異常，返回 JSON 格式的錯誤
        logger.error(f"Error in recommend endpoint: {e}", exc_info=True)
        return RecommendResponse(
            status="error",
            guideline="North American Consensus Guidelines 2024 update",
            ruleSetVersion=RULESET_VERSION,
            message=f"Internal server error: {str(e)}"
        )


@app.post("/fhir/MedicationRequest/create")
async def create_medication_request(req: CreateMedRequest, authorization: Optional[str] = Header(None), request: Request = None):
    """建立 MedicationRequest"""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif request:
        token = get_token_from_request(request)
    
    fhir_base = (req.fhirBase or DEFAULT_FHIR_BASE).rstrip("/")
    
    mr = {
        "resourceType": "MedicationRequest",
        "status": "active",
        "intent": "order",
        "subject": {"reference": f"Patient/{req.patientId}"},
        "basedOn": [{"reference": f"ServiceRequest/{req.serviceRequestId}"}],
        "medicationCodeableConcept": {
            "coding": [{
                "system": "http://example.org/radiopharm",
                "code": req.radiopharmCode,
                "display": req.radiopharmDisplay
            }]
        },
        "dosageInstruction": [{
            "doseAndRate": [{
                "doseQuantity": {
                    "value": req.recommendedMBq,
                    "unit": "MBq",
                    "system": "http://unitsofmeasure.org",
                    "code": "MBq"
                }
            }]
        }]
    }
    
    # 加入 note
    notes = []
    if req.note:
        notes.append({"text": req.note})
    if req.overrideReason:
        notes.append({"text": f"Override reason: {req.overrideReason}"})
    
    if notes:
        mr["note"] = notes
    
    # 加入 extension 記錄覆寫理由（如果有的話）
    if req.overrideReason:
        mr.setdefault("extension", []).append({
            "url": "http://example.org/fhir/StructureDefinition/override-reason",
            "valueString": req.overrideReason
        })
    
    created = fhir_post(fhir_base, "MedicationRequest", mr, token)
    logger.info(f"Created MedicationRequest/{created.get('id')} for Patient/{req.patientId}")
    return {"ok": True, "id": created.get("id"), "resource": created}


class CreateWeightObservationRequest(BaseModel):
    patientId: str
    weightKg: float
    effectiveDateTime: Optional[str] = None


@app.post("/fhir/Observation/create-weight")
async def create_weight_observation(req: CreateWeightObservationRequest, request: Request = None):
    """建立體重 Observation"""
    try:
        token = get_token_from_request(request)
        
        if not token:
            logger.warning("No access token found for weight observation creation")
            return JSONResponse(
                status_code=401,
                content={"ok": False, "error": "No access token found. Please ensure you are logged in via SMART on FHIR."}
            )
        
        patient_id = req.patientId
        weight_kg = req.weightKg
        effective_date_time = req.effectiveDateTime
        
        logger.info(f"Creating weight Observation: Patient/{patient_id}, weight={weight_kg} kg, date={effective_date_time}")
        
        fhir_base = DEFAULT_FHIR_BASE.rstrip("/")
        
        # 建立 Observation resource
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
            "subject": {"reference": f"Patient/{patient_id}"},
            "valueQuantity": {
                "value": float(weight_kg),
                "unit": "kg",
                "system": "http://unitsofmeasure.org",
                "code": "kg"
            }
        }
        
        # 設定有效日期時間
        if effective_date_time:
            # 轉換 datetime-local 格式為 ISO 8601
            try:
                # datetime-local 格式: YYYY-MM-DDTHH:mm (沒有時區資訊)
                # 轉換為 ISO 8601: YYYY-MM-DDTHH:mm:ss+00:00
                if 'T' in effective_date_time:
                    # 如果沒有秒數，加上 :00
                    if effective_date_time.count(':') == 1:
                        effective_date_time = effective_date_time + ':00'
                    dt = isoparse(effective_date_time)
                else:
                    # 如果只是日期，加上時間
                    dt = isoparse(effective_date_time + 'T00:00:00')
                
                if dt.tzinfo is None:
                    # 假設為本地時間，轉換為 UTC（這裡簡化處理，假設為 UTC）
                    dt = dt.replace(tzinfo=timezone.utc)
                
                observation["effectiveDateTime"] = dt.isoformat()
                logger.info(f"Parsed effectiveDateTime: {observation['effectiveDateTime']}")
            except Exception as e:
                logger.warning(f"Failed to parse effectiveDateTime '{effective_date_time}': {e}, using current time")
                observation["effectiveDateTime"] = now_utc().isoformat()
        else:
            observation["effectiveDateTime"] = now_utc().isoformat()
        
        logger.info(f"Creating weight Observation for Patient/{patient_id}: {weight_kg} kg at {observation.get('effectiveDateTime')}")
        logger.debug(f"Observation resource: {json.dumps(observation, indent=2)}")
        
        created = fhir_post(fhir_base, "Observation", observation, token)
        
        observation_id = created.get("id")
        logger.info(f"Successfully created weight Observation/{observation_id} for Patient/{patient_id}")
        
        # 將新建立的 Observation ID 儲存到 session，以便頁面重新載入時使用
        if request:
            session_id = request.cookies.get("session_id")
            if session_id and session_id in sessions:
                sessions[session_id]["recently_created_weight_obs_id"] = observation_id
                logger.info(f"Stored recently created Observation ID {observation_id} in session for Patient/{patient_id}")
        
        # 驗證建立的 Observation
        if observation_id:
            # 等待更長時間讓 FHIR server 處理和索引更新
            import time
            time.sleep(2.0)  # 增加到 2 秒
            # 嘗試讀取剛建立的 Observation 以確認
            try:
                verify_obs = fhir_get(fhir_base, f"Observation/{observation_id}", token)
                verify_weight = verify_obs.get("valueQuantity", {}).get("value")
                verify_date = verify_obs.get("effectiveDateTime", "N/A")
                verify_last_updated = verify_obs.get("meta", {}).get("lastUpdated", "N/A")
                logger.info(f"✓ Verified created Observation: {verify_weight} kg (date: {verify_date}, id: {observation_id})")
                
                # 再次查詢所有體重，確認新體重能被找到
                all_weights_query = f"Observation?patient=Patient/{patient_id}&code=http://loinc.org|29463-7&_count=20"
                all_weights = fhir_get(fhir_base, all_weights_query, token)
                all_entries = all_weights.get('entry', [])
                logger.info(f"✓ Total weight observations after creation: {len(all_entries)}")
                
                # 檢查新建立的 Observation 是否在查詢結果中
                found_in_query = any(e.get('resource', {}).get('id') == observation_id for e in all_entries)
                if found_in_query:
                    logger.info(f"✓ New Observation {observation_id} is found in query results")
                else:
                    logger.warning(f"⚠ New Observation {observation_id} NOT found in query results - may need more time for indexing")
            except Exception as e:
                logger.warning(f"Could not verify created Observation: {e}")
        
        return {"ok": True, "id": observation_id, "resource": created, "weightKg": weight_kg}
    except HTTPException as e:
        error_msg = str(e.detail)
        logger.error(f"HTTPException creating weight Observation: {error_msg}")
        # 檢查是否是權限問題
        if "403" in error_msg or "Forbidden" in error_msg or "insufficient_scope" in error_msg.lower() or "401" in error_msg:
            error_msg += "\n\n可能原因：缺少 Observation.write 權限。請重新進行 SMART 授權（登出後重新啟動）。"
        return JSONResponse(
            status_code=e.status_code,
            content={"ok": False, "error": error_msg}
        )
    except Exception as e:
        error_msg = f"Internal server error: {str(e)}"
        logger.error(f"Error creating weight Observation: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": error_msg}
        )


@app.get("/logout")
async def logout(request: Request):
    """登出"""
    session_id = request.cookies.get("session_id")
    if session_id and session_id in sessions:
        del sessions[session_id]
    
    from fastapi.responses import RedirectResponse
    response = RedirectResponse(url="/launch", status_code=302)
    response.delete_cookie("session_id")
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)

