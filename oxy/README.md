# Proxy IP Finder — refactor

Python 3.10+. Mencoba session proxy secara paralel hingga menemukan satu
IPv4 yang cocok dengan prefix, dihentikan pengguna, atau durasi habis.
Hasil service tetap `list[Match] | None`, dengan key `ip`, `session`,
`city`, dan `isp`. Semua kode lengkap ada dalam project ini.

## Struktur

```text
proxy-ip-finder/
  proxy_finder/
    __init__.py       # Public interface
    __main__.py       # CLI, logging, Enter/Ctrl+C
    config.py         # .env dan validasi
    client.py         # HTTP, proxy, parsing
    service.py        # Thread pool dan pencarian
  tests/test_finder.py
  tests/test_modes.py
  .env.example
  .gitignore
  requirements.txt
  README.md
```

## Menjalankan di Windows PowerShell

```powershell
cd proxy-ip-finder
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
.\.venv\Scripts\python.exe -m proxy_finder
```

Isi PROXY_USERNAME dengan username dasar provider, termasuk `customer-`,
tanpa suffix sesi; isi PROXY_PASSWORD dengan password baru yang valid.
Tidak ada kredensial asli dalam project. Ganti password yang pernah dibagikan.
Tidak perlu mengaktifkan virtual environment jika menjalankan path di atas.

Linux/macOS:

```bash
cd proxy-ip-finder
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env dengan editor pilihan, kemudian:
.venv/bin/python -m proxy_finder
```

Enter pada terminal interaktif atau Ctrl+C menghentikan penjadwalan.
Saat stdin bukan terminal, monitor Enter tidak dibuat. Exit code: 0 untuk
selesai/tidak ditemukan/dibatalkan, 1 untuk error runtime, 2 untuk konfigurasi.
Environment proses mengalahkan nilai .env. File .env dibaca dari root project.

## Masalah, penyebab, dan perbaikan

| Masalah | Penyebab lama | Perbaikan |
| --- | --- | --- |
| Tetap menunggu Enter setelah match | `input_thread.join()` menunggu `input()` | Polling terminal yang memeriksa Event dan join setelah stop |
| Overhead thread | Pool baru tiap batch | Satu pool per pencarian, pending dibatalkan, worker aktif ditunggu |
| Stop terlambat | `as_completed` menunggu request selesai | Polling future 0,1 detik dan Event per pencarian |
| Crash JSON/IP | Tidak memeriksa status/payload | Validasi HTTP, JSON object, field IP, IPv4 |
| Kredensial bocor | Hardcode dan exception dapat memuat URL proxy | .env, repr rahasia, log jenis error saja, URL encoding |
| Request detail ganda | Endpoint IP diminta lagi untuk field yang sama | Gunakan city/org dari response awal; satu request per session |
| Konfigurasi salah baru gagal di request | Tidak ada validasi | Validasi port, worker, durasi, prefix, URL, kredensial |
| Sulit dipakai API | Event global dan input bercampur logic | Service menerima Settings dan Event sendiri |
| Loop error terlalu cepat | Tidak ada jeda batch | Jeda batch 0,25 detik yang bisa diatur dan dibatalkan |

Gunakan satu Session HTTP per task sehingga tidak dibagi lintas thread.
Session dan Response ditutup dengan context manager. SSL verification tetap
aktif; redirect tidak diikuti. Proxy dari environment dan .netrc tidak diwarisi.
Hostname/URL konfigurasi diasumsikan dikendalikan operator, bukan input API publik.

## Perilaku yang dipertahankan dan perubahan yang disengaja

- Prefix default `88.230.184.`, session `t01q1` dan seterusnya,
  country `tr` untuk mode location, sesi 30 menit, 25 worker, durasi 200 detik, timeout 5 detik.
- Match masih menggunakan `startswith`, bukan filter CIDR, ASN, atau kota.
- Jika beberapa hasil selesai bersamaan, salah satu match pertama dipilih;
  urutan penyelesaian thread memang tidak deterministik pada kode lama.
- Mode baru `asn` mengirim parameter ASN saja; mode `location` mengirim
  negara dan kota opsional. Parameter mode lain tidak ikut username proxy.
  Konstanta URL tidak terpakai dan deduplikasi satu hasil tetap dihapus.
- Request detail kedua dihapus. City/ISP kini berasal dari snapshot respons
  pertama; match tidak hilang hanya karena request detail berikutnya gagal.
  Field opsional kosong menjadi `N/A`.
- START_PORT diganti START_SESSION karena nilainya nomor sesi, bukan port.
- Setiap pencarian selesai menandai Event sebagai stopped. Untuk pencarian
  berikutnya, gunakan Event baru atau biarkan service membuatnya.
