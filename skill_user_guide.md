# Skill User Guide

這份文件是給你自己在 Codex 裡快速使用 skills 的實用指南。

## 1. Skill 是什麼

Skill 可以把某一類工作流程包成一套固定做法，讓 Codex 在處理任務時更穩定。

例如：
- `debugging-and-error-recovery`: 適合查 bug、定位錯誤、縮小問題範圍
- `frontend-ui-engineering`: 適合改 UI、版面、互動與前端結構
- `code-review-and-quality`: 適合做 code review
- `spec-driven-development`: 適合先寫需求與規格，再開始實作
- `test-driven-development`: 適合要先補測試、再改功能

## 2. 你現在已經安裝好的 skills

你目前安裝了這些 skills：

- `api-and-interface-design`
- `browser-testing-with-devtools`
- `ci-cd-and-automation`
- `code-review-and-quality`
- `code-simplification`
- `context-engineering`
- `debugging-and-error-recovery`
- `deprecation-and-migration`
- `documentation-and-adrs`
- `frontend-ui-engineering`
- `git-workflow-and-versioning`
- `idea-refine`
- `incremental-implementation`
- `performance-optimization`
- `planning-and-task-breakdown`
- `security-and-hardening`
- `shipping-and-launch`
- `source-driven-development`
- `spec-driven-development`
- `test-driven-development`
- `using-agent-skills`

## 3. 最簡單的使用方式

你可以直接在對話裡明講 skill 名稱。

### 方式 A：直接提 skill 名稱

範例：

```text
請用 debugging-and-error-recovery 幫我查 copy_exe.py 為什麼 GPIO 狀態不對
```

```text
請用 frontend-ui-engineering 幫我把這個 tkinter 畫面排版調得更像附圖
```

```text
請用 code-review-and-quality review 這個檔案
```

### 方式 B：用 `$skill-name`

範例：

```text
$debugging-and-error-recovery 幫我查 serial packet 為什麼解析錯誤
```

```text
$test-driven-development 幫我先補 verify_gpio.py 的測試，再重構 copy_exe.py
```

這兩種方式都可以，直接寫 skill 名稱通常就夠了。

## 4. 什麼情況該用哪個 skill

### 查 bug

用：
- `debugging-and-error-recovery`

適合：
- 數值對不上
- 封包解析錯誤
- UI 顯示和實際狀態不同
- 某個功能之前正常，改完壞掉

你可以這樣說：

```text
請用 debugging-and-error-recovery 幫我查 PB5/PB6/PB8 為什麼沒有亮綠燈
```

### 改 UI / 畫面

用：
- `frontend-ui-engineering`

適合：
- 視覺排版
- 元件擺放
- 表格 / 卡片 / 狀態區重排
- 參考圖片做仿製

你可以這樣說：

```text
請用 frontend-ui-engineering 把 copy_exe.py 的 UI 改得更像第一張圖
```

### 先規劃再做

用：
- `spec-driven-development`
- `planning-and-task-breakdown`

適合：
- 新功能還沒開始做
- 你想先把需求講清楚
- 你想把大任務拆成好做的小步驟

你可以這樣說：

```text
請用 spec-driven-development 幫我整理這個 power monitor 的需求
接著用 planning-and-task-breakdown 幫我拆成可實作的步驟
```

### 想讓改動更安全

用：
- `test-driven-development`
- `incremental-implementation`

適合：
- 你要重構
- 你怕一改壞掉
- 想先補測試再改

你可以這樣說：

```text
請用 test-driven-development 幫我先替 verify_gpio.py 建立測試
再用 incremental-implementation 一步一步重構 copy_exe.py
```

### 做 code review

用：
- `code-review-and-quality`

你可以這樣說：

```text
請用 code-review-and-quality review copy_exe.py
```

### 想精簡程式

用：
- `code-simplification`

你可以這樣說：

```text
請用 code-simplification 幫我把 copy_exe.py 簡化，但不要改變行為
```

## 5. 你這個專案最常用的 skill 組合

### 組合 1：查硬體資料問題

推薦：
- `debugging-and-error-recovery`
- `source-driven-development`

適合：
- ADC byte 對不上
- endian 問題
- baud / packet / GPIO 格式不明

範例：

```text
請用 debugging-and-error-recovery + source-driven-development
幫我確認這個 serial packet 的欄位定義是不是正確
```

### 組合 2：UI 調整

推薦：
- `frontend-ui-engineering`
- `incremental-implementation`

範例：

```text
請用 frontend-ui-engineering + incremental-implementation
幫我把畫面改成像參考圖，但每次只改一塊並驗證
```

### 組合 3：安全重構

推薦：
- `test-driven-development`
- `code-simplification`

範例：

```text
請用 test-driven-development + code-simplification
幫我重構 copy_exe.py，先保住行為再簡化結構
```

## 6. 我建議你平常怎麼下指令

你可以用這個模板：

```text
請用 [skill 名稱]
處理 [檔案 / 功能]
目標是 [你要的結果]
限制是 [不能動的地方 / 特別要求]
```

例如：

```text
請用 debugging-and-error-recovery
處理 copy_exe.py 的 GPIO 判斷
目標是讓 PB5/PB6/PB8 正確顯示綠紅
限制是不要破壞現在 ADC 與 POWER 顯示
```

再例如：

```text
請用 frontend-ui-engineering
處理 copy_exe.py 的版面
目標是接近我附的第一張圖
限制是功能邏輯不要改
```

## 7. 如果你不知道該用哪個 skill

最簡單就直接說：

```text
請用 using-agent-skills 幫我判斷這個任務該用哪些 skills
```

或者：

```text
我現在要改 copy_exe.py 的 serial、GPIO、UI
請幫我選最適合的 skills 再開始做
```

## 8. 實用建議

- 如果任務很明確，直接指定 skill，效果通常最好。
- 如果任務又大又雜，可以一次指定 2 個 skill，但不要太多。
- 如果你想要 Codex 直接做，不只分析，記得補一句「直接改」或「直接實作」。
- 如果你只想先討論，不要動檔案，就明講「先不要改 code」。

## 9. 建議你先收藏的常用句

```text
請用 debugging-and-error-recovery 幫我查這個 bug，直接改。
```

```text
請用 frontend-ui-engineering 幫我調整這個畫面，風格參考附圖。
```

```text
請用 code-review-and-quality review 這個檔案，先列問題。
```

```text
請用 test-driven-development 幫我先補測試，再改功能。
```

```text
請用 using-agent-skills 幫我挑這題最適合的 skill。
```

