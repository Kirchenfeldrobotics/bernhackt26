# BärnHäckt 2026 — Kirchenfeldrobotics Technische Dokumentation

Unser Projekt ist eine Mixed-Reality-App für die Meta Quest 3, die ein Büro
vermisst, fotografiert und mithilfe einer Unternehmensbeschreibung daraus konkrete Nachhaltigkeits-Massnahmen ableitet —
mit Produktvorschlägen, einer Zehnjahres-Ersparnis in Franken und einer Position
im Raum, an die die Massnahme gehört. Der Client ist in Unity (`6000.5.9f1`) mit
dem Meta XR SDK `205.0.0` und dem Mixed Reality Utility Kit (MRUK) gebaut, das
Backend ist eine FastAPI-Anwendung mit dreistufiger Gemini-Pipeline.

---

## 1 Projektidee und Impact

### Das Problem

Ein Nachhaltigkeits-Audit für ein Büro ist entweder teuer oder generisch —
zwischen «schaltet die Monitore aus» und einem bezahlten Audit gibt es nichts. Es
fehlt die Verbindung zwischen Ratschlag und Raum: ein Tipp, der nicht sagt,
*welcher* Mülleimer ersetzt gehört, wird nicht umgesetzt.

### Unsere Lösung

Die App scannt den Raum mit MRUK und schiesst dabei Passthrough-Aufnahmen.
Anchors und Bilder gehen ans Backend, das daraus eine Objektbeschreibung baut,
die Probleme benennt und dazu reale Produkte recherchiert. Zurück kommen bis zu
**acht Conclusions**, jede mit Problem, Lösungen, Quelle, Ersparnis und Anchor.

### Warum VR/AR und nicht eine normale App

Weil wir Geometrie brauchen, die ein Handyfoto nicht liefert. MRUK gibt die
Anchors mit Position, Rotation und Grösse in Metern, die Passthrough-Kamera die
zweite Hälfte: Anchors sagen, *dass* dort ein Tisch steht, die Bilder, in welchem
Zustand. Weil der Raum bekannt ist, kann auch die Antwort räumlich sein — **der
Vorschlag hängt am Objekt, nicht in einer Liste.**

### Impact

Wir haben den Output an drei Stellen hart eingegrenzt, damit am Ende etwas
steht, das jemand am Montag umsetzen kann:

- **Nur im Raum umsetzbar.** Die Prompts verbieten alles, was Umbau,
  Standortwechsel oder eine Änderung am Geschäftsmodell bräuchte.
- **Reale Produkte, keine erfundenen.** Die Recherche läuft mit
  Google-Search-Grounding: lieber eine Verhaltensänderung als ein erfundenes
  Produkt, und **niemals eine erfundene URL** — ohne Quelle bleibt das Feld leer.
- **Eine Zahl statt eines Gefühls.** Jede Conclusion nennt eine
  Zehnjahres-Ersparnis in Franken und einen Satz, woher sie kommt.

Angenommene Massnahmen werden mit Status gespeichert — ein Unternehmen sieht über
mehrere Scans hinweg, wozu es sich verpflichtet hat.

---

## 2 API Implementation

### Architekturübersicht

```
Meta Quest 3 (Unity/MRUK)  ──POST /receive-data──┐
                                                 ├──> nginx ──> FastAPI ──> Gemini API
Web-App (Next.js)  ──/backend/*  (Rewrite)───────┘                  │
                                                                    ├──> received/<batch>/
                                                                    └──> SQLite (app.db)
```

Die Web-App spricht das Backend über einen Rewrite auf ihrem eigenen Origin an
(`/backend`). Damit ist der Request same-origin und die CORS-Allowlist des
Servers spielt keine Rolle mehr.

### Der Endpoint /receive-data

Das Request-Modell steht in `server/llm/room_description.py`:

```python
class Payload(BaseModel):
    room: Room              # room.anchors: label, position, rotation, size
    captures: List[str]     # base64-kodierte JPEGs
    company_name: str       # validiert: darf nicht leer sein
```

