# nm-cds-service 使用說明

## 快速開始

### 1. 確認服務正在運行

```powershell
# 檢查 Docker 容器狀態
docker ps

# 應該看到以下容器正在運行：
# - hapi-fhir-r4
# - smart-launcher
# - nm-cds-service
```

### 2. 重新啟動服務（如果已修改配置）

```powershell
# 停止並重新啟動服務
docker compose restart nm-cds-service

# 或者完全重建
docker compose up -d --build nm-cds-service
```

### 3. 載入測試資料（如果尚未載入）

```powershell
# 從專案根目錄執行
python load_sample_data.py
```

### 4. 訪問應用程式

#### 方式 A：通過 SMART Launcher 啟動（推薦）

1. 開啟瀏覽器訪問：**http://localhost:4000**
2. 設定以下參數：
   - **FHIR Version**: R4
   - **Patient**: 選擇一個兒科病人（例如：Alex Wu、Sophie Huang、Ryan Liu）
   - **Practitioner**: 選擇一個醫師（可選）
   - **App Launch URL**: `http://localhost:8000/launch`
3. 點擊 **Launch** 按鈕

#### 方式 B：直接訪問應用程式

1. 開啟瀏覽器訪問：**http://localhost:8000/launch**
2. 應用程式會自動嘗試連接到 SMART Launcher 進行授權

### 5. 使用功能

#### 查看病人資訊和體重
- 登入後，首頁會顯示：
  - 病人基本資訊（姓名、性別、生日）
  - 最新體重（如果有的話）
  - 活躍的 ServiceRequest（檢查醫令）

#### 計算建議活度
1. 選擇一個 ServiceRequest（檢查醫令）
2. 如果沒有體重，可以：
   - 輸入體重並建立 Observation
   - 或等待系統自動查詢現有體重
3. 點擊「計算建議活度」按鈕
4. 查看計算結果：
   - 建議活度（MBq）
   - 計算規則和範圍
   - 警告訊息（如果有）

#### 建立 MedicationRequest
1. 計算建議活度後
2. 可以選擇：
   - 使用建議值建立 MedicationRequest
   - 或覆寫活度並輸入理由

## API 文檔

訪問以下網址查看完整的 API 文檔：

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 故障排除

### 問題：無法取得 SMART Configuration

**症狀**：訪問 `/launch` 時顯示錯誤訊息

**解決方案**：
1. 確認 SMART Launcher 正在運行：
   ```powershell
   docker logs smart-launcher
   ```

2. 測試 SMART Launcher 端點：
   在瀏覽器中訪問：http://localhost:4000/v/r4/fhir/.well-known/smart-configuration
   應該會看到 JSON 格式的配置

3. 檢查服務日誌：
   ```powershell
   docker logs nm-cds-service
   ```

4. 重新啟動服務：
   ```powershell
   docker compose restart nm-cds-service smart-launcher
   ```

### 問題：無法讀取病人資料

**症狀**：登入後看不到病人資訊或體重

**解決方案**：
1. 確認已載入測試資料：
   ```powershell
   python load_sample_data.py
   ```

2. 檢查 FHIR 伺服器：
   訪問 http://localhost:8080/fhir/Patient 查看是否有病人資料

3. 檢查授權範圍：
   確認授權時選擇了正確的 scope（應包含 `patient/Patient.read` 和 `patient/Observation.read`）

### 問題：無法建立 Observation

**症狀**：輸入體重後無法建立 Observation

**解決方案**：
1. 確認授權範圍包含 `patient/Observation.write`
2. 檢查服務日誌：
   ```powershell
   docker logs nm-cds-service
   ```
3. 重新進行 SMART 授權（登出後重新啟動）

## 配置說明

### 環境變數

可以在 `docker-compose.yml` 中修改以下環境變數：

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `FHIR_BASE` | `http://smart-launcher:80/v/r4/fhir` | FHIR 伺服器 URL（應使用 SMART Launcher） |
| `CLIENT_ID` | `nm-cds-client` | SMART on FHIR Client ID |
| `REDIRECT_URI` | `http://localhost:8000/callback` | OAuth2 重定向 URI |
| `WEIGHT_LOOKBACK_DAYS` | `90` | 體重資料有效天數 |
| `WEIGHT_STALE_AS_MISSING` | `false` | 體重過舊是否視為缺資料 |

### 修改配置後

```powershell
# 重新啟動服務以套用新配置
docker compose restart nm-cds-service

# 或完全重建
docker compose up -d --build nm-cds-service
```

## 本地開發

如果想在本地運行（不使用 Docker）：

```powershell
# 進入服務目錄
cd nm-cds-service

# 建立虛擬環境
python -m venv .venv
.venv\Scripts\activate

# 安裝依賴
pip install -r requirements.txt

# 設定環境變數（PowerShell）
$env:FHIR_BASE="http://localhost:4000/v/r4/fhir"
$env:CLIENT_ID="nm-cds-client"
$env:REDIRECT_URI="http://localhost:8000/callback"

# 啟動服務
python -m uvicorn app:app --reload --port 8000
```

## 支援的檢查類型

根據 `rules.json` 配置，支援以下檢查類型：

- **骨掃** (Bone Scan)
- **MAG3** (MAG3 Scan)
- **DMSA** (DMSA Scan)
- **MIBG** (MIBG Scan)
- **FDG PET** (FDG PET Scan)

每個檢查類型都有對應的：
- MBq/kg 計算規則
- 最小/最大活度限制
- 放射性藥物資訊

