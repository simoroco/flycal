# FlyCal — Flight Calendar Comparator

Application web de comparaison de vols affichée sur un calendrier vertical. Scrape les sites des compagnies aériennes, stocke l'historique des prix, et présente les résultats dans une interface dark mode Liquid Glass.

## Stack technique

- **Frontend** : HTML5 + Vanilla JS + CSS (Liquid Glass Dark Mode)
- **Backend** : FastAPI (Python 3.12)
- **Scraping** : Playwright (Chromium headless) + playwright-stealth, httpx + BeautifulSoup (fallback)
- **Scheduler** : APScheduler (07h00 et 20h00 Europe/Paris)
- **Base de données** : SQLite + SQLAlchemy ORM
- **Email** : smtplib natif
- **Reverse proxy & HTTPS** : Caddy (certificat auto-signé, port 4444)
- **Conteneurisation** : Docker Compose mono-service

## Lancement

```bash
chmod +x start.sh
./start.sh
```

Puis ouvrir **https://localhost:4444** (accepter le certificat auto-signé).

## Lancement manuel (sans script)

```bash
docker compose up --build -d
```

## Architecture

```
├── start.sh
├── docker-compose.yml
├── Dockerfile
├── Caddyfile
├── backend/
│   ├── main.py              # FastAPI + APScheduler
│   ├── database.py           # SQLAlchemy models + init
│   ├── scheduler.py          # Cron jobs 07h/20h
│   ├── email_service.py      # Récap email HTML
│   ├── requirements.txt
│   ├── routers/
│   │   ├── flights.py        # GET /api/flights/last, POST /api/flights/search
│   │   ├── searches.py       # GET /api/searches, POST /api/searches/{id}/rerun
│   │   ├── settings.py       # GET/PUT /api/settings
│   │   ├── crawler.py        # GET/POST /api/crawler/*
│   │   └── airlines.py       # CRUD /api/airlines
│   └── scraper/
│       ├── base.py            # Classe abstraite ScraperBase
│       ├── ryanair.py         # API JSON (sans Playwright)
│       ├── transavia.py       # Playwright + XHR interception
│       ├── airfrance.py       # Playwright + XHR interception
│       └── airarabia.py       # Playwright + XHR/DOM parsing
└── frontend/
    ├── index.html             # Page principale (calendrier)
    ├── searches.html          # Historique des recherches
    ├── settings.html          # Paramètres
    ├── css/
    │   ├── main.css           # Liquid Glass Dark Mode
    │   └── calendar.css       # Calendrier vertical
    └── js/
        ├── api.js             # Client API
        ├── app.js             # Logique page principale
        ├── calendar.js        # Rendu calendrier + colorisation
        └── settings.js        # Logique paramètres
```

## API Documentation

Swagger UI : **https://localhost:4444/api/docs**

## Compagnies par défaut

Transavia, Ryanair, Air France, Air Arabia (configurables dans Paramètres).