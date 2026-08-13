# AFI-OS Internal Production Replatform

AFI-OS là sản phẩm độc lập giúp một người vận hành hoạt động affiliate qua Google Ads theo hướng **evidence-first, profit-first và local-first**.

Repository này là bản triển khai mới, giữ sản phẩm cũ trong `legacy/v3/` nhưng xây lại lõi production:

- SQLite + migration thay cho `localStorage` làm nguồn dữ liệu chính.
- Commission ledger tách `PENDING / APPROVED / LOCKED / PAID / REJECTED / REFUNDED / CHARGEBACK`.
- Terms warning: `AMBIGUOUS`, `CONFLICT`, `PROHIBITED` và `NOT_CHECKED` được hiển thị rõ nhưng không loại dự án khỏi Radar, Economics hay tracking.
- Economics engine tách one-time, recurring giới hạn và lifetime.
- Module ⓪ **Truy vết quảng cáo / Advertiser Graph** phân biệt số advertiser độc lập với số lượng mẫu quảng cáo.
- Batch advertiser snapshot lưu stable advertiser ID, URL nguồn, checked_at, evidence,
  số quảng cáo được nguồn báo cáo và audit; retry không tạo trùng.
- Portfolio phân biệt `Chưa thu thập`, dữ liệu một phần và số đã quan sát; thiếu dữ liệu
  hoặc thiếu cửa sổ last-seen không bao giờ bị trình bày thành số 0.
- Browser-assisted capture, không crawler hàng loạt.
- Audit log, idempotency constraints và automated tests.
- Terms Evidence automation nhận domain, lưu proposal có nguồn và không tự mở permission.
- Generic Terms collector chỉ đọc một tập nhỏ trang HTTPS chính thức cùng domain, chặn private host/redirect ngoài domain và tự trích proposal PPC/commission để xét duyệt.
- Trang chính thức lớn được đọc tối đa 1 MB thay vì bị bỏ toàn bộ; audit và Evidence Pack ghi rõ URL nào bị cắt ngắn.
- URL nguồn bỏ riêng tham số navigation/tracking đã biết (`nav`, `utm_*`, click IDs), nhưng giữ query nghiệp vụ và chữ ký; cùng một trang không còn chiếm nhiều slot rà Terms.
- Hash của trang bị cắt ngắn không được dùng làm bằng chứng `CONTENT_CHANGED`; audit trả `PARTIAL` khi prefix động khác nhau, còn proposal PPC/commission vẫn được so riêng.
- 404/410 của đường dẫn chuẩn chỉ được hệ thống dò thử không còn bị ghi là lỗi; URL đã lưu/link chính thức bị mất và lỗi tạm thời vẫn được audit/retry.
- Terms research nhớ mọi URL chính thức liên quan đã rà theo domain và tự ưu tiên dùng lại, nhưng không tái dùng nguồn chỉ còn trong evidence/fact đã reject.
- Permission extractor đọc theo từng câu chính sách, nên lệnh cấm direct link không bị suy rộng thành cấm toàn bộ PPC.
- Permission evidence và commission facts được tách riêng; chỉ claim cùng commercial
  subject mâu thuẫn mới tạo `CONFLICT`, còn rate cho sản phẩm/add-on khác nhau là tier.
