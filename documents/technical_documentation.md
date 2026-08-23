# BärnHäckt 2026 — <!-- TODO: Projektname --> Technische Dokumentation

Unser Projekt ist eine Mixed-Reality-App für die Meta Quest 3, die ein Büro
vermisst, fotografiert und daraus konkrete Nachhaltigkeits-Massnahmen ableitet —
mit Produktvorschlägen, einer Zehnjahres-Ersparnis in Franken und einer Position
im Raum, an die die Massnahme gehört. Der Client ist in Unity (Editor
`6000.5.9f1`) mit dem Meta XR SDK `205.0.0` und dem Mixed Reality Utility Kit
(MRUK) gebaut, das Backend ist eine FastAPI-Anwendung, die eine dreistufige
Gemini-Pipeline fährt.

---

## 1 Projektidee und Impact

### Das Problem

Ein Nachhaltigkeits-Audit für ein Büro ist heute entweder teuer oder generisch.
Eine Beraterin kostet Tagessätze; eine Checkliste aus dem Netz weiss nichts über
den Raum, in dem sie angewendet wird. Zwischen «schaltet die Monitore aus» und
einem bezahlten Audit gibt es nichts, und deshalb passiert in den meisten kleinen
Büros schlicht nichts.

Das eigentliche Problem ist die fehlende Verbindung zwischen Ratschlag und Raum.
Ein Tipp, der nicht sagt, *welcher* Mülleimer ersetzt gehört und *was* das über
zehn Jahre bringt, wird nicht umgesetzt.

### Unsere Lösung

Die App scannt den Raum mit MRUK, führt die Nutzerin systematisch durch die
begehbaren Bereiche und schiesst dabei automatisch Passthrough-Aufnahmen. Anchors
und Bilder gehen ans Backend, das daraus eine Objektbeschreibung des Raums baut,
die Nachhaltigkeitsprobleme benennt und für jedes davon reale, kaufbare Produkte
recherchiert. Zurück kommen bis zu **acht Conclusions**, jede mit Problem,
Lösungen, Quelle, Zehnjahres-Ersparnis und dem MRUK-Anchor, zu dem sie gehört.

### Warum VR/AR und nicht eine normale App

Weil wir Geometrie brauchen, die ein Handyfoto nicht liefert. MRUK gibt uns die
Anchors des Raums mit Position, Rotation und Grösse in Metern, dazu die
Raumgrenzen und einen Raycast gegen die Raumgeometrie. Erst damit können wir den
Boden in Zellen zerlegen, prüfen, wo überhaupt jemand stehen kann, und messen, ob
eine Blickrichtung genug freie Sicht hat, um ein brauchbares Bild zu ergeben.

Die Passthrough-Kamera liefert die zweite Hälfte: Anchors sagen, *dass* dort ein
Tisch steht, die Bilder sagen, in welchem Zustand er ist und was darauf liegt.
Unsere erste Pipeline-Stufe führt genau diese beiden Quellen zusammen.

Und weil der Raum bekannt ist, kann die Antwort ebenfalls räumlich sein: jede
Conclusion trägt das Label eines echten MRUK-Anchors und eine x/y/z-Position, an
der ihr Erklärungspanel schweben soll. **Der Vorschlag hängt am Objekt, nicht in
einer Liste.**

### Impact

Wir haben den Output an drei Stellen bewusst hart eingegrenzt, damit am Ende
etwas steht, das jemand am Montag umsetzen kann:

- **Nur im Raum umsetzbar.** Beide Analyse-Prompts verbieten explizit alles, was
  einen Umbau, einen Standortwechsel oder eine Änderung am Geschäftsmodell
  bräuchte. Erlaubt ist, was gekauft, hereingetragen, ersetzt, ausgeschaltet,
  ausgesteckt oder umgestellt werden kann.
- **Reale Produkte, keine erfundenen.** Die Recherche-Stufe läuft mit
  Google-Search-Grounding. Der Prompt schreibt vor, lieber eine
  Verhaltensänderung zu nennen als ein Produkt zu erfinden, und **niemals eine
  URL zu erfinden** — ohne Quelle bleibt das Feld leer.