Die Antwort nennt die gespeicherte Schreibweise des Unternehmens, ob die
Persistenz geklappt hat (`persisted`), und liefert die Conclusions mit `id`
zurück — die referenziert der Client über `/accept-solution`.

### Persistenz

Jeder Scan bekommt ein Verzeichnis `received/YYYYMMDD_HHMMSS`; landen zwei in
derselben Sekunde, wird der Name durchnummeriert. **Die Rohdaten werden zuerst
geschrieben** — Bilder und `room.json`, bevor der erste bezahlte Call rausgeht;
fällt die Pipeline danach um, liegt der Scan trotzdem auf der Platte. Danach
folgen `description.json`, `problems.txt` und `plan.json`.

Parallel gehen die Conclusions in eine SQLite-Datenbank (`companies`,
`conclusions`). Die Solutions liegen als JSON-Spalte ohne eigene IDs — akzeptiert
wird immer die ganze Conclusion.

### Deployment

Hinter demselben nginx laufen zwei Dienste. Der vhost beansprucht
`location /api/` für sich — daher der Proxy-Prefix `/backend`. Die Web-App
forwardet an `http://127.0.0.1:8232` statt an den öffentlichen Namen, der Hop
bleibt also lokal.

- **systemd** (`bernhackt26.service`): als `www-data`, WorkingDirectory
  `/var/www/webapp-bernhackt/server/`, ExecStart
  `venv/bin/uvicorn main:app --host 127.0.0.1 --port 8232`, `Restart=on-failure`
  mit `RestartSec=3`. `ReadWritePaths` gibt nur `data/` und `received/` frei.
- **Web-App:** unter pm2 (`next start --hostname 127.0.0.1 --port 3005`), nicht
  unter systemd.
- **nginx:** `bernhackt26.…` reicht `/` an `127.0.0.1:8232` durch;
  `webapp-bernhackt.…` reicht `/` an `127.0.0.1:3005` und `/api/` an
  `127.0.0.1:8232`. Beide: `client_max_body_size 50M` (base64-JPEGs) und
  `proxy_read_timeout` / `proxy_send_timeout` auf `300s`. Port 80 gibt ein `301`.
- **HTTPS:** Let's Encrypt via Certbot, Zertifikate unter
  `/etc/letsencrypt/live/<host>/`, Erneuerung über `certbot.timer`.

Der Client zeigt direkt auf `https://bernhackt26.kirchenfeldrobotics.ch`. `GET /`
gibt `{"status": "alive"}` zurück und dient als Liveness-Probe.

### Fehlerbehandlung und Logging

Der Endpoint übersetzt Pipeline-Fehler in Statuscodes, statt alles als 500
durchzureichen:

| Ursache | Status | Bedeutung |
|---|---|---|
| Unbekanntes Unternehmen | `404` | Wird geprüft, **bevor** ein Call rausgeht |
| Kaputtes base64, leeres Bild | `400` | Vom Decoder abgelehnt |
| `GEMINI_API_KEY` fehlt | `503` | Server ist nicht konfiguriert |
| Modell nicht erreichbar, kaputtes JSON | `502` | Detail bleibt im Log |

**Wenn die Datenbank streikt, nachdem das Modell geantwortet hat, darf die
Antwort nicht verloren gehen.** Der Speicherpfad ist separat abgesichert:
scheitert er, wird `plan.json` trotzdem geschrieben und mit `persisted: false`
geantwortet. Geloggt wird an jeder Stufengrenze mit Mengengerüst.

### Offene Punkte

Der Unity-Client sendet nur `room` und `captures` — das Pflichtfeld
`company_name` fehlt in seiner `Payload`-Klasse, ein POST aus dem Headset läuft
damit in einen `422`. `server/test/vr_receive_sim.py` sendet es korrekt und fährt
die Pipeline End-to-End durch.

