# CheckMe — Système de surveillance intelligent

MVP de vidéosurveillance avec détection IA locale (YOLOv8 + Apple M1 MPS).

---

## Architecture

```
MacBook Camera (FaceTime HD)
        ↓
Python Backend (FastAPI + OpenCV)
        ↓
Motion Pre-filter (MOG2) ← évite YOLO sur frames statiques
        ↓
YOLOv8n (MPS / M1 GPU) ← ~50 fps sur M1
        ↓
Alertes debounced (5 frames consécutives → alerte)
        ↓
WebSocket → Next.js Dashboard
```

---

## Stack

| Couche | Technologie |
|--------|------------|
| Backend | Python 3.11 · FastAPI · Uvicorn |
| Vision | OpenCV 4 · MOG2 background subtraction |
| IA | YOLOv8n (Ultralytics) · PyTorch MPS |
| Streaming | MJPEG over HTTP (multipart/x-mixed-replace) |
| Temps réel | WebSocket natif (FastAPI) |
| Frontend | Next.js 14 · TypeScript · Tailwind CSS |

---

## Structure du projet

```
CheckMe/
├── backend/
│   ├── main.py          # FastAPI app — MJPEG stream + WebSocket
│   ├── camera.py        # Capture caméra (thread dédié)
│   ├── detector.py      # YOLOv8 wrapper (MPS / CUDA / CPU)
│   ├── motion.py        # Pre-filtre MOG2 (évite YOLO sur frames vides)
│   ├── alerts.py        # Debounce + historique des alertes
│   ├── config.py        # Paramètres configurables
│   └── requirements.txt
└── frontend/
    └── src/
        ├── app/page.tsx           # Dashboard principal
        ├── components/
        │   ├── VideoFeed.tsx      # Flux MJPEG
        │   ├── AlertList.tsx      # Alertes temps réel
        │   └── StatusBar.tsx      # État connexion / AI device
        └── lib/useEvents.ts       # Hook WebSocket
```

---

## Installation & démarrage

### 1. Backend Python

```bash
# Installer les dépendances (1 seule fois)
./setup_backend.sh

# Démarrer le serveur
cd backend
source .venv/bin/activate
python main.py
# → http://localhost:8000
```

### 2. Frontend Next.js

```bash
cd frontend
npm run dev
# → http://localhost:3000
```

---

## Endpoints backend

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/video` | Flux MJPEG live |
| GET | `/api/status` | État caméra + modèle IA |
| GET | `/api/alerts` | Historique des alertes (JSON) |
| WS | `/ws/events` | Événements temps réel |

---

## Classes détectées (COCO)

| Classe | Action |
|--------|--------|
| person | Alerte |
| car | Alerte |
| motorcycle | Alerte |
| bus | Alerte |
| truck | Alerte |
| bird, cat, dog, insecte… | **Ignorés** (faux positifs) |

---

## Configuration (`backend/config.py`)

```python
CONFIDENCE_THRESHOLD = 0.50   # Seuil confiance YOLO
MOTION_MIN_AREA = 2000        # px² min pour activer YOLO
ALERT_TRIGGER_FRAMES = 5      # Frames consécutives avant alerte
ALERT_COOLDOWN_SECONDS = 30   # Délai entre 2 alertes même classe
```

---

## Performances M1 Max estimées

| Composant | Fréquence |
|-----------|-----------|
| Capture caméra | 30 fps |
| MOG2 pre-filter | 30 fps (CPU, négligeable) |
| YOLOv8n (MPS) | ~50 fps |
| Stream MJPEG | 25 fps |

---

## Roadmap MVP → Produit

- [ ] Support RTSP (caméras IP Hikvision / Dahua)
- [ ] Alertes WhatsApp (Twilio / WhatsApp Business API)
- [ ] Alertes SMS
- [ ] Push notifications mobile (Expo / FCM)
- [ ] Enregistrement vidéo des événements (H.264)
- [ ] Multi-caméras
- [ ] Fine-tuning YOLO sur dataset local
- [ ] Déploiement Jetson Nano / Raspberry Pi 5
- [ ] Dashboard multi-sites