- **Eine Zahl statt eines Gefühls.** Jede Conclusion muss eine
  Zehnjahres-Ersparnis in Franken angeben, dazu einen Satz, woher die Zahl kommt.
  Das Format ist erzwungen und wird serverseitig normalisiert.

Angenommene Massnahmen werden mit Status in der Datenbank gehalten. Ein
Unternehmen sieht damit über mehrere Scans hinweg, wozu es sich verpflichtet hat.

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

Die Web-App spricht das Backend nicht direkt an, sondern über einen Rewrite auf
ihrem eigenen Origin (`/backend`). Damit ist der Request same-origin und die
CORS-Allowlist des Servers spielt keine Rolle mehr — sonst müsste jede
Deployment-Domain einzeln in `ALLOWED_ORIGINS` eingetragen werden.

### Der Endpoint /receive-data

Das Request-Modell ist in `server/llm/room_description.py` definiert:

```python
class Anchor(BaseModel):
    label: str
    position: List[float]
    rotation: List[float]
    size: Optional[List[float]] = None

class Room(BaseModel):
    anchors: List[Anchor]

class Payload(BaseModel):
    room: Room
    captures: List[str]     # base64-kodierte JPEGs
    company_name: str       # validiert: darf nicht leer sein
```

Die Antwort nennt die gespeicherte Schreibweise des Unternehmens, ob die
Persistenz geklappt hat, und liefert die Conclusions so zurück, wie die Datenbank
sie vergeben hat — mit `id` und `created_at`, damit der Client sie später über
`/accept-solution` referenzieren kann:

```json
{
  "status": "ok",
  "company_name": "3dMike",
  "persisted": true,
  "conclusions": [ { "id": "...", "title": "...", "problem": "...",
                     "solutions": [...], "savings_10y_chf": "|1200|...",
                     "anchor": {...}, "status": "in_progress", ... } ]
}
```

### Persistenz

Jeder Scan bekommt ein Verzeichnis `received/YYYYMMDD_HHMMSS`. Landen zwei Scans
in derselben Sekunde, wird der Name durchnummeriert, statt das bestehende
Verzeichnis zu überschreiben. **Die Rohdaten werden zuerst geschrieben** — Bilder
und `room.json`, bevor der erste bezahlte Call rausgeht. Fällt die Pipeline
danach um, liegt der Scan trotzdem auf der Platte und kann nachgefahren werden.
Danach kommen `description.json`, `problems.txt` und `plan.json` dazu.

Parallel gehen die Conclusions in eine SQLite-Datenbank, zwei Tabellen:
`companies` und `conclusions`. Die Solutions einer Conclusion liegen als
JSON-Spalte und haben keine eigenen IDs — akzeptiert wird immer die ganze
Conclusion, nie eine einzelne Lösung daraus.

### Deployment

Auf dem Server laufen zwei Dienste hinter demselben nginx: die FastAPI-Anwendung
und die Next.js-Web-App. Die Aufteilung der Pfade ist dabei nicht frei gewählt —
der nginx-vhost beansprucht `location /api/` für sich, weshalb die Web-App ihren
Proxy-Prefix auf `/backend` legen musste; ein Rewrite auf `/api` würde die
Requests nie zu sehen bekommen. Die Web-App forwardet serverseitig an
`http://127.0.0.1:8232`, also an das Backend auf derselben Maschine statt an
seinen öffentlichen Namen: der Hop bleibt lokal und funktioniert weiter, falls
Hostname oder Zertifikat einmal ausfallen.

Der Client zeigt direkt auf `https://bernhackt26.kirchenfeldrobotics.ch`. Der
Endpoint `GET /` gibt `{"status": "alive"}` zurück und dient nginx und dem
Headset als Liveness-Probe.

<!-- TODO: .service-Datei und nginx-Konfiguration liegen nicht im Repository.
     Folgende Punkte aus den echten Configs nachtragen: -->

