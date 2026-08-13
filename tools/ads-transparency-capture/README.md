# AFI-OS Capture Helper

MVP này là **browser-assisted capture**, không phải crawler.

## Cài trên Chrome/Chromium

1. Chạy AFI-OS tại `http://127.0.0.1:8765`.
2. Mở `chrome://extensions`.
3. Bật **Developer mode**.
4. Chọn **Load unpacked** và chọn thư mục này.
5. Mở Ads Transparency Center, tìm advertiser/project và chọn đoạn text cần làm bằng chứng.
6. Bấm extension, nhập `advertiser_name` + `project_domain`, rồi Capture.

## Ranh giới cố ý

- Không tự cuộn trang.
- Không tự mở kết quả kế tiếp.
- Không vượt CAPTCHA hoặc cơ chế chống tự động.
- Không chạy nền.
- Lưu nguồn, thời điểm và bản text thô để có thể kiểm toán lại.
