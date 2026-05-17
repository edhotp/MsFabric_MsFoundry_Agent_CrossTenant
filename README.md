# MS Fabric × MS Foundry — Agent Cross-Tenant

Repositori ini berisi **proposal arsitektur, alternatif solusi, dan rencana demo** untuk skenario di mana **Microsoft Fabric Data Agent** dan **Azure AI Foundry Agent Service** berada di **dua tenant Microsoft Entra (Azure AD) yang berbeda** dan harus tetap dapat berkolaborasi dalam satu pengalaman agen AI.

---

## Konteks Singkat

- **Tenant A** — host **Microsoft Fabric** (workspace, Power BI semantic model, Microsoft Fabric Data Agent).
- **Tenant B** — host **Azure AI Foundry** (Agent Service, model deployment).
- **Masalah**: Microsoft Fabric Data Agent ketika dipanggil sebagai *tool* dari **Foundry Agent Service** saat ini **mensyaratkan same-tenant** dengan Foundry, dan pada jalur tersebut **tidak mendukung Service Principal** (wajib *user identity passthrough* / OBO). Akibatnya, Foundry Agent di Tenant B tidak dapat memanggil Fabric Data Agent di Tenant A meski user sudah berstatus *guest*. (Catatan: panggilan **langsung** ke Fabric Data Agent kini mendukung Service Principal sebagai *preview* terpisah — lihat proposal Bagian 1.1.)
- **Solusi inti**: bangun **Agent Manager** custom (berbasis [Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/overview/)) di Tenant B yang melakukan akuisisi token *user-delegated* / *On-Behalf-Of* lintas tenant ke Tenant A, lalu memanggil Microsoft Fabric Data Agent dengan identitas user yang valid.

---

## Daftar Dokumen

| Dokumen | Isi | Audiens |
|---|---|---|
| [proposal-agent-manager-cross-tenant.md](proposal-agent-manager-cross-tenant.md) | **Proposal utama (v1.4)** — arsitektur lengkap, alur autentikasi On-Behalf-Of lintas tenant, contoh kode Python (Microsoft Agent Framework 1.0.0rc6 + Microsoft Authentication Library), pertimbangan keamanan, topologi *deployment*, *roadmap*, risiko, dan referensi Microsoft Learn. Juga berisi **Daftar Singkatan dan Istilah** lengkap. | Solution Architect, Tech Lead, Security |
| [demo-mvp-plan.md](demo-mvp-plan.md) | **Software Development Plan MVP (v1.1)** — rencana implementasi demo end-to-end sederhana (Python FastAPI backend + web UI vanilla) untuk membuktikan integrasi lintas tenant. Berisi arsitektur, sequence diagram autentikasi & chat, project structure, 5 sprint development plan dengan acceptance criteria, demo script, dan **alignment matrix** ke proposal v1.4 + Microsoft Learn. | Developer, Demo Engineer |

> Dokumen pendukung lain (alternatif solusi berbasis Device Code flow tanpa middle-tier, rencana hardening produksi) **direncanakan** dan dapat ditambahkan ke repositori ini di kemudian hari.

---

## Bagaimana Cara Membaca Repo Ini?

1. **Mulai dari [proposal-agent-manager-cross-tenant.md](proposal-agent-manager-cross-tenant.md)** — pahami konteks (Bagian 1), istilah (Bagian 2), tujuan (Bagian 3), dan opsi solusi (Bagian 4).
2. **Pelajari arsitektur** di Bagian 5 dan **alur autentikasi lintas tenant** di Bagian 6.
3. **Lihat contoh kode Python** di Bagian 7 (sudah disesuaikan dengan Microsoft Agent Framework Python 1.0.0rc6 — Januari 2026).
4. **Baca pertimbangan keamanan, topologi *deployment*, *roadmap*, dan risiko** di Bagian 8–11.
5. **Referensi Microsoft Learn** lengkap tersedia di Bagian 13.
6. **Untuk mulai membangun demo MVP**, lanjut ke [demo-mvp-plan.md](demo-mvp-plan.md) — rencana implementasi singkat (5 sprint, ~18 jam kerja) dengan stack Python FastAPI + Microsoft Agent Framework + Azure OpenAI + Microsoft Fabric Data Agent.

---

## Prasyarat Teknis (Ringkas)

Untuk implementasi sebenarnya, Anda akan memerlukan minimal:

- **Tenant A (Fabric)**:
  - Microsoft Fabric *Capacity* aktif (mis. F64) dan satu *Workspace* yang sudah memiliki **Microsoft Fabric Data Agent** ter-*publish*.
  - User dari Tenant B telah ditambahkan sebagai *guest* (Microsoft Entra B2B) dengan peran minimal *Contributor*.
  - **Cross-Tenant Access Settings (Inbound)** mengizinkan Tenant B.
  - **Admin consent** atas izin *delegated* yang dibutuhkan (`Item.ReadWrite.All`, `<itemType>.Read.All`) untuk *Application Registration* multi-tenant milik Agent Manager.
- **Tenant B (Foundry / Agent Manager)**:
  - *Application Registration* multi-tenant (Confidential Client) untuk Agent Manager + *client secret* atau *certificate*.
  - **Azure OpenAI** *deployment* (mis. GPT-4.1 / GPT-5).
  - (Opsional) Microsoft Foundry Project untuk sub-agen tambahan.
  - Layanan *hosting* untuk Agent Manager (mis. **Azure Container Apps**, **Azure App Service**).
  - **Azure Key Vault** untuk *secret*; **Azure Cache for Redis** untuk *token cache*.
- **Sisi Developer**:
  - Python ≥ 3.10.
  - `agent-framework`, `agent-framework-azure`, `msal`, `azure-identity`, `python-dotenv` (versi terkini per Mei 2026).
  - Catatan: Microsoft Agent Framework **tidak** memuat `.env` secara otomatis — wajib `load_dotenv()`.

---

## Kontribusi

Repositori ini bersifat dokumentatif. Pertanyaan, koreksi teknis, dan saran penyempurnaan dipersilakan melalui *Issues* atau *Pull Request*. Sertakan referensi ke [Microsoft Learn](https://learn.microsoft.com/) bila menyangkut kebenaran teknis.

---

## Lisensi

Konten dokumentasi ini disediakan **apa adanya (as-is)** tanpa jaminan apa pun, baik tersurat maupun tersirat. Pembaca menggunakan informasi ini atas risiko sendiri.

Seluruh nama produk Microsoft (Microsoft Fabric, Power BI, Azure OpenAI, Microsoft Foundry, Microsoft Entra, Azure AI, dll.) adalah merek dagang Microsoft Corporation. Penggunaan nama-nama tersebut dalam dokumen ini semata-mata untuk tujuan referensi teknis.
