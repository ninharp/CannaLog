<p align="center"><img src="app/static/assets/logo.png" alt="CannaLog" width="420"></p>

# CannaLog

CannaLog ist ein privates Grow-Tagebuch für Pflanzen, Zelte und Außenbereiche. Du hältst fest,
was du gießt, düngst und misst, siehst auf einen Blick, in welcher Phase jede Pflanze steht,
und stellst die Einträge als Bericht oder PDF zusammen. Die App läuft eigenständig per Docker
oder als App in Home Assistant und ist fürs Handy im Zelt genauso gebaut wie für den Desktop.

![Übersicht](assets/screenshot_dashboard.png)

## Funktionen

- **Übersicht nach Umgebung:** jede Pflanze mit Phasenleiste, Tag seit dem Start und letzter Aktion,
  jedes Zelt mit Maßen, Lichtzyklus, Lampenleistung und dem letzten Klima
- **Aktionen:** Gießen, Düngen, Training, Umtopfen, Ernte und mehr, mit Notizen
- **Messungen:** pH, EC, TDS, Höhe, Wassertemperatur und PPFD pro Pflanze, Temperatur, Luftfeuchte,
  VPD, CO₂ und Lichtabstand pro Umgebung, jeweils als Einzelwert oder Bereich
- **Fotos:** mehrere pro Pflanze oder Umgebung, eines davon als Vorschaubild
- **Bericht:** Klima, Messungen und Aktionen einer Umgebung am Bildschirm oder als PDF
- **Schnellerfassung am Handy:** feste Leiste für Aktion, Messung und Foto
- **Mehrere Konten**, Registrierung abschaltbar

## Screenshots

| Pflanze | Umgebung |
| --- | --- |
| ![Pflanze](assets/screenshot_plant_overview.png) | ![Umgebung](assets/screenshot_env_overview.png) |
| **Messung erfassen** | **Bericht** |
| ![Messung](assets/screenshot_plant_log.png) | ![Bericht](assets/screenshot_report.png) |

Am Handy:

<p>
  <img src="assets/screenshot_mobile_dashboard.png" alt="Übersicht am Handy" width="250">
  <img src="assets/screenshot_mobile_plant.png" alt="Pflanze am Handy" width="250">
  <img src="assets/screenshot_mobile_action.png" alt="Aktion eintragen am Handy" width="250">
</p>

## Installation

### Home Assistant

CannaLog gibt es als Home-Assistant-App mit Seitenleiste (Ingress) und direktem Port:
[ninharp/CannaLog_HomeAssistant](https://github.com/ninharp/CannaLog_HomeAssistant)

### Docker

```bash
docker compose up -d
```

Die App läuft dann auf http://localhost:5000, Datenbank, Bilder und der erzeugte
Sitzungsschlüssel liegen in `./data`.

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `SECRET_KEY` | leer | Leer: wird einmalig erzeugt und in `/data/secret_key` gespeichert |
| `ALLOW_REGISTRATION` | `true` | Neue Konten erlauben |
| `SECURE_COOKIES` | `false` | Cookies nur über HTTPS senden (hinter einem HTTPS-Proxy einschalten) |
| `MAX_UPLOAD_MB` | `20` | Maximale Upload-Größe |
| `CANNALOG_DATA_DIR` | `instance/` bzw. `/data` | Ablage für Datenbank, Uploads und Schlüssel |

### Lokal entwickeln

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python init_db.py
.venv/bin/python run.py
```

Für den PDF-Export braucht WeasyPrint Pango (`brew install pango` bzw. `apk add pango`).

## Releases

Ein Tag `vX.Y.Z` baut per GitHub Actions `ghcr.io/ninharp/cannalog` (Standalone) und
`ghcr.io/ninharp/{aarch64,amd64}-cannalog-addon` (Home Assistant). Danach im
HA-Repository `version` in `cannalog/config.yaml` anheben.

## Lizenz

MIT License
