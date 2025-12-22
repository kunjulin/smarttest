# 核醫檢查 CDS Service

基於 North American Consensus Guidelines 2024 的兒科核醫檢查活度建議系統。

## 功能

- 根據病人體重和檢查類型自動計算建議活度（MBq）
- 支援多種核醫檢查類型（骨掃、MAG3、DMSA、MIBG、FDG PET）
- 自動套用安全範圍限制（min/max clamp）
- 體重過舊警告/檢查
- 支援覆寫活度並記錄理由
- 自動建立 FHIR MedicationRequest

## 快速開始

### 使用 Docker（推薦）

服務已包含在主專案的 `docker-compose.yml` 中，會自動啟動。

### 本地開發

**Windows PowerShell:**
```powershell
# 建立虛擬環境
python -m venv .venv
.venv\Scripts\activate

# 安裝依賴
pip install -r requirements.txt

# 啟動服務（使用 python -m uvicorn 確保使用正確的 Python）
python -m uvicorn app:app --reload --port 8000
```

**Linux/Mac:**
```bash
# 建立虛擬環境
python -m venv .venv
source .venv/bin/activate

# 安裝依賴
pip install -r requirements.txt

# 啟動服務
uvicorn app:app --reload --port 8000
```

**注意：** 在 Windows 中，如果直接使用 `uvicorn` 命令出現錯誤，請使用 `python -m uvicorn` 代替。

## 配置

環境變數（可在 `docker-compose.yml` 或環境中設定）：

- `FHIR_BASE`: FHIR 伺服器 URL（預設：`http://localhost:8080/fhir`）
- `CLIENT_ID`: SMART on FHIR Client ID
- `REDIRECT_URI`: OAuth2 重定向 URI
- `WEIGHT_LOOKBACK_DAYS`: 體重資料有效天數（預設：90）
- `WEIGHT_STALE_AS_MISSING`: 體重過舊是否視為缺資料（預設：false）

## API 文檔

啟動服務後，訪問：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 規則配置

規則配置位於 `rules.json`，包含：
- 各檢查類型的 MBq/kg 計算規則
- min/max 活度限制
- ServiceRequest code 映射

## 授權

本服務實作 SMART on FHIR 授權流程，支援：
- Standalone Launch
- EHR Launch（透過 SMART Launcher）