- **systemd:** <!-- TODO: Unit-Name, User, WorkingDirectory, uvicorn-Aufruf (Port 8232), Restart-Policy -->
- **nginx:** <!-- TODO: server_name, client_max_body_size (relevant: die Payloads enthalten mehrere base64-JPEGs), proxy_read_timeout (relevant: die Pipeline läuft bis zu 300 s, der Client-Timeout liegt bei 60 s) -->
- **HTTPS:** <!-- TODO: Certbot-Setup und Renewal für bernhackt26.kirchenfeldrobotics.ch -->

### Fehlerbehandlung und Logging

Der Endpoint übersetzt die Fehler der Pipeline in Statuscodes, statt alles als
500 durchzureichen:

| Ursache | Status | Bedeutung |
|---|---|---|
| Unbekanntes Unternehmen | `404` | Wird geprüft, **bevor** ein Call rausgeht |
| Kaputtes base64, leeres Bild | `400` | Vom Decoder abgelehnt |
| `GEMINI_API_KEY` fehlt | `503` | Server ist nicht konfiguriert |
| Modell nicht erreichbar, kaputtes JSON | `502` | Detail bleibt im Log, nicht in der Antwort |

Zwei Dinge sind uns dabei wichtig gewesen. Erstens: Ein Batch-Verzeichnis, in dem
nichts gelandet ist, wird wieder entfernt, bevor der Fehler zum Statuscode wird.
Zweitens: **Wenn die Datenbank streikt, nachdem das Modell geantwortet hat, darf
die Antwort nicht verloren gehen.** Der Speicherpfad ist deshalb separat
abgesichert; scheitert er, wird der Traceback geloggt, `plan.json` trotzdem
geschrieben und die Antwort mit `persisted: false` ausgeliefert.

Geloggt wird an jeder Stufengrenze mit Mengengerüst — wie viele Anchors und
Bilder reingingen, wie viele Zeichen zurückkamen, wie viele Conclusions
entstanden. Retries protokollieren Fehlercode und Wartezeit.

### Offene Punkte

Der Unity-Client sendet aktuell nur `room` und `captures`; das vom Server
verlangte Pflichtfeld `company_name` fehlt in der `Payload`-Klasse, ein POST aus
dem Headset läuft damit in einen `422`. Das Testskript
`server/test/vr_receive_sim.py` sendet das Feld korrekt und fährt die Pipeline
End-to-End durch.

Ausserdem wertet der Client die Antwort noch nicht aus: `SendData()` loggt den
Response-Body und meldet Erfolg. Die Anchor-Positionen der Conclusions werden
also noch nicht als Panels im Raum gerendert — das Backend liefert sie bereits.

---

## 3 Funktion der AI-Pipeline

### Was im Backend aus Anchors und Captures wird

Der Client schickt zwei sehr unterschiedliche Datenquellen: eine Liste von
MRUK-Anchors mit Label, Position, Rotation und Grösse in Metern, und eine Reihe
von JPEGs, die im Raum verteilt aufgenommen wurden. Anchors sind exakt, aber
stumm — `TABLE` sagt nichts über Zustand oder Nutzung. Bilder sind das Gegenteil.

Wir haben die Pipeline deshalb in drei Stufen zerlegt, die jeweils genau eine
Frage beantworten. Alle drei laufen gegen **`gemini-3.6-flash`**.

### Stufe 1 — Room Description

Der einzige Call, der Bilder sendet. Er bekommt alle Captures plus die
Anchor-Liste als JSON und soll **eine** vereinheitlichte Objektliste zurückgeben:
jeden Anchor unverändert kopiert und um ein `details`-Feld ergänzt, plus alle
weiteren Objekte, die er in den Bildern findet. Die Positionen der selbst
gefundenen Objekte schätzt er anhand der Anchors als Massstab.

Die Zusatzobjekte sind bewusst auf zwei Typen beschränkt — `Trashes` und
`Tables`. Der Grund ist Ehrlichkeit gegenüber der letzten Stufe: nur an diesen
Objekten kann sie später eine Massnahme verankern. Der Prompt verbietet
ausserdem, einen Typ zu erfinden, der auf keinem Bild vorkommt.

Die Bild-Parts stehen im Request **vor** dem Text — das Modell folgt der
Instruktion so zuverlässiger.