- Official permission proposal mới trái với evidence đã chấp nhận lập tức hạ trạng thái xanh thành cảnh báo `CONFLICT`, nhưng không tự sửa permission.
- Commission CSV Import có preview, chống đếm trùng, cập nhật trạng thái và hàng đợi UNATTRIBUTED.
- Backup SQLite một nút ghi schema/integrity/foreign keys; restore tự bỏ qua bản hỏng hoặc sai schema và tạo backup khẩn cấp.
- Backup được kiểm tra lại checksum/integrity/foreign key/schema khi hiển thị; bản lịch lỗi không thể trì hoãn bản thay thế tự động.
- Google Ads CSV preview/import idempotent và màn hình Risk & Exposure tách spend, commission, actual cash và terms risk.
- Currency normalization ledger giữ nguyên số tiền gốc, chỉ dùng tỷ giá có nguồn đã được duyệt.
- Reconciliation queue giữ riêng `ATTRIBUTED / PARTIAL / UNATTRIBUTED / DUPLICATE / CONFLICT` để không âm thầm ghi đè giao dịch.
- Operations Inbox gom Terms/commission proposals, FX, reconciliation, nguồn còn thiếu và campaign warnings thành một hàng đợi ngoại lệ.
- Operations Inbox gom commission proposal theo chương trình, còn `NOT_CHECKED` chỉ là cảnh báo tự theo dõi; số “cần xử lý” không còn đếm từng dòng vô nghĩa.
- Terms Evidence Center tách “automation đã rà nguồn” khỏi “đã có evidence PPC”; lần rà thành công nhưng không thấy quyền PPC công khai được ghi thành cảnh báo riêng.
- Operations Inbox gộp cảnh báo Terms cấp chương trình với cảnh báo campaign cùng nguyên nhân thành một việc theo dõi; số lượng và tên campaign vẫn hiện đầy đủ.
- Cảnh báo Terms của nhiều campaign cùng chương trình cũng được gom ở Inbox; Risk & Exposure vẫn giữ từng campaign.
- Chế độ macOS 24/7 tự khởi động lại server, heartbeat bảo trì mỗi 30 phút và tránh hai chu kỳ chồng nhau.
- Auto-ingest chọn báo cáo Google Ads campaign mới nhất trong Downloads, nhập idempotent và đưa file lỗi/campaign chưa ghép vào Operations Inbox.
- Auto-ingest xác minh Customer ID trước khi ghi; CSV cũ chưa có Customer ID phải khớp tiền tệ của tài khoản đã cấu hình. Báo cáo sai tài khoản chỉ tạo cảnh báo và không chạm dữ liệu.
- Auto-ingest chỉ cập nhật metadata campaign khi cột tương ứng thật sự có giá trị; báo cáo rút gọn không thể xoá ngân sách, trạng thái, loại chiến dịch, tên tài khoản hoặc tiền tệ đã lưu.
- Nếu Google Ads không xuất `Campaign ID`, auto-ingest chỉ khôi phục mã từ `Customer ID` trực tiếp và một tên campaign khớp duy nhất trong tài khoản đã lưu; mọi trường hợp sai/mơ hồ ghi 0 dòng.
- Campaign mới tự ghép chương trình khi tên chứa đúng một merchant domain; domain mơ hồ vẫn vào Inbox và mapping thủ công không bị ghi đè.
- Mỗi chu kỳ bảo trì rà lại cả campaign cũ chưa ghép, nên không cần chờ file Ads thay đổi mới áp dụng quy tắc domain.
- Command Center hiện số campaign vừa tự ghép, còn chưa ghép và mapping cũ được bảo toàn trong chu kỳ gần nhất.
- Auto-ingest commission chỉ đọc CSV có tên commission/hoa hồng, yêu cầu mapping chương trình duy nhất và chặn toàn bộ file lỗi/xung đột trước khi ghi.
- Thiết lập Google Ads một lần bấm dùng OAuth Desktop loopback + PKCE và lưu bốn credential trực tiếp trong macOS Keychain.

## Chạy trên Mac

Trong Finder, mở thư mục AFI-OS rồi nhấp chuột phải `START-AFI-OS.command` → **Mở**.

Dành cho kỹ thuật:

```bash
cd ~/Downloads/AFI-OS
./START-AFI-OS.command
```

Mở: `http://127.0.0.1:8765`

API docs: `http://127.0.0.1:8765/api/docs`

## Kiểm thử

```bash
make test
make lint
```

## Cấu trúc

