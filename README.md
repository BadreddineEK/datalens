# DataLens

Micro-SaaS B2B — Audit qualité CSV en 30 secondes.

## Structure

```
datalens/
├── backend/          → FastAPI API (Render Free)
│   ├── main.py
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── render.yaml
│   ├── .env.example
│   └── src/
│       ├── audit/         # profiler.py · scorer.py · type_detector.py
│       ├── payment/       # stripe_handler.py
│       └── utils/         # file_handler.py
├── frontend/         → App outil (Cloudflare Pages — app.datalens.badreddineek.com)
│   ├── index.html
│   ├── style.css
│   └── app.js
├── landing/          → Landing page (Cloudflare Pages — datalens.badreddineek.com)
│   └── index.html
└── tests/            → Tests unitaires pytest
    ├── test_profiler.py
    └── test_scorer.py
```

## Lancement local (backend)

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # renseigner les clés Stripe
uvicorn main:app --reload --port 8000
```

## Tests

```bash
# depuis la racine datalens/
pytest
```

## Variables d'environnement (backend)

| Variable | Description |
|---|---|
| `STRIPE_SECRET_KEY` | Clé secrète Stripe (`sk_live_xxx`) |
| `STRIPE_PRICE_ID` | ID du prix Stripe (`price_xxx`) |
| `STRIPE_WEBHOOK_SECRET` | Secret webhook Stripe (`whsec_xxx`) |
| `APP_URL` | URL de l'app frontend (`https://app.datalens.badreddineek.com`) |

## Deploy

- **Backend** → Render Free : connecter le repo, pointer sur `backend/`, utiliser `render.yaml`
- **Frontend** → Cloudflare Pages : build output `frontend/`, domaine `app.datalens.badreddineek.com`
- **Landing** → Cloudflare Pages : build output `landing/`, domaine `datalens.badreddineek.com`
- **UptimeRobot** : monitor HTTP sur `https://api.datalens.badreddineek.com/api/health` toutes les 14 min
