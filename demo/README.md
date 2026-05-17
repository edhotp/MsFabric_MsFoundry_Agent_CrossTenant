# Fabric Cross-Tenant MVP — Demo

Implementasi nyata dari rencana di [../demo-mvp-plan.md](../demo-mvp-plan.md).
Dirancang **sederhana**: satu file `.env` untuk semua konfigurasi, satu perintah untuk menjalankan.

> Status kode: scaffold belum dibuat (Sprint 1 belum mulai). Folder ini saat ini hanya berisi `.env.example` dan README ini.
> Setelah Sprint 1 selesai, struktur folder akan mengikuti `demo-mvp-plan.md` §8.

---

## Quickstart (3 langkah)

### 1. Selesaikan prerequisites (one-time)

Ikuti checklist di [../demo-mvp-plan.md](../demo-mvp-plan.md) **§7** — App Registration di Tenant B, admin consent di Tenant A, Fabric Data Agent yang sudah di-publish, Azure OpenAI deployment.

Kumpulkan nilai berikut sebelum melangkah ke #2:

- `TENANT_A_ID` (GUID tenant Fabric)
- `APP_CLIENT_ID` + `APP_CLIENT_SECRET` (dari App Reg di Tenant B)
- `FABRIC_AGENT_PUBLISHED_URL` + `FABRIC_WORKSPACE_ID` + `FABRIC_AGENT_ID` (dari Fabric portal → Data Agent)
- `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_DEPLOYMENT` + (`AZURE_OPENAI_API_KEY` atau jalan `az login`)

### 2. Konfigurasi

```pwsh
# Dari folder demo/
Copy-Item .env.example .env
# Edit .env, isi semua nilai bertanda <...>
notepad .env
```

`.env` **tidak boleh** di-commit ke git — sudah dilindungi `.gitignore` di root repo.

### 3. Jalankan (setelah Sprint 1 selesai)

```pwsh
# Sekali saja — buat virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Jalankan server
uvicorn app.main:app --reload
```

Buka browser ke `http://localhost:8000` → klik **Sign in** → login dengan user Tenant A → mulai chat.

---

## Struktur `.env` — apa isinya?

`.env.example` di folder ini adalah **single source of truth** untuk semua parameter yang dipakai aplikasi. Dikelompokkan menjadi 7 section:

| # | Section | Wajib diisi? |
|---|---|---|
| 1 | Tenant A | ✅ (`TENANT_A_ID`) |
| 2 | App Registration | ✅ (`APP_CLIENT_ID`, `APP_CLIENT_SECRET`) |
| 3 | Fabric Data Agent | ✅ (3 nilai dari portal) |
| 4 | Azure OpenAI | ✅ (endpoint + deployment + key/azcli) |
| 5 | Server | ⚠️ default cukup untuk localhost |
| 6 | Session | ✅ (`SESSION_SECRET_KEY` generate random) |
| 7 | Logging | ⚠️ default `INFO` |

Buka [`.env.example`](.env.example) untuk komentar penjelas tiap variabel.

---

## Troubleshooting cepat

| Gejala | Cek |
|---|---|
| Redirect callback 400 | `APP_REDIRECT_URI` sama persis (huruf, port, slash) dengan yang didaftarkan di Entra App Reg → Authentication |
| `AADSTS50020` saat login | User belum ditambahkan sebagai guest di Tenant A, atau admin consent belum dilakukan |
| Fabric Data Agent 401/403 | Token `aud` bukan `https://analysis.windows.net/powerbi/api`, atau user belum punya role **Build** di semantic model + Read di Data Agent (lihat plan §7.3) |
| Azure OpenAI 401 | `AZURE_OPENAI_AUTH_MODE=apikey` tapi key kosong; atau `azurecli` tapi belum `az login` |
| LLM tidak memanggil tool | Naikkan `LOG_LEVEL=DEBUG`, periksa apakah `ask_fabric_data_agent` terdaftar pada `ChatAgent` |

Untuk troubleshoot mendalam, ikuti **§11. Testing Strategy** di [../demo-mvp-plan.md](../demo-mvp-plan.md).