```text
apps/web/                         giao diện mới
src/afi_os/                       backend FastAPI + domain services
migrations/                       schema migration
services/economics.py             financial truth model
services/compliance.py            terms warning evaluation
services/programs.py              persistent terms/evidence resolution
services/campaign_import.py       Google Ads CSV preview/import
services/exposure.py              campaign spend + commission risk view
services/commission_import.py     CSV parser, dedupe, state update, attribution
services/currency.py              sourced FX proposals + normalized finance view
services/reconciliation.py        persistent exception queue + resolution audit
services/backups.py               consistent SQLite backup/restore
services/ad_intelligence.py       independent advertiser score
tools/ads-transparency-capture/   Chrome capture helper
legacy/v3/                        sản phẩm Claude cũ, không sửa
reference/                        audit và gói bàn giao gốc
docs/                             spec, quyết định, taskboard, runbook
```

## Trạng thái

Đây là **v0.2.103**. Công thức hoàn vốn áp dụng đúng kịch bản sheet `3× bid thấp` và `0,5× bid cao`, quy đổi bid VND sang giá gói USD bằng tỷ giá cố định 26.000 VND/USD. `/api/appraise` trả điểm thật 0–100 và trạng thái đạt/chưa đạt/chờ dữ liệu; điều khoản cấm Ads vẫn chỉ tạo cảnh báo, không tự loại dự án hoặc dừng campaign.

Command Center tiếp tục phân biệt lần quét folder với thời điểm file Google Ads thực sự được xuất. Khi snapshot có dữ liệu của hôm nay nhưng file nguồn đã hơn 6 giờ, hệ thống tạo cảnh báo làm mới không chặn và không sửa/dừng campaign.

Trình thiết lập Google Ads tiếp tục tự tìm duy nhất OAuth Desktop JSON hợp lệ trong Downloads, bỏ qua JSON hỏng, web-client, file lớn và symlink. Nếu có nhiều client hợp lệ, hệ thống không tự đoán mà yêu cầu chọn rõ file.

Sau khi chọn JSON, OAuth + API preflight vẫn phải hoàn tất trước khi bất kỳ credential nào được ghi nguyên tử vào macOS Keychain. Desktop client ID/secret không được in hoặc lưu database.

Evidence Pack format 4 tiếp tục tự mang theo URL đăng ký và provenance `OFFICIAL/PARTNER_PORTAL`, kể cả khi chưa có research, evidence hoặc commission fact.

API và giao diện tiếp tục hiện link đăng ký an toàn; cùng một hàm phân loại nguồn được dùng cho API và Evidence Pack để tránh kết quả lệch nhau.

Nguồn đăng ký chỉ là metadata truy xuất: nó không mở PPC, không quyết định commission, không loại hoặc dừng dự án/campaign. Chương trình chưa có link tiếp tục hiện cảnh báo thay vì bị ẩn.

Production-copy Pictory có bảy nguồn thật, `collection_errors=[]`, `UNCHANGED`; commission vẫn `CONFLICT`, không tạo evidence PPC và cả bốn quyền quảng cáo vẫn `NOT_CHECKED`.

Kết quả rà Terms luôn hiện đúng toàn bộ URL vừa đọc ở lần hiện tại, kể cả khi nội dung evidence không đổi và hệ thống tái sử dụng một research run cũ.

Terms research ghi dấu SHA-256 của phần nội dung affiliate/PPC/commission trên từng nguồn chính thức để phát hiện nguồn mới, mất hoặc đổi nội dung ở lần rà sau. Hệ thống không lưu toàn bộ trang; thay đổi chỉ tạo cảnh báo và không tự mở PPC.

Nguồn chính thức liên quan đã đọc vẫn được ưu tiên dùng lại, kể cả khi lần đầu chưa trích được evidence hoặc program chưa tồn tại. Nguồn đã reject không quay lại qua lịch sử.

Mọi backup được xác minh lại trên byte hiện tại trước khi mang nhãn an toàn. Backup lịch lỗi vẫn được giữ để chẩn đoán nhưng không được dùng cho Restore hoặc trì hoãn bản thay thế ở heartbeat kế tiếp.

Operations Inbox chỉ tạo một cảnh báo khi thiếu Terms evidence và campaign đang chạy bắt nguồn từ cùng một chương trình. Cảnh báo gốc hiện số lượng/tên campaign, còn Risk & Exposure vẫn giữ từng campaign và spend riêng.

