# Proxy IP Finder Dashboard

Dashboard terpadu untuk DataImpulse, Oxylabs, dan IPRoyal. UI dan API lokal tetap
dapat dijalankan dengan:

```powershell
python -m pip install -r requirements.txt
python run_dashboard.py
```

Buka <http://127.0.0.1:8765>.

## Arsitektur deployment

Backend dashboard memakai `ThreadingHTTPServer`, background thread, dan penyimpanan
job di memori. Karena Vercel Functions stateless dan prosesnya dapat dihentikan
setelah respons selesai, backend tidak cocok dijalankan native di Vercel.

```text
Browser -> Vercel (static UI + same-origin API proxy)
        -> persistent Python web service (dashboard + finder jobs)
```

Business logic finder tidak dipindah atau diubah. `vercel.json` menyajikan UI yang
sama, dan `api/proxy.py` meneruskan route `/api/*` ke backend persisten.

## Environment variables

Jangan commit file `.env`. Untuk lokal, `.env` lama di masing-masing folder masih
didukung. Pada backend production gunakan nama berawalan provider:

| Variable | Wajib | Lokasi |
|---|---:|---|
| `IMPULSE_PROXY_USERNAME` | Ya untuk DataImpulse | Backend |
| `IMPULSE_PROXY_PASSWORD` | Ya untuk DataImpulse | Backend |
| `OXY_PROXY_USERNAME` | Ya untuk Oxylabs | Backend |
| `OXY_PROXY_PASSWORD` | Ya untuk Oxylabs | Backend |
| `ROYALE_PROXY_USERNAME` | Ya untuk IPRoyal | Backend |
| `ROYALE_PROXY_PASSWORD` | Ya untuk IPRoyal | Backend |
| `HOST=0.0.0.0` | Ya | Backend |
| `PORT` | Biasanya otomatis | Backend |
| `BACKEND_URL` | Ya | Vercel |

Semua setting finder dapat dioverride dengan pola yang sama, misalnya
`OXY_COUNTRY`, `ROYALE_CITY`, `IMPULSE_MAX_WORKERS`, atau
`OXY_EXECUTION_DURATION`. Lihat `.env.example` dan contoh provider untuk setting
lain. `BACKEND_URL` harus origin HTTPS tanpa slash akhir, misalnya
`https://ipsearch-backend.onrender.com`.

> Aplikasi publik menggunakan kuota proxy milik akun backend. Gunakan akun/limit
> khusus demo dan pantau pemakaian agar credential utama tidak disalahgunakan.
> Credential tidak pernah dikirim kembali ke browser.

## Deploy backend Python (Render)

Repository menyertakan `render.yaml` dan `Procfile`.

1. Push repository ke GitHub.
2. Di Render pilih **New > Blueprint**, hubungkan repository, lalu terapkan
   `render.yaml`.
3. Tambahkan credential provider di pengaturan Environment service.
4. Tunggu deploy, lalu buka `https://<backend>/healthz`. Respons yang benar adalah
   `{"status":"ok"}`.
5. Salin origin HTTPS backend tersebut untuk `BACKEND_URL` di Vercel.

Host Python persisten lain dapat dipakai dengan build command
`pip install -r requirements.txt`, start command `python run_dashboard.py`, dan
`HOST=0.0.0.0`.

## Deploy frontend ke Vercel

1. Di Vercel pilih **Add New > Project** lalu import repository GitHub ini.
2. Gunakan root repository sebagai **Root Directory**. `vercel.json` menetapkan
   framework `Other` dan output statis `dashboard/static`; build command khusus
   tidak diperlukan.
3. Tambahkan `BACKEND_URL` untuk Production (dan Preview bila diperlukan).
4. Klik **Deploy**. Setelah mengubah environment variable, lakukan redeploy.
5. Buka URL root, misalnya `https://nama-project.vercel.app/`.

Route publik:

- `/` — dashboard portfolio
- `/api/methods` — pemeriksaan koneksi frontend ke backend
- backend `/healthz` — health check backend langsung

## Logs dan diagnosis

- Vercel: project > **Deployments** > deployment > **Functions** atau **Runtime
  Logs**. Error `BACKEND_URL belum dikonfigurasi` berarti variable belum diset;
  `Backend tidak dapat dijangkau` berarti URL, TLS, atau service backend bermasalah.
- Render: service > **Logs**. Log `[dashboard]` menunjukkan request masuk.
- `/api/methods` pada domain Vercel harus menghasilkan JSON tiga metode;
  `configured` harus `true` untuk provider dengan credential lengkap.

## Git

Untuk repository baru:

```powershell
git init
git add .
git status
git commit -m "Prepare portfolio deployment for Vercel"
git branch -M main
git remote add origin https://github.com/USERNAME/REPOSITORY.git
git push -u origin main
```

Periksa `git status` sebelum commit dan pastikan tidak ada `.env`, `.venv`, token,
atau credential yang ikut ter-stage.
