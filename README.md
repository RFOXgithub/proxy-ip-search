# Proxy IP Finder Dashboard

Dashboard lokal untuk DataImpulse, Oxylabs, dan IPRoyal. Berjalan sepenuhnya di
komputer sendiri, tanpa deploy ke Vercel/Render.

## Menjalankan

Cara cepat (otomatis membuat `.venv`, install dependency, buka browser):

```powershell
.\run.bat        # Windows
./run.sh         # Linux/macOS
```

Atau manual:

```powershell
python -m pip install -r requirements.txt
python run_dashboard.py
```

Buka <http://127.0.0.1:8765>.

## Credential

Salin `.env.example` ke `.env` (jangan di-commit), atau gunakan `.env` di masing-masing
folder provider (`impulse/`, `oxy/`, `royale/`). Variable berawalan provider:

`IMPULSE_PROXY_USERNAME`, `IMPULSE_PROXY_PASSWORD`, `OXY_PROXY_USERNAME`,
`OXY_PROXY_PASSWORD`, `ROYALE_PROXY_USERNAME`, `ROYALE_PROXY_PASSWORD`.

Setting lain bisa dioverride dengan pola sama, mis. `OXY_COUNTRY`, `ROYALE_CITY`,
`IMPULSE_MAX_WORKERS`. `HOST` dan `PORT` mengubah alamat server (default
`127.0.0.1:8765`).

## Test

```powershell
python -m pytest dashboard impulse oxy royale
```