Terms Evidence Center hiện riêng lần automation đã rà và evidence PPC thực sự tìm thấy; một lần rà còn mới không bao giờ được hiểu thành quyền quảng cáo đã xác minh. Operations Inbox vẫn chỉ đếm một quyết định commission cho mỗi chương trình và giữ từng fact để ACCEPT/REJECT riêng.

Các permission proposal `NOT_CHECKED` được gom thành một cảnh báo tự theo dõi và không yêu cầu xác nhận. Chúng không thể mở quyền PPC; dự án/campaign vẫn được giữ nguyên với warning.

Các campaign cùng một chương trình và cùng cảnh báo Terms chỉ chiếm một dòng trong Operations Inbox. Risk & Exposure tiếp tục giữ từng campaign, spend và trạng thái riêng để không mất chi tiết.

Mỗi lần rà fixture/web ghi đúng `duplicate_run` vào audit, nên lịch sử phân biệt lần tạo research run mới với lần kiểm tra lại cùng kết quả.

Extractor commission loại các pricing discount như `SAVE MORE THAN 15%` ngay cả khi chúng nằm sát nội dung affiliate. Với trang Pictory hiện tại, live refresh chỉ giữ 40% one-time và recurring up to 50%; 15% Annual saving không được tạo fact.

Permission proposal tự động từ cùng URL, scope và decision được làm mới tại chỗ khi nguồn chỉ đổi câu chữ. Bằng chứng đã ACCEPTED/REJECTED hoặc nhập tay không bị ghi đè; một decision thật sự khác vẫn tạo proposal riêng để bật cảnh báo `CONFLICT`.

Mỗi permission refresh có audit trước/sau, checked_at mới và xác nhận `permissions_changed=false`. Canonical PPC chỉ đổi qua thao tác review riêng của người vận hành; campaign/project vẫn warning-only.

Commission proposal tự động từ cùng URL, cùng mức và cùng loại cũng được làm mới tại chỗ thay vì nhân bản khi câu chữ nguồn thay đổi. Chỉ proposal do fixture/web tạo mới được refresh; fact đã ACCEPTED hoặc nhập tay không bao giờ bị ghi đè. Mỗi lần refresh có audit trước/sau và vẫn hoàn toàn tách khỏi PPC permission.

Research response tính commission state trên toàn bộ facts còn hiệu lực của chương trình, nên một lần web không tìm thấy nguồn mới không thể che conflict đã tồn tại. Pictory vẫn warning-only và mọi quyền PPC giữ `NOT_CHECKED`.

Heartbeat bảo trì vẫn chạy mỗi 30 phút để nhận CSV và Terms sớm, nhưng Google Ads API có cadence riêng sáu giờ để không đọc lặp cùng dữ liệu và lãng phí quota. Lỗi xác thực giãn 24 giờ và luôn yêu cầu đăng nhập lại; lỗi tạm thời tự thử lại sau sáu giờ.

Thiết lập OAuth thành công tạo một yêu cầu đồng bộ một lần không chứa bí mật, vì vậy lần đọc đầu tiên chạy ngay cả khi một lỗi xác thực cũ còn trong thời gian chờ. Yêu cầu được xóa sau khi đã thử; Runtime hiện rõ mốc API kế tiếp.

Updater và rollback tiếp tục tái tạo hai LaunchAgent từ code của phiên bản vừa cài/khôi phục, rồi mới bootstrap và health-check. Vì vậy thay đổi cadence không thể bị plist cũ che mất.

Live plist và launchctl được xác nhận cùng `StartInterval=1800`. Nếu regeneration lỗi, updater giữ trạng thái rõ “dịch vụ chưa phục hồi” thay vì báo thành công giả.

Maintenance dùng heartbeat 30 phút nên update/reload không thể lùi một lần rà Terms vừa đến hạn thêm gần 6 giờ. Runtime ETA và LaunchAgent dùng cùng cadence mới.

Backup vẫn bị gate 24 giờ, Terms ổn định 24 giờ và lỗi web retry 6 giờ; tăng nhịp chỉ giúp phát hiện đến hạn/file mới sớm hơn. Import vẫn idempotent, lock vẫn chặn chạy chồng và permission/campaign không tự thay đổi.

