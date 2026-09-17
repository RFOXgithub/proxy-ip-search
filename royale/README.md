# IPRoyal IP Finder

Project mandiri Python 3.10+, terpisah dari Oxylabs dan DataImpulse.
Mencari satu IPv4 berdasarkan prefix melalui sesi SOCKS5. Parameter lokasi dan
sesi disusun pada password, bukan username.

## Struktur

```text
iproyal-ip-finder/
  iproyal_finder/
    __init__.py       # Interface publik
    __main__.py       # CLI, logging, Enter/Ctrl+C
    config.py         # .env dan validasi
    client.py         # SOCKS5, password, parsing
    service.py        # ID sesi dan thread pool
  tests/
    test_finder.py
    test_proxy.py
  .env.example
  .gitignore
  requirements.txt
  README.md
```

## Windows PowerShell

```powershell
cd iproyal-ip-finder
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
.\.venv\Scripts\python.exe -m iproyal_finder
```

Isi username dan password DASAR IPRoyal, tanpa parameter _country/_session.
Ganti password yang telah dibagikan. ZIP tidak memuat kredensial asli.

Linux/macOS:

```bash
cd iproyal-ip-finder
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env, kemudian:
.venv/bin/python -m iproyal_finder
```

Enter/Ctrl+C menghentikan penjadwalan. Monitor Enter hanya aktif pada terminal.
Exit code 0: selesai/tidak cocok/dibatalkan; 1: runtime error; 2: konfigurasi.
.env dibaca dari root project; variabel environment proses lebih diprioritaskan.

## .env.example

```dotenv
PROXY_USERNAME=your_iproyal_username
PROXY_PASSWORD=replace_with_new_password
PROXY_HOST=geo.iproyal.com
PROXY_PORT=32325
PROXY_SCHEME=socks5
COUNTRY=az
CITY=baku
SESSION_PREFIX=m18m
SESSION_MINUTES=30
MAX_WORKERS=25
TARGET_IP_PREFIX=185.30.88.
IP_INFO_URL=https://ipinfo.io/json
EXECUTION_DURATION=200
REQUEST_TIMEOUT=5
BATCH_DELAY=0.25
```

CITY opsional: tulis `CITY=` untuk negara saja. COUNTRY harus dua huruf.
Nama kota harus sesuai dashboard; underscore ditolak agar tidak menyisipkan
parameter lain. Format password contoh (rahasia palsu):

```text
fake_country-az_city-baku_session-m18mabcd_lifetime-30m
fake_country-az_session-m18mabcd_lifetime-30m
```

SESSION_PREFIX 0–4 karakter alfanumerik; suffix acak melengkapi panjang ID menjadi
8 karakter. Collision dicegah selama satu pencarian, bukan dijamin unik global.
Ubah prefix antar run jika ingin mengurangi peluang memakai sesi run sebelumnya.
START_PORT/START_SESSION dihapus karena port tetap dan ID tidak lagi counter.
SESSION_MINUTES menerima 1–10080 menit (maksimal 7 hari).

socks5 memakai DNS lokal seperti kode lama; socks5h memakai DNS melalui proxy.
Port default 32325 mengikuti contoh SOCKS5 resmi. Sesuaikan jika dashboard akun
memberi endpoint SOCKS yang berbeda. ASN dan PROXY_MODE tidak dibaca project ini.
ASN=64466 lama tidak dipakai. Dokumentasi lokasi yang diperiksa menjelaskan
ISP berdasarkan nama, bukan parameter ASN numerik; refactor tidak menebak
format ASN. TARGET_IP_PREFIX tetap menjadi filter hasil pencarian.

## Review: masalah, penyebab, perbaikan

| Masalah | Penyebab | Perbaikan |
| --- | --- | --- |
| SOCKS gagal | Port HTTP 12321 dipakai untuk SOCKS | Default 32325 sesuai contoh resmi |
| Dependensi SOCKS hilang | requests biasa tidak membawa PySocks | Gunakan requests[socks] |
| ID sesi tidak sesuai format | Prefix + counter panjangnya berubah | ID alfanumerik acak 8 karakter |
| Tetap menunggu Enter | input blocking di-join | Polling terminal dan Event |
| Overhead thread | Pool baru setiap batch | Satu pool per pencarian |
| JSON/IP rusak | Status dan payload belum divalidasi | Validasi HTTP, JSON object, IPv4 |
| Rahasia dalam kode/log | Hardcode, exception mentah | .env, repr aman, encoding, log jenis error |
| Request ganda | Detail city/org diminta ulang | Ambil dari response awal |

Request detail kedua, URL tidak terpakai, dan set deduplikasi satu hasil dihapus.
City/ISP kini berasal dari snapshot pertama; jika kosong menjadi N/A. Match tidak
hilang akibat request detail berikutnya gagal. Format return tetap list satu
dict dengan key ip, session, city, isp atau None. Hasil concurrent bersamaan
memiliki urutan tidak deterministik seperti kode lama.

Session per task dan Response ditutup memakai context manager. TLS verification
aktif; redirect tidak diikuti; system proxy dan .netrc tidak diwarisi. Teks error
yang mungkin berisi password tidak dicetak. Jeda batch 0,25 detik dapat diubah
atau dibatalkan. Tidak ada retry otomatis.

Deadline monotonic menghentikan penjadwalan/penerimaan hasil; request aktif
tetap ditunggu hingga selesai untuk menutup resource. EXECUTION_DURATION bukan
batas keras waktu keseluruhan. Timeout Requests adalah connect/read timeout,
bukan total wall-clock; DNS atau respons bertahap dapat memperpanjang shutdown.
Event disetel saat service selesai; gunakan Event baru pada pencarian selanjutnya.

## Dependencies dan tes

requirements.txt:

```text
requests[socks]>=2.32.5,<3
python-dotenv>=1.0.1,<2
```

requests[socks] memasang PySocks. Selain itu memakai standard library.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

16 tes berhasil tanpa jaringan: password, kota opsional, .env, encoding,
dependensi SOCKS, ID sesi/collision, match, JSON/HTTP rusak, pembatalan,
deadline, dan konfigurasi. Akun proxy belum diuji langsung.

## Integrasi website/API

```python
from threading import Event
from iproyal_finder import Settings, find_matching_ip

stop = Event()
results = find_matching_ip(Settings.from_env(), stop)
```

Jalankan sebagai background job dengan job ID, status, dan endpoint cancel.
Jangan memanggil service sinkron langsung dari endpoint async. Batasi jumlah job
serta total worker. Untuk server multiproses, gunakan antrean/status bersama.
Kredensial tetap di server; autentikasi endpoint; URL konfigurasi hanya dikelola
operator, bukan input bebas pengguna. Flask/FastAPI belum ditambahkan.

## Referensi

- [IPRoyal location](https://docs.iproyal.com/proxies/residential/proxy/location.md): parameter country/city dan ISP.
- [IPRoyal rotation](https://docs.iproyal.com/proxies/residential/proxy/rotation.md): sesi 8 karakter dan lifetime.
- [IPRoyal requests](https://docs.iproyal.com/proxies/residential/proxy/making-requests.md): port SOCKS5 32325.
- [Requests](https://requests.readthedocs.io/en/latest/user/advanced/): Session, timeout, SOCKS.