Er setzt ausserdem `req.timeout = 60`, während nginx und Pipeline auf 300 s
ausgelegt sind — ein vollständiger Scan bricht clientseitig ab, bevor die Antwort
da ist. Und er wertet sie noch nicht aus: die Conclusions werden nicht als Panels
gerendert, obwohl das Backend sie liefert.

---

## 3 Funktion der AI-Pipeline

### Was im Backend aus Anchors und Captures wird

Der Client schickt zwei sehr unterschiedliche Datenquellen: MRUK-Anchors und
JPEGs. Anchors sind exakt, aber stumm — `TABLE` sagt nichts über Zustand oder
Nutzung. Bilder sind das Gegenteil. Wir haben die Pipeline deshalb in drei Stufen
zerlegt, die jeweils genau eine Frage beantworten. Alle Calls laufen gegen
**`gemini-3.6`**, gesetzt über `GEMINI_MODEL` in der `.env`.

### Stufe 1 — Room Description

Der einzige Call, der Bilder sendet. Er bekommt alle Captures plus die
Anchor-Liste und soll **eine** vereinheitlichte Objektliste zurückgeben: jeden
Anchor unverändert kopiert und um ein `details`-Feld ergänzt, plus weitere
Objekte aus den Bildern, deren Positionen er anhand der Anchors schätzt.

Die Zusatzobjekte sind bewusst auf `Trashes` und `Tables` beschränkt — nur daran
kann die letzte Stufe eine Massnahme verankern. Einen Typ zu erfinden, der auf
keinem Bild vorkommt, verbietet der Prompt. Die Bild-Parts stehen **vor** dem
Text; so folgt das Modell der Instruktion zuverlässiger.

### Stufe 2 — Problemanalyse

Bekommt die Room Description und die hinterlegte Geschäftsbeschreibung und spielt
einen Nachhaltigkeits-Auditor. Der Prompt hat eine ungewöhnliche Hauptregel: **er
darf keine Lösungen nennen.** Nur Probleme, maximal zehn, das wichtigste zuerst.

Das ist Absicht: ein Modell, das Problem und Lösung in einem Zug schreibt, nimmt
die Lösung, die ihm zuerst einfällt, und begründet das Problem rückwärts dazu.

### Stufe 3 — Recherche und Conclusions

Zwei Calls, weil die Gemini-API Search-Grounding und ein erzwungenes JSON-Schema
nicht gleichzeitig erlaubt:

1. **Recherche, mit Google Search.** Sucht reale, kaufbare Produkte und schreibt
   die Funde als Fliesstext samt Quell-URLs.
2. **Strukturierung, mit Schema.** Füllt aus Problemen, Anchors und Recherche das
   `ConclusionPlan`-Schema.

Die Feldreihenfolge ist bewusst gewählt: Titel, Problem und Lösungen stehen vor
Ersparnis und Anchor. Das Modell füllt ein Schema von oben nach unten, also ist
die Begründung fertig, bevor es sich auf Zahl und Ort festlegt.

### Validierung

Auf jedes JSON kommt eine zweite Prüfung durch Pydantic — das erzwungene Schema
der API ist uns als einzige Garantie nicht genug. Passt die Antwort nicht, wird
sie als `GeminiError` abgewiesen und der Client bekommt einen `502` statt halber
Daten. `savings_10y_chf` muss exakt `|Betrag|Erklärung` sein; der Validator
repariert Trennzeichen und Währungssymbol, lehnt aber ab, wenn Betrag oder
Erklärung fehlt.

### Warum diese Architektur

**Drei Stufen statt einem Call**, weil ein einzelner Prompt, der alles auf
einmal macht, nicht debugbar ist: drei Stufen schreiben drei Artefakte auf die
Platte, und man sieht, wo es gekippt ist. Der Preis sind vier API-Calls pro Scan.
**Timeout 300 s, drei Versuche**, weil der Search-Call langsam ist und ein zu
knapper Timeout einen teuren Request abbricht; wiederholt wird nur bei `5xx` und
`429` — ein `4xx` würde beim zweiten Mal dieselbe Absage kassieren.