Sau OAuth, thiết lập Google Ads đổi access token và chạy SearchStream chỉ đọc một ngày cho mọi Customer ID đã lưu. Chỉ khi Google chấp nhận cả OAuth lẫn Developer Token/quyền tài khoản, đủ bốn credential mới được commit vào Keychain.

Preflight không ghi campaign hay database, không gọi mutate và không trả/log access hoặc refresh token. Auth/network/rate-limit failure giữ nguyên Keychain cũ và CSV fallback.

Thiết lập Google Ads tiếp tục commit đủ bốn credential theo một bundle. Nếu ghi lỗi giữa chừng, hệ thống phục hồi bộ cũ; nếu người dùng hủy OAuth, Keychain hoàn toàn không đổi.

Người vận hành chỉ cần cung cấp OAuth Desktop JSON và Developer Token. Client ID/Secret được đọc từ JSON, refresh token được Google tạo, bí mật không đi vào database/UI/log; setup thành công sẽ yêu cầu maintenance kiểm tra API ngay và CSV fallback luôn được giữ.

Restore tiếp tục tạm dừng cả hai LaunchAgent 24/7, xác nhận server thật sự đóng rồi mới chạm SQLite, và luôn nạp lại đúng chế độ cũ sau cả thành công lẫn lỗi.

Nếu database hiện tại không mở được, hệ thống lấy schema kỳ vọng từ migration graph và vẫn có thể chọn backup tương thích. Trước khi thay dữ liệu, raw database cùng WAL/SHM được giữ nguyên byte trong emergency snapshot mà không bị SQLite mở trước.

Backup mới tiếp tục ghi schema thật, integrity và foreign-key status. Restore quét từ mới đến cũ, chỉ chọn bản có SHA hợp lệ, database toàn vẹn và cùng schema; nếu không có bản phù hợp thì dừng mà không thay dữ liệu hiện tại.

Danh sách backup hiện schema database của từng bản, kể cả backup được tạo tự động trước update. Không có backup cũ nào bị xóa bởi thay đổi này.

Collector chỉ tự retry timeout, lỗi mạng, 408/425/429 và 5xx. Các đường dẫn policy đoán sẵn trả 404/410 hoặc bị chặn bởi safety/content validation không còn tạo vòng lặp retry vô hạn.

Lịch Terms vẫn có biên an toàn 5 phút để chu kỳ bảo trì không bị bỏ qua chỉ vì collector ghi heartbeat sau mốc bắt đầu vài mili-giây. Retry là 6 giờ và kết quả ổn định là 24 giờ.

Lỗi truy cập Terms tạm thời chuyển sang `RETRY_REQUIRED` và tự thử lại mà không yêu cầu người dùng. Chỉ khi truy cập được nhưng không có evidence rõ ràng mới dùng `MANUAL_INPUT_REQUIRED`.

Command Center phân biệt mốc Terms đến hạn với lần rà thực tế ở chu kỳ bảo trì kế tiếp. Lịch này chỉ để quan sát: Terms vẫn là cảnh báo, không tự mở PPC permission, không loại campaign/project và không tự quyết commission facts.

Google Ads CSV vẫn chỉ được coi là hoàn tất khi không còn `unmapped_rows`. File đọc thành công nhưng còn campaign chưa ghép sẽ tự retry context; nếu program từ `program_domain` xuất hiện sau, hệ thống tạo mapping mà không nhân spend/stats.

Nếu live source không truy cập được hoặc không còn nội dung rõ ràng, hệ thống lưu lần thử thật dưới dạng `MANUAL_INPUT_REQUIRED` và giữ Pictory/campaign trong hệ thống với cảnh báo.

Nếu lần rà mới chỉ còn tìm được commission nhưng không revalidate đủ các scope PPC đã chấp nhận, `TERMS_OK` tự hạ thành `WARNING_TERMS_UNVERIFIED`. Commission không thể che việc mất nguồn permission; canonical permission và campaign/project vẫn không bị tự sửa hoặc loại.

