# DataImpulse IP Finder

Project mandiri untuk Python 3.10+, terpisah dari versi Oxylabs.
Mencoba port sticky secara berurutan dalam batch paralel untuk menemukan
satu IPv4 dengan prefix tertentu. Tidak menggunakan sessid atau username Oxylabs.

## Struktur

```text
dataimpulse-ip-finder/
  dataimpulse_finder/
    __init__.py
    __main__.py       # Terminal, Enter/Ctrl+C, logging
    config.py         # Settings, .env, validasi
    client.py         # Format DataImpulse, HTTP, parsing
    service.py        # Pencarian port dan thread pool
  tests/test_finder.py
  .env.example
  .gitignore
  requirements.txt
  README.md
```

## Menjalankan — Windows PowerShell

```powershell
cd dataimpulse-ip-finder
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
.\.venv\Scripts\python.exe -m dataimpulse_finder
```

Isi PROXY_USERNAME dengan login dasar DataImpulse, tanpa `__cr...`.
Isi PROXY_PASSWORD dengan password valid yang baru. Kredensial asli tidak
ada di ZIP. Ganti password yang telah dibagikan di percakapan.

Linux/macOS:

```bash
cd dataimpulse-ip-finder
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env, kemudian:
.venv/bin/python -m dataimpulse_finder
```

Enter atau Ctrl+C menghentikan penjadwalan; request aktif ditunggu sampai selesai.
Non-interactive stdin tidak mengaktifkan monitor Enter. Exit code 0: pencarian
selesai/tidak cocok/dibatalkan; 1: runtime error; 2: konfigurasi tidak valid.
Environment proses mengalahkan .env; lokasi .env adalah root project ini.

## Pilihan targeting

| PROXY_MODE | COUNTRY | CITY | ASN | Suffix username |
| --- | --- | --- | --- | --- |
| combined | az | baku | 31721 | __cr.az;city.baku;asn.31721 |
| location | az | baku | diabaikan | __cr.az;city.baku |
| location | us | kosong | diabaikan | __cr.us |
| asn | az | diabaikan | 31721 | __cr.az;asn.31721 |

Mode `combined` mendukung kombinasi kode lama; isi ASN=31721 untuk mengaktifkan ASN tersebut. COUNTRY tetap wajib pada
mode ASN: DataImpulse memerlukan negara untuk targeting ASN/kota. CITY opsional
pada location/combined; tulis `CITY=` untuk menghapus kota default baku.
Pakai nama kota yang didukung dashboard; program tidak menebak alias kota.

Konfigurasi awal (.env.example juga memuat komentar):

```dotenv
PROXY_USERNAME=your_dataimpulse_login
PROXY_PASSWORD=replace_with_new_password
PROXY_HOST=gw.dataimpulse.com
PROXY_MODE=combined
COUNTRY=az
CITY=baku
ASN=
START_PORT=10000
END_PORT=20000
MAX_WORKERS=2
TARGET_IP_PREFIX=185.30.88.
IP_INFO_URL=https://ipinfo.io/json
EXECUTION_DURATION=200
REQUEST_TIMEOUT=5
BATCH_DELAY=0.25
```

Program berhenti jika match ditemukan, dibatalkan, durasi habis, atau END_PORT
selesai dicoba. Setiap port dicoba sekali per pencarian. Batas port inklusif;
port di luar rentang sticky 10000–20000 ditolak. Targeting proxy tetap berbeda
dari filter TARGET_IP_PREFIX: kombinasi filter tidak menjamin IP prefix tersedia.

## Review dan perubahan

| Masalah lama | Penyebab | Perbaikan |
| --- | --- | --- |
| Rahasia tersimpan di source | Username/password hardcode | .env, placeholder, repr rahasia, log tanpa teks exception sensitif |
| Port terus naik tanpa batas | Tidak ada END_PORT | Rentang tervalidasi, berhenti saat habis |
| Overhead pool | Pool dibuat setiap batch | Satu pool per pencarian |
| Pembatalan sulit ditangani | Event global dan input blocking | Event per pencarian, polling input, pending dibatalkan |
| JSON/IP rusak bisa gagal | Validasi payload tidak lengkap | Status HTTP, tipe JSON, dan IPv4 diperiksa |
| Request detail berulang | org diminta lagi pada endpoint kedua | Gunakan city/org respons pertama |
| Sulit dipakai API | CLI bercampur logic | Pisah config, client, service, CLI |

