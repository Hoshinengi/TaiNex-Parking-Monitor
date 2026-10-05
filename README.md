# TaiNEX Parking Monitor

台北南港展覽館（TaiNEX）展覽時程與停車費率查詢工具，提供 Android App 與電腦版 HTML 報告兩種使用方式。

目前版本：**v0.2.0**

## 功能

- **當前停車費率**：依官網「指定展期費率」自動判斷 1 館、2 館今天是展期或一般費率，顯示每小時費率、每日上限與過夜費
- **展覽行事曆**：雙月顯示，可左右切換月份；日期上方以色條標示 1 館（藍）、2 館（橘）的展覽
- **停車優惠紀錄**：點擊日期標記已使用信用卡停車優惠（綠點），自動統計本月已用／剩餘次數（每月 10 次）
- **近期展覽清單**：展覽名稱、館別、日期、地點，可點擊連到官網
- **一鍵更新**：App 右上角更新按鈕即時重新擷取官網資料

資料來源：[TaiNEX 展會活動](https://www.tainex.com.tw/event)、[TaiNEX 停車場](https://www.tainex.com.tw/service/transportation/parking-garage)

## 檔案說明

| 檔案 | 說明 |
|---|---|
| `tainex_app.py` | Flet App 主程式（Android / 桌面） |
| `tainex_monitor.py` | 產生 HTML 報告並用瀏覽器開啟 |
| `南港展覽館報告.bat` | 雙擊執行 `tainex_monitor.py` |
| `pyproject.toml` | 專案設定與 Flet 打包設定 |
| `assets/icon.png` | App 圖示 |
| `.github/workflows/build-apk.yml` | GitHub Actions 自動建置 APK |

## 安裝 Android App

1. 到 [Actions](https://github.com/Hoshinengi/TaiNex-Parking-Monitor/actions) 點進最新成功的 **Build Android APK**
2. 頁面底部 **Artifacts** 下載 `tainex-monitor-apk`（需登入 GitHub）
3. 解壓縮後將 `.apk` 傳到手機安裝（需允許安裝未知來源 App）

每次 push 到 `main` 會自動建置新版 APK，也可以在 Actions 頁面手動 **Run workflow**。

## 電腦上執行

```powershell
pip install -r requirements.txt

# 桌面版 App
python tainex_app.py

# HTML 報告
python tainex_monitor.py
```

## 注意事項

- 停車優惠紀錄存在本機（手機為 App 私有資料目錄，電腦為 `parking_discount.json`），解除安裝 App 會一併清除
- 官網改版可能導致資料擷取失敗，費率顯示 `?` 時通常就是頁面結構變了
- 實際費率以停車場現場公告為準

## 版本紀錄

### v0.2.0
- 配合官網停車場頁面改版，重寫停車費率解析
- 改用官網「指定展期費率」日期判斷展期／一般費率，並顯示當日實際上限（350 元或無上限）
- 新增雙月展覽行事曆（可切換月份、色條標示館別）
- 新增信用卡停車優惠使用紀錄
- 修正同時在 1、2 館舉辦的展覽只顯示 1 館的問題
- 停車費卡片改用展館 logo、自訂 App 圖示

### v0.1
- 初版：展覽時程、當前停車費率、HTML 報告、Android App