Cách chọn lần rà mới nhất thống nhất của 0.2.24 vẫn giữ nguyên giữa Maintenance, Runtime, Inbox và Terms gate.

Guard source loss của 0.2.23 vẫn giữ nguyên: nếu lần rà thực sự mới nhất không còn nguồn rõ ràng và mới hơn accepted/review event, trạng thái xanh tự hạ thành `WARNING_TERMS_UNVERIFIED`; permission không đổi và campaign/project vẫn được giữ.

Guard xung đột của 0.2.22 vẫn hoạt động: official proposal mới trái với accepted evidence lập tức tạo `WARNING_TERMS_CONFLICT`; loại proposal sai sẽ khôi phục trạng thái từ evidence đã chấp nhận.

Bảo trì 24/7 cũng rà campaign cũ chưa liên kết và tự ghép nếu tên chứa đúng một merchant domain với ranh giới đầy đủ. Command Center hiện ngay số vừa ghép, chưa ghép và mapping cũ được giữ.

Khi đủ credential trong Keychain, bảo trì 24/7 dùng Google Ads API v25 `SearchStream` với truy vấn chỉ `SELECT` để đọc bảy ngày gần nhất đến hôm qua, đối chiếu từng campaign/ngày với sổ CSV rồi mới cập nhật dòng canonical. Lỗi 429/5xx/mạng được thử lại tối đa ba lần theo nhịp 1–2 giây; hết lượt vẫn lỗi thì lưu SyncRun an toàn và tự thử lại ở chu kỳ sáu giờ kế tiếp. Chỉ lỗi xác thực mới yêu cầu người vận hành đăng nhập lại.

Mở `SETUP-GOOGLE-ADS-READ-ONLY.command` khi đã có OAuth Desktop JSON và Developer Token. Lệnh này dùng loopback `127.0.0.1` + PKCE rồi lưu credential trực tiếp trong macOS Keychain; giá trị bí mật không vào database, UI hoặc log.

Để bật chế độ này một lần, mở `ENABLE-AFI-OS-24-7.command`. Có thể xem trạng thái bằng `STATUS-AFI-OS-24-7.command` hoặc tắt tự khởi động bằng `DISABLE-AFI-OS-24-7.command`; các thao tác này không xóa dữ liệu hay backup.

Với domain ngoài fixture, hệ thống thử homepage và tối đa bảy URL affiliate/partner/terms chính thức. Nó chỉ lưu các đoạn nhận diện được thành `PROPOSED`, chống lặp theo hash và không sửa canonical permission. Nếu không thấy câu PPC rõ ràng, kết quả là `MANUAL_INPUT_REQUIRED` và permission tiếp tục `NOT_CHECKED`.

Google Ads CSV Import đọc trực tiếp báo cáo tiếng Việt hoặc tiếng Anh, tự tìm hàng tiêu đề sau phần mô tả báo cáo, bỏ các dòng “Tổng số”, chuẩn hóa trạng thái/kênh và chống trùng giữa các tên nguồn Google Ads CSV. Khi hệ thống chỉ có một tài khoản Ads, Customer ID được điền lại tự động trên giao diện.

Finance & Reconciliation dùng VND làm tiền tệ cơ sở mặc định. Dữ liệu cùng tiền tệ được chuẩn hóa 1:1; dữ liệu khác tiền tệ vẫn giữ nguyên và được báo thiếu tỷ giá cho tới khi một đề xuất có URL nguồn, confidence tối thiểu 0,8 và được người vận hành chấp nhận. Giao dịch trùng hoặc xung đột đi vào hàng đợi thay vì ghi đè số tiền đã lưu.

## macOS có Python 3.9

Bản Runtime v2 tự tải Python 3.11 vào chính thư mục AFI-OS bằng `uv`; không thay đổi Python hệ thống của macOS. Khi môi trường cũ bị lỗi hoặc thư mục đã được di chuyển, mở `FIX-PYTHON.command` một lần rồi dùng `START-AFI-OS.command` như bình thường.
