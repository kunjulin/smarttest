# SMART on FHIR 測試環境 - Quick Start

本地 FHIR R4 測試環境，用於開發和測試 SMART on FHIR 應用程式。

本專案包含核醫檢查 CDS Service：
- **核醫檢查 CDS Service** (`nm-cds-service/`) - 基於 North American Consensus 2024 的兒科核醫檢查活度建議系統

## 🚀 快速啟動

### 前置需求

- Docker Desktop (已安裝並運行)
- Python 3.7+
- Git (可選)

### 步驟 0: 設定環境變數

首次使用時，需要建立 `.env` 檔案：

```bash
# 複製環境變數範本
cp .env.example .env

# 編輯 .env 檔案（可選，預設值通常已足夠）
# Windows: notepad .env
# Linux/Mac: nano .env
```

`.env` 檔案包含以下設定：

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `HOST` | `localhost` | 主機名稱或 IP 位址 |
| `LAUNCHER_PORT` | `4000` | SMART Launcher 服務埠號 |
| `R4_PORT` | `8080` | HAPI FHIR R4 伺服器埠號 |

**注意：** `.env` 檔案已加入 `.gitignore`，不會被提交到版本控制。如需自訂設定，請修改 `.env` 檔案。

### 步驟 1: 啟動 Docker 環境

```bash
# 啟動 FHIR 伺服器和 SMART Launcher
docker compose up -d
```

等待服務啟動完成（約 30-60 秒），確認容器運行：

```bash
docker compose ps
```

### 步驟 2: 載入測試資料

```bash
# 載入範例病人、醫師、觀察值等資料（包含核醫測試資料）
# 從 nm-cds-service 目錄執行
cd nm-cds-service
python load_sample_data.py
```

### 步驟 3: 啟動 SMART App

#### 選項 A: 使用 Docker（推薦）

核醫檢查 CDS Service 已包含在 `docker-compose.yml` 中，會自動啟動。

#### 選項 B: 本地開發

**Windows PowerShell:**
```powershell
# 啟動核醫檢查 CDS Service
cd nm-cds-service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app:app --reload --port 8000
```

**Linux/Mac:**
```bash
# 啟動核醫檢查 CDS Service
cd nm-cds-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

**注意：** 在 Windows 中，如果 `uvicorn` 命令無法使用，請使用 `python -m uvicorn` 代替。

### 步驟 4: 測試應用程式

#### 測試核醫檢查 CDS Service

1. 開啟瀏覽器前往 **http://localhost:4000** (SMART Launcher)
2. 設定：
   - **FHIR Version**: R4
   - **Patient**: 選擇一個兒科病人（例如：Alex Wu、Sophie Huang、Ryan Liu）
   - **App Launch URL**: `http://localhost:8000/launch`
3. 點擊 **Launch** 按鈕
4. 在頁面上選擇一個 ServiceRequest（檢查醫令）
5. 點擊「計算建議活度」按鈕
6. 查看計算結果，可選擇建立 MedicationRequest

## 📋 服務端點

| 服務 | URL | 說明 |
|------|-----|------|
| SMART Launcher | http://localhost:4000 | OAuth2 授權伺服器和啟動介面 |
| FHIR R4 Server | http://localhost:8080/fhir | HAPI FHIR R4 API 端點 |
| 核醫檢查 CDS Service | http://localhost:8000 | FastAPI CDS 服務（含前端 UI） |
| CDS API 文檔 | http://localhost:8000/docs | Swagger UI API 文檔 |

## 📦 專案結構

```
smarttest-main/
├── docker-compose.yml     # Docker 容器配置
├── nm-cds-service/        # 核醫檢查 CDS Service
│   ├── app.py            # FastAPI 後端服務
│   ├── rules.json        # 核醫檢查規則配置（NA Consensus 2024）
│   ├── requirements.txt  # FastAPI 依賴套件
│   ├── Dockerfile        # Docker 映像檔配置
│   ├── load_sample_data.py  # 載入測試資料腳本（含核醫測試資料）
│   ├── templates/        # FastAPI 前端模板
│   │   ├── index.html    # 主頁面（顯示建議活度）
│   │   └── launch.html   # SMART 啟動頁面
│   ├── README.md         # CDS Service 說明
│   └── USAGE.md          # 使用說明
└── README.md              # 本檔案
```

## 🔧 常用命令

### Docker 管理

```bash
# 啟動服務
docker compose up -d

# 停止服務
docker compose down

# 查看日誌
docker compose logs -f

# 重啟服務
docker compose restart

# 完全重置（刪除資料庫）
docker compose down -v
```

### 測試資料管理

```bash
# 載入測試資料（包含核醫測試資料）
cd nm-cds-service
python load_sample_data.py

# 查看病人列表
curl http://localhost:8080/fhir/Patient

# 查看觀察值
curl http://localhost:8080/fhir/Observation

# 查看 ServiceRequest（核醫檢查）
curl http://localhost:8080/fhir/ServiceRequest
```

## 📝 測試資料

執行 `load_sample_data.py` 後會建立：

### 一般測試資料
- **2 位醫療提供者** (Practitioner)
- **3 位病人** (Patient)
- **3 筆就診記錄** (Encounter)
- **9 筆觀察值** (Observation) - 包含血壓、體溫、心率、BMI、血糖等

