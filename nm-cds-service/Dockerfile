FROM python:3.11-slim

WORKDIR /app

# 複製依賴檔案
COPY requirements.txt .

# 安裝依賴
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式檔案
COPY . .

# 暴露端口
EXPOSE 8000

# 啟動應用程式
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]