### Stufe 2 — Problemanalyse

Bekommt die Room Description und die hinterlegte Geschäftsbeschreibung des
Unternehmens und spielt einen Nachhaltigkeits-Auditor. Der Prompt hat eine
ungewöhnliche Hauptregel: **er darf keine Lösungen nennen.** Kein «sollte», kein
«könnte ersetzt werden durch». Nur Probleme, maximal zehn, das wichtigste zuerst,
jedes mit Beobachtung und Begründung.

Das ist Absicht. Ein Modell, das Problem und Lösung in einem Zug schreibt,
schreibt die Lösung, die ihm zuerst einfällt, und begründet das Problem rückwärts
dazu. Getrennt bekommt die Recherche-Stufe eine saubere Problemliste als Input,
in der jeder Eintrag für sich allein lesbar ist.

### Stufe 3 — Recherche und Conclusions

Zwei Calls, weil die Gemini-API Search-Grounding und ein erzwungenes JSON-Schema
nicht gleichzeitig erlaubt:

1. **Recherche, mit Google Search.** Sucht zu den Problemen reale, kaufbare
   Produkte und schreibt die Funde als Fliesstext samt Quell-URLs.
2. **Strukturierung, mit Schema.** Bekommt Probleme, Anchors und die Recherche
   und füllt das `ConclusionPlan`-Schema.

Die Feldreihenfolge im Schema ist bewusst gewählt: Titel, Problem und Lösungen
stehen vor Ersparnis und Anchor. Das Modell füllt ein Schema von oben nach unten,
also ist die Begründung fertig, bevor es sich auf eine Zahl und einen Ort
festlegt.

### Validierung und Rückgabe an den Client

Auf jedes JSON kommt eine zweite Prüfung durch Pydantic — das erzwungene Schema
der API ist uns als einzige Garantie nicht genug. Passt die Antwort nicht, wird
sie als `GeminiError` abgewiesen und der Client bekommt einen `502` statt halber
Daten.

Ein Feld verdient eine eigene Erwähnung. `savings_10y_chf` muss exakt
`|Betrag|Erklärung` sein, weil aus ihm eine einzige Datenbankspalte wird. Ein
Modell schreibt an dieser Stelle aber gerne `CHF 1'200.–`. Der Validator
toleriert deshalb, was sich reparieren lässt, und lehnt nur ab, was wirklich
fehlt:

```python
amount, separator, explanation = value.strip().lstrip("|").partition("|")
if not separator:
    raise ValueError("savings_10y_chf must be '|amount|explanation'")
digits = re.search(r"\d+", amount.replace("'", "").replace(",", "").replace(" ", ""))
```

### Warum diese Architektur

**Drei Stufen statt einem Call.** Ein einzelner Prompt, der Bilder auswertet,
Probleme findet, Produkte recherchiert und alles räumlich verankert, ist nicht
debugbar — bei einem schlechten Ergebnis weiss man nicht, welcher Teil schuld
war. Drei Stufen schreiben drei Artefakte auf die Platte, und man sieht, wo es
gekippt ist. Der Preis sind vier API-Calls pro Scan und eine spürbare Laufzeit.

**Timeout 300 Sekunden, drei Versuche.** Der Search-Call ist langsam. Ein zu
knapper Timeout bricht einen laufenden, teuren Request ab — schlimmer als gar
keiner. Wiederholt wird nur bei `5xx` und `429`; ein `4xx` würde beim zweiten Mal
dieselbe Absage kassieren.

**Flash statt eines grösseren Modells.** Vier Calls pro Scan, davon einer mit
mehreren Bildern im Kontext, machen Latenz und Kosten zum bestimmenden Faktor.
Die Aufgabenteilung fängt das auf: keine Stufe muss mehr als eine Sache können.

**Dateien und Datenbank parallel.** Die Batch-Verzeichnisse sind das Protokoll,
die Datenbank ist der Zustand. Das Verzeichnis hält fest, was das Modell
tatsächlich gesagt hat, auch wenn die Datenbank gerade nicht erreichbar war.