### 核醫檢查測試資料
- **3 位兒科病人** (Patient) - Alex Wu (8歲)、Sophie Huang (5歲)、Ryan Liu (12歲)
- **3 筆體重 Observation** (LOINC 29463-7) - 包含最新和過舊的體重資料
- **5 筆 ServiceRequest** - 包含 BONE_SCAN、MAG3、DMSA、MIBG、FDG_PET 等檢查類型

## 🐛 故障排除

### 問題：無法連接到 FHIR 伺服器

**解決方案：**
```bash
# 確認 Docker 容器正在運行
docker compose ps

# 檢查容器日誌
docker compose logs hapi-fhir
```

### 問題：No Providers Found

**解決方案：**
```bash
# 重新載入測試資料
cd nm-cds-service
python load_sample_data.py
```

### 問題：Failed to auto-select encounter

**解決方案：**
- 在 SMART Launcher 中將 **Encounter** 設為 **None**
- 或使用 Standalone Launch 模式

### 問題：Port 已被佔用

**解決方案：**
修改 `.env` 檔案中的 port 設定，或停止佔用該 port 的程式。

```bash
# 編輯 .env 檔案，修改對應的 PORT 設定
# 例如：將 LAUNCHER_PORT=4000 改為 LAUNCHER_PORT=4002
```

### 問題：找不到 .env 檔案

**解決方案：**
```bash
# 從範本建立 .env 檔案
cp .env.example .env
```

### 問題：環境變數未生效

**解決方案：**
```bash
# 修改 .env 後，需要重啟 Docker 容器
docker compose down
docker compose up -d
```

## 📚 相關資源

- [SMART on FHIR 官方文件](http://docs.smarthealthit.org/)
- [FHIR R4 規範](https://www.hl7.org/fhir/R4/)
- [HAPI FHIR 文件](https://hapifhir.io/)

## 🔄 更新測試資料

如果需要重新載入測試資料：

```bash
# 刪除現有資料（可選）
docker compose down -v
docker compose up -d

# 載入新資料
cd nm-cds-service
python load_sample_data.py
```

## 🏥 核醫檢查 CDS Service 詳細說明

### 功能特色

- **基於 North American Consensus Guidelines 2024**：實作最新的兒科核醫檢查活度建議
- **支援多種檢查類型**：
  - 骨掃描 (BONE_SCAN / 99mTc-MDP)
  - 腎臟掃描 (MAG3 / 99mTc-MAG3) - 支援 flow/no-flow 模式
  - 腎皮質掃描 (DMSA / 99mTc-DMSA)
  - MIBG 掃描 (MIBG / 123I-MIBG)
  - FDG PET 掃描 (FDG_PET / 18F-FDG) - 支援 body/brain 區域和策略選擇
- **自動計算建議活度**：根據病人體重和檢查類型計算
- **安全範圍限制**：自動套用 min/max clamp，並顯示原因
- **體重過舊警告**：檢查體重資料是否過舊（預設 >90 天）
- **覆寫功能**：支援醫師覆寫活度並記錄理由
- **FHIR 整合**：自動建立 MedicationRequest，連結到原始 ServiceRequest

### API 端點

- `GET /health` - 健康檢查
- `GET /` - 主頁面（需要 SMART 授權）
- `GET /launch` - SMART 啟動頁面
- `GET /callback` - OAuth2 回調處理
- `POST /cds/nm-dose/recommend` - 計算建議活度（API）
- `POST /fhir/MedicationRequest/create` - 建立 MedicationRequest（API）
- `GET /docs` - Swagger UI API 文檔

### 環境變數

可在 `docker-compose.yml` 或環境中設定：

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `FHIR_BASE` | `http://localhost:8080/fhir` | FHIR 伺服器基礎 URL |
| `CLIENT_ID` | `nm-cds-client` | SMART on FHIR Client ID |
| `REDIRECT_URI` | `http://localhost:8000/callback` | OAuth2 重定向 URI |
| `WEIGHT_LOOKBACK_DAYS` | `90` | 體重資料有效天數 |
| `WEIGHT_STALE_AS_MISSING` | `false` | 體重過舊是否視為缺資料 |

### 使用範例

#### 透過 API 計算建議活度

```bash
curl -X POST http://localhost:8000/cds/nm-dose/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "patientId": "PATIENT_ID",
    "serviceRequestId": "SERVICE_REQUEST_ID",
    "protocol": {
      "mag3_with_flow": false,
      "fdg_region": "body",
      "fdg_strategy": "low"
    }
  }'
```

#### 建立 MedicationRequest

```bash
curl -X POST http://localhost:8000/fhir/MedicationRequest/create \
  -H "Content-Type: application/json" \
  -d '{
    "patientId": "PATIENT_ID",
    "serviceRequestId": "SERVICE_REQUEST_ID",
    "recommendedMBq": 35.5,
    "radiopharmCode": "FDG",
    "radiopharmDisplay": "18F-FDG",
    "note": "Dose per NA Consensus 2024",
    "overrideReason": "臨床考量：病人體重變化"
  }'
```

### 規則配置

規則配置位於 `nm-cds-service/rules.json`，包含：
- 各檢查類型的 MBq/kg 計算規則
- min/max 活度限制
- ServiceRequest code 到檢查類型的映射

## 📄 授權

本專案僅供開發和測試使用。