- Tidak ada retry otomatis agar kegagalan tidak memperbanyak request/biaya.

## Batas waktu dan penghentian

`EXECUTION_DURATION` membatasi penjadwalan dan penerimaan hasil, bukan batas
keras total proses. Request yang sudah aktif tidak bisa dipaksa dibatalkan oleh
ThreadPoolExecutor. Service menunggu request aktif selesai agar resource tertutup.
Timeout Requests adalah timeout connect/read, bukan total wall-clock; DNS,
beberapa koneksi, atau server yang terus meneteskan byte dapat memperpanjang
waktu berhenti. Jangan menganggap program pasti keluar persis pada detik ke-200.
Lihat [dokumentasi Requests](https://requests.readthedocs.io/en/latest/user/advanced/#timeouts).

## Dependencies

Isi requirements.txt:

```text
requests>=2.32.5,<3
python-dotenv>=1.0.1,<2
```

Tambahan dibanding kode lama hanya `python-dotenv`; lainnya standard library.
Versi dependency belum dikunci ke satu versi; untuk deployment kunci versi setelah
instalasi dan pengujian di environment target.

## Pengujian tanpa jaringan

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Atau Linux: `.venv/bin/python -m unittest discover -s tests -v`.
Tes mengganti HTTP dengan mock: match, payload rusak, HTTP/JSON gagal,
encoding kredensial, pembatalan, deadline, ID sesi unik, dan konfigurasi.
Tes tidak memeriksa akun proxy atau ketersediaan IPinfo secara langsung.

## Integrasi Flask/FastAPI berikutnya

Service dapat diimpor tanpa mengaktifkan input terminal atau logging global:

```python
from threading import Event
from proxy_finder import Settings, find_matching_ip

settings = Settings.from_env()
stop_event = Event()
results = find_matching_ip(settings, stop_event)
```

Untuk website, jalankan pencarian sebagai job background dan berikan job ID,
endpoint status, serta endpoint cancel yang memanggil Event milik job itu.
Jangan memanggil service sinkron ini langsung dalam endpoint `async def` karena
akan memblokir event loop. Batasi job dan total worker lintas pengguna agar
25 worker per job tidak berkembang tanpa batas. Mulai dengan satu proses;
bila memakai beberapa proses server, gunakan penyimpanan status/antrean bersama.
Simpan kredensial di server, autentikasi endpoint, dan jangan menerima proxy URL
atau endpoint HTTP bebas dari pengguna. Tambahkan rate-limit/backoff khusus 429
sesuai batas provider jika diperlukan. Flask/FastAPI belum menjadi dependency
karena belum ada kebutuhan endpoint konkret.

## Revisi: pilihan ASN atau negara/kota

Atur di `.env`, bukan dengan mengomentari kode Python:

| Pilihan | PROXY_MODE | ASN | COUNTRY | CITY |
| --- | --- | --- | --- | --- |
| ASN saja | asn | 9121 | diabaikan | diabaikan |
| Negara saja | location | diabaikan | tr | kosong |
| Negara + kota | location | diabaikan | tr | sakarya |

Contoh ASN:

```dotenv
PROXY_MODE=asn
ASN=9121
COUNTRY=tr
CITY=
```

Contoh negara + kota:

```dotenv
PROXY_MODE=location
COUNTRY=tr
CITY=sakarya
```

Gunakan `CITY=` untuk negara saja. Country menggunakan nama variabel COUNTRY
(parameter proxy `cc`), bukan CR. Field Python adalah `settings.asn`, huruf kecil.
`from_env()` sudah menghubungkan PROXY_MODE, ASN, COUNTRY, dan CITY ke Settings.
Spasi tepi dan huruf kapital pada mode/country/city di .env dinormalisasi.
CITY harus slug provider (huruf kecil, angka, underscore); nama berspasi tidak
tebak-dikonversi. Cocokkan slug dengan generator username dashboard provider.
Sintaks kota belum diverifikasi langsung dengan akun provider.

.env.example memilih ASN agar sesuai revisi ini; default Settings jika
PROXY_MODE tidak ditentukan tetap location untuk kompatibilitas.
ASN dibaca dan divalidasi hanya dalam mode asn. COUNTRY/CITY divalidasi hanya
dalam mode location. ASN default 9121 digunakan bila mode asn tanpa variabel ASN.
Filter TARGET_IP_PREFIX tetap aktif pada kedua mode: targeting proxy tidak
menjamin prefix tersedia. Mode memilih jaringan/lokasi proxy, bukan mengganti
kondisi kecocokan IP program. Tidak ada dependency tambahan untuk revisi ini.