Perubahan perilaku disengaja: request detail kedua dihapus. ISP sekarang berasal
dari respons awal; jika tidak tersedia hasil tetap dikembalikan dengan `N/A`.
Match tidak lagi hilang akibat kegagalan request detail kedua. IP_CHECK_URL,
IP_INFO_URL dan fungsi fetch_ip_details dihapus karena tidak diperlukan lagi.
Set deduplikasi dihapus karena program hanya mengembalikan satu hasil.
Ditambahkan jeda batch 0,25 detik yang dapat dibatalkan/diatur, tanpa retry otomatis.

Return tetap list berisi satu tuple `(ip, port, city, isp)` atau None.
Implementasi menggunakan NamedTuple agar tuple tetap dapat di-unpack dan
memiliki atribut bernama. Signature service berubah menjadi
`find_matching_ip(settings, stop_event=None)` agar siap diimpor oleh API.

Session HTTP terisolasi per task, ditutup bersama Response dengan `with`.
TLS verification aktif. Redirect, system proxy, dan .netrc tidak diwarisi.
Konfigurasi URL dikendalikan operator, bukan input bebas pengguna website.
Deadline memakai monotonic; tidak menerima hasil yang selesai melewati deadline.

## Batas waktu

EXECUTION_DURATION membatasi penjadwalan/penerimaan hasil, bukan batas keras
waktu keseluruhan. Request yang sedang aktif tidak dapat dibatalkan paksa oleh
thread pool; shutdown menunggu resource tertutup. Timeout Requests adalah
connect/read timeout, bukan total wall-clock: DNS atau respons bertahap dapat
memperpanjang waktu berhenti.

## Dependencies dan tes

requirements.txt:

```text
requests>=2.32.5,<3
python-dotenv>=1.0.1,<2
```

Tambahan hanya python-dotenv. Tes memakai unittest bawaan Python:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Pengujian memakai mock, tanpa koneksi/biaya proxy: format setiap mode, pemetaan
.env, encoding rahasia, payload rusak, error HTTP, tuple hasil, port berurutan,
batas port, pembatalan dan deadline. Akun dan jaringan provider belum diuji.

## Integrasi website/API

```python
from threading import Event
from dataimpulse_finder import Settings, find_matching_ip

stop = Event()
results = find_matching_ip(Settings.from_env(), stop)
payload = [item._asdict() for item in results] if results else []
```

Jalankan sebagai background job; sediakan job ID, status, dan cancel. Jangan
memanggil fungsi sinkron langsung dari endpoint async. Batasi jumlah job dan
worker total; untuk server multiproses, status/cancel perlu antrean atau
penyimpanan bersama. Kredensial harus tetap di server; autentikasi endpoint.
Flask/FastAPI belum ditambahkan karena belum ada endpoint yang diminta.

## Referensi provider

- [Format parameter](https://docs.dataimpulse.com/proxies/parameters): delimiter __, key.value dan pemisah ;.
- [Sticky connections](https://docs.dataimpulse.com/proxies/types-of-connections.md): port 10000–20000.
- [City targeting](https://docs.dataimpulse.com/proxies/parameters/city.md): country wajib untuk kota dan ASN.
- [Requests timeouts](https://requests.readthedocs.io/en/latest/user/advanced/#timeouts).

## Revisi ASN opsional

ASN kosong (`ASN=`), hanya spasi, atau variabel ASN tidak ada berarti tanpa
filter ASN. Default Python `asn=None`; tidak ada fallback ASN tersembunyi.
Isi `ASN=31721` untuk memakai ASN pada mode combined/asn.
Mode location tetap mengabaikan ASN. Nilai 0, negatif, atau non-angka pada
mode combined/asn tetap ditolak karena bukan ASN valid.

```dotenv
PROXY_MODE=combined
COUNTRY=az
CITY=baku
ASN=
```

Contoh di atas mengirim `__cr.az;city.baku`. Jika CITY juga kosong, hanya
`__cr.az` yang dikirim. Mode asn dengan ASN kosong juga mengirim negara saja
(CITY tetap diabaikan pada mode asn). COUNTRY tetap wajib.
.env.example kini mengosongkan ASN secara default.
