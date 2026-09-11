# RAT-HAILAMDEV

> **Mục đích học tập và phòng thủ.**
>
> Dự án này được xây dựng để nghiên cứu lập trình socket, TLS, giao thức JSON
> và các rủi ro khi phát triển công cụ quản trị từ xa. Chỉ chạy trên máy cá nhân,
> máy ảo hoặc hệ thống mà bạn sở hữu/được cấp phép kiểm thử. Không sử dụng để
> truy cập trái phép, thu thập dữ liệu, theo dõi người dùng hoặc phát tán mã độc.

## Giới thiệu

RAT-HAILAMDEV là mô hình client/server tối giản viết bằng Python. Kênh liên lạc
được bọc bằng TLS và dữ liệu trao đổi theo từng dòng JSON. Phiên bản hiện tại
phục vụ mục đích học tập, chưa nên sử dụng trong môi trường production.

Các chức năng đang có:

- Khởi động server lắng nghe kết nối client.
- Kết nối client qua TLS.
- Thu thập thông tin hệ điều hành và máy chủ (`sysinfo`).
- Liệt kê thư mục (`ls`).
- Thực thi lệnh từ xa (`exec`).
- Download/upload tệp.
- Ghi lại kết quả phiên vào file JSON khi server dừng bằng `Ctrl+C`.

## Yêu cầu

- Python 3.9 trở lên.
- OpenSSL để tạo chứng chỉ thử nghiệm.
- Chỉ dùng trong mạng lab hoặc trên `localhost`.

Không có dependency bắt buộc cho các chức năng cơ bản. Tính năng screenshot
trong mã nguồn hiện chưa hoàn thiện và không được xem là chức năng ổn định.

## Cài đặt

```bash
git clone <URL_REPOSITORY>
cd RAT-HAILAMDEV
python3 --version
```

Tạo chứng chỉ tự ký cho môi trường lab:

```bash
openssl req -x509 -newkey rsa:2048 \
  -keyout server.key \
  -out server.crt \
  -days 365 -nodes \
  -subj "/CN=localhost"
```

Không commit `server.key` lên Git. Nên thêm các file sinh ra vào `.gitignore`.

## Chạy thử trên cùng một máy

Mở terminal thứ nhất để chạy server:

```bash
python3 rat.py server 4444
```

Mở terminal thứ hai để chạy client:

```bash
python3 rat.py client 127.0.0.1 4444
```

Một số lệnh trong giao diện client:

```text
sysinfo
ls
ls /tmp
exec whoami
download /path/to/file
upload /path/to/file <base64-data>
exit
```

Khi dừng server bằng `Ctrl+C`, các phiên được ghi vào `rat_sessions.json`.

## Giao thức JSON tối giản

Mỗi request và response kết thúc bằng ký tự xuống dòng (`\\n`). Ví dụ request:

```json
{"action":"sysinfo"}
```

```json
{"action":"exec","cmd":"whoami"}
```

Các action được xử lý trong mã nguồn gồm `exec`, `sysinfo`, `ls`, `download`,
`upload` và `kill`.

## Cảnh báo an toàn

Đây là mã nguồn minh họa, chưa đáp ứng yêu cầu của một hệ thống quản trị từ xa
an toàn:

- Server mặc định bind trên `0.0.0.0`, có thể mở dịch vụ ra toàn bộ interface.
- Chưa có xác thực client hoặc cơ chế phân quyền người dùng.
- `exec` sử dụng `shell=True`, có nguy cơ command injection.
- Đường dẫn đọc/ghi tệp chưa được sandbox hoặc kiểm soát quyền.
- Chứng chỉ tự ký chỉ phù hợp cho lab; không dùng làm PKI production.
- Chưa có cơ chế chống replay, rate limit, audit bất biến hoặc quản lý secret.
- Một số chức năng được mô tả trong docstring chưa hoàn thiện đầy đủ trong CLI.

Để nghiên cứu theo hướng phòng thủ, nên chạy trong máy ảo cô lập, giới hạn
`host` về `127.0.0.1`, dùng dữ liệu giả và xóa chứng chỉ sau khi kết thúc lab.

## Hướng phát triển an toàn

- Thêm xác thực hai chiều bằng client certificate hoặc token ngắn hạn.
- Loại bỏ `shell=True`, thay bằng allowlist các lệnh được phép.
- Giới hạn thư mục thao tác bằng sandbox và kiểm tra path traversal.
- Bind mặc định vào localhost và thêm cấu hình firewall rõ ràng.
- Bổ sung test cho giao thức, TLS, timeout và xử lý lỗi.
- Tách phần transport, protocol và business logic để dễ audit.

## Tác giả và nguồn

**Nguyen Xuan Hai**

- LinkedIn: [linkedin.com/in/xuanhai0913](https://www.linkedin.com/in/xuanhai0913/)
- Facebook: [facebook.com/nguyenhai0913](https://www.facebook.com/nguyenhai0913)

## License

Dự án được phát hành theo [MIT License](LICENSE).
