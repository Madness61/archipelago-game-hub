# Archipelago Game Hub – Projektübergabe für Claude

**Stand:** 05.11.2026 · **Repository:** https://github.com/Madness61/archipelago-game-hub (privat) · **Branch:** `main`  
**Verifizierter Code-Stand:** `bb8a71ffaa70e43f4cac7060400264c49c4abc24`  
**Zweck:** Technische und fachliche Übergabe. Vor Änderungen bitte den tatsächlichen GitHub-Stand erneut prüfen.

## 1. Projektziel (Produktvision)

Eine benutzerfreundliche Webplattform für eine private Archipelago-Multiplayer-Gruppe: Niemand soll jedes Mal manuell die YAMLs aller Teilnehmer zusammentragen, APWorld-Versionen vergleichen oder Dateinamen verändern müssen.

**Gewünschter Idealablauf:**

1. Ein Spieler besucht den Game Hub und meldet sich an.
2. Er wählt aus der **gemeinsamen, dauerhaft verfügbaren Spielebibliothek** ein Spiel für die anstehende Runde.
3. Andere Spieler wählen unabhängig davon ihre eigenen Spiele; dasselbe Spiel darf mehrfach gewählt werden.
4. Die Bibliothek enthält für jedes Spiel die vorbereitete **YAML-Vorlage**, optional **.apworld**, Metadaten, Installationshinweise und Links zu Client/Mod.
5. Bei Rundenerstellung wird **nur die generierte Kopie** der YAML auf den jeweiligen Spieler-/Slotnamen angepasst. Die zentrale Vorlage bleibt unverändert.
6. Der Host löst serverseitig die Archipelago-Seed-Generierung aus und erhält die fertige `AP_*.zip`.
7. Langfristiges Wunschziel: möglichst automatischer Host-Prozess auf `archipelago.gg` und ein transparenter Link zum entstandenen Raum. **Aktuell nur manueller Upload + „Create Room“ unterstützt.** Keine undokumentierten APIs oder Automatisierungen als bestehende Funktion ausgeben.
8. Die Spieler erhalten pro Spiel eine klare Anleitung mit Downloadlinks und den nötigen Verbindungs-/Mod-Schritten.

**Kernentscheidung:** Keine einzelnen Spielebibliotheken pro Spieler. **Ein gemeinsamer Spielekatalog** mit wiederverwendbaren Vorlagen für alle. Spätere Runden referenzieren Einträge, anstatt Dateien neu hochzuladen.

## 2. Aktueller Implementierungsstand

### Implementiert (im Repository vorhanden)

- Multiuser-Web-App mit Registrierung, Login, Sessions, einfachem Host-Rollenmodell und Gruppencode.
- **Erstes registriertes Konto ist Host**. Alle weiteren Nutzer sind Teilnehmer; Host kann Runden anlegen, Seed-Generierung auslösen und Server-Konfiguration bearbeiten.
- Gemeinsame Spielebibliothek: Spiele erstellen, ansehen, filtern/suchen, bearbeiten und löschen. Autor oder Host darf Einträge ändern/löschen.
- Pro Spiel **eine YAML-Vorlage**, optionale **Custom APWorld**, optionale Coverdatei, Beschreibung, Genre, Anleitung, Setup- und Mod-URL.
- YAML-Inhaltsvalidierung (ein Dokument; Top-Level-Felder `name`, `game` und passende Spieleoptions-Sektion).
- APWorld-ZIP-Strukturprüfung, Pfadprüfungen, Größenlimit und Versionskonflikterkennung per SHA-256 beim Paketbau.
- Mehrere Nutzer können **dasselbe Katalogspiel** in derselben Runde wählen.
- Host erstellt Runden. Jeder Nutzer verwaltet seine **eigene Auswahl** in einer Runde.
- Export als ZIP mit `Players/<slot>.yaml`-Dateien, optionalen Custom Worlds und `manifest.json`.
- Automatische YAML-Slotnamensersetzung in den **Export-/Generierungskopien** (maximal 16 Zeichen; ursprüngliche Vorlagen bleiben erhalten).
- Generator-Anbindung an lokale Archipelago-Installation: `ArchipelagoGenerate.exe` oder `Generate.py`; asynchroner Hintergrundthread, Status/Log und Download der generierten Seed-ZIP.
- Im UI ein Link zur offiziellen Upload-Seite https://archipelago.gg/uploads; der anschließend **manuell** erzeugte Raumlink kann in der Runde gespeichert werden.
- Setup-Ansicht mit den zum ausgewählten Spiel hinterlegten Links/Anleitungen.
- Responsive HTML/CSS/Vanilla-JavaScript-Oberfläche.
- Neuer UI-Fix für **sichtbaren Speicherstatus der YAML/APWorld im Editor**, Dateigrößen und authentifizierte Downloadlinks in Editor und Detailansicht.

### Was **nicht** implementiert oder nicht real getestet ist

- **Kein automatisches Hochladen/Erstellen eines Raums auf archipelago.gg.** Der Host muss `AP_*.zip` hochladen und „Create Room“ anklicken.
- **Kein eigener dauerhaft online gehosteter Webserver**; Anwendung läuft lokal auf Host-PC/LAN. GitHub ist lediglich die Codeablage.
- **Keine automatische Installation von Game-Mods, ROMs oder Clients** auf Teilnehmer-Rechnern. Stattdessen manuelle Anleitungen.
- Keine umfassende produktionsreife Härtung für öffentliches Internet, keine abgesicherte isolierte Sandbox für Custom APWorld-Code.
- **Kein bestätigter produktiver End-to-End-Test** mit der tatsächlichen Archipelago-Installation, unterschiedlichen Custom Worlds und einem echten Room auf archipelago.gg.
- Keine Unterstützung für mehrere YAML-Presets/Profiles desselben Katalogeintrags oder spielerspezifisches Anpassen einzelner YAML-Optionen über die UI.
- Keine automatische APWorld-Versionsauflösung/-Installation auf Teilnehmer-PCs.
- CI prüft Python-Tests mit einem **Fake-/Mock-Generator**, nicht die reale Archipelago-Generierung.

## 3. Technische Architektur

| Datei / Verzeichnis | Funktion |
|---|---|
| `server.py` | Python-HTTP-Server; Auth, SQLite, REST-artige API, Dateispeicherung, Runden und Generator-Aufträge |
| `core.py` | YAML-Validierung und Slotnamenersetzung; APWorld-Prüfung; Erstellung des Runden-ZIPs |
| `web/index.html` | Browseroberfläche mit Spielebibliothek, Rundenplaner, Seed/Hosting und Installation |
| `web/app.js` | API-Anbindung, Dialoge, Auswahl, Upload (Base64-JSON), Anzeige/Download gespeicherter Dateien |
| `web/styles.css` | Dark-UI und responsive Gestaltung |
| `tests/test_core.py` | Core-Unit-Tests |
| `tests/test_api.py` | Black-Box-Integrationstest mit zwei Nutzern und einem Fake-Generator |
| `.github/workflows/tests.yml` | Automatische Tests bei Push/PR |
| `.env.example` | Lokale Konfiguration |
| `start.bat` | Windows-Start mit **Python 3.13** |
| `start.sh` | Linux/macOS-Start |
| `data/` | Laufzeitdaten; **nicht in Git** |

**Stack:** Python 3.13 unter Windows; Python-Standardbibliothek + `PyYAML>=6.0,<7`; SQLite; Vanilla JavaScript; HTML/CSS; keine Node.js-Installation erforderlich.

**Datenfluss:**

```text
Browser (localhost:8765)
  └─ HTTP-Backend (server.py)
       ├─ SQLite: data/hub.sqlite3
       ├─ Spieldateien: data/uploads/<game-id>/options.yaml
       │                                  └── world.apworld (optional)
       ├─ Builds: data/builds/<build-id>/
       └─ Generator-Aufruf auf lokaler Archipelago-Installation
            └─ Seed-ZIP zum Download
                 └─ MANUELLER Upload auf archipelago.gg
                      └─ Raumlink zurück im Game Hub speichern
```

**Wichtig:** YAMLs und APWorlds liegen **auf dem PC/Server**, auf dem die Website läuft – nicht im GitHub-Repository. Datenbank, `data/` und `.env` beim Updaten/Clonen/Umziehen niemals unbedacht überschreiben.

## 4. Einrichten und lokal ausführen (Windows)

Voraussetzungen: Git und VS Code empfohlen; Python **3.13**; eine kompatible Archipelago-Installation (z. B. unter `C:\ProgramData\Archipelago`).

```powershell
git clone https://github.com/Madness61/archipelago-game-hub.git
cd archipelago-game-hub
Copy-Item .env.example .env
```

`.env` anpassen:

```dotenv
AP_BIND=127.0.0.1
AP_PORT=8765
AP_JOIN_CODE=HIER_EIN_EIGENES_LANGES_GEHEIMNIS
ARCHIPELAGO_DIR=C:\ProgramData\Archipelago
```

Dann `start.bat` verwenden oder:

```powershell
py -3.13 -m pip install -r requirements.txt
py -3.13 server.py
```

Browser: http://localhost:8765

**Hintergrund des Python-Pinnings:** Bei einem früheren Start wurde Python 3.15 verwendet; PyYAML versuchte ohne passende vorgefertigte Wheels eine C-Erweiterung zu bauen und scheiterte an fehlenden Microsoft-C++-Build-Tools. `start.bat` wurde deshalb auf `py -3.13` geändert.

Zugriff aus demselben **vertrauenswürdigen** LAN: `AP_BIND=0.0.0.0` und entsprechender Firewall-Zugriff, ohne direkten Internet-Portforward. Bei Zugriff über das Internet bevorzugt sicheres VPN oder gehärtete HTTPS-Bereitstellung; die aktuelle Anwendung **nicht einfach öffentlich exponieren**.

### VS Code + Git-Workflow

- Repository **klonen** statt ständig ZIP-Dateien herunterladen.
- Nach Änderungen auf GitHub: im Projektordner `git pull`; den Python-Server anschließend neu starten, Browser mit `Strg+F5` neu laden.
- Eigene Änderungen: Git-Commit/Push über VS Code.
- Vor einem Pull lokale, uncommittete **Codeänderungen** sichern/committen.
- `data/` und `.env` bleiben lokal und sollen nicht in Commits gelangen.

## 5. Zentrale Datenmodelle und API

In `server.py` werden SQLite-Tabellen `users`, `sessions`, `games`, `rounds`, `picks`, `builds` und `config` angelegt. Persistierte Spieldateien liegen im `data/uploads`-Verzeichnis.

**Wichtige API-Endpunkte:**

| Methode / Route | Bedeutung |
|---|---|
| `POST /api/auth/register`, `POST /api/auth/login` | Registrierung/Login |
| `GET /api/state` | Gemeinsamer UI-Zustand mit Spielen, Runden, Picks und Statusfeldern |
| `POST /api/games` | Spiel samt YAML/APWorld/Cover erstellen |
| `POST /api/games/{id}`, `DELETE /api/games/{id}` | Spiel bearbeiten/löschen |
| `GET /api/games/{id}/yaml` | Gespeicherte YAML herunterladen |
| `GET /api/games/{id}/apworld` | Gespeicherte APWorld herunterladen |
| `GET /api/games/{id}/cover` | Cover laden |
| `POST /api/rounds` | Runde anlegen (Host) |
| `POST /api/picks` | Spielauswahl für den aktuell angemeldeten Spieler |
| `GET /api/rounds/{id}/bundle` | YAML/APWorld-Paket exportieren |
| `POST /api/rounds/{id}/generate` | Seed-Generierung (Host) |
| `GET /api/builds/{id}/log` | Buildstatus/Log |
| `GET /api/builds/{id}/download` | Seed-ZIP herunterladen |
| `POST /api/rounds/{id}/room` | Raumlink speichern |
| `POST /api/settings` | Archipelago-Verzeichnis setzen (Host) |

Datei-Uploads werden im Frontend per `FileReader` in Base64-JSON übertragen. Grenzen aktuell: YAML 512 KiB, APWorld 20 MiB, Cover 3 MiB, gesamter HTTP-Body 36 MiB. Das ist ein bewusst einfacher Ansatz, nicht optimiert für sehr große Uploads.

### YAML-Verarbeitung

`core.validate_yaml` verlangt u. a. ein einfaches, eindeutiges `name:` auf oberster Ebene; der `game`-Wert muss einer Optionssektion entsprechen. `core.render_yaml` ersetzt dieses `name:` in einer **Kopie**, ohne die restlichen YAML-Optionen absichtlich neu zu formatieren. Unterstützte Templates sind dadurch enger gefasst als alle denkbaren Archipelago-YAML-Varianten (z. B. keine gewichtete Game-Auswahl).

Beispiel:

```yaml
name: Vorlage
game: Hollow Knight
Hollow Knight:
  death_link: false
```

Wenn Nutzer `Marci` das Spiel wählt, erhält nur sein generierter Slot die Zeile `name: "Marci"`.

### APWorld-Verarbeitung

- Integrierte Archipelago-Worlds benötigen keine eigene APWorld-Datei.
- Custom APWorlds müssen den passenden ZIP-Inhalt besitzen; Dateiname mit Kleinbuchstaben, Zahlen und Unterstrichen.
- Konflikte derselben APWorld unter gleichem Namen, aber unterschiedlichem Hash werden vor dem Build erkannt.
- Der lokale Generator kann APWorlds in `custom_worlds/` der Archipelago-Installation kopieren; bestehende abweichende Versionen werden nicht überschrieben.
- **APWorlds enthalten potenziell ausführbaren Python-Code.** Herkunft, Version und Sicherheit prüfen; nicht blind auf einem öffentlich erreichbaren Host ausführen.

## 6. Kürzlich behobenes UX-Problem: Uploads scheinen zu fehlen

Ein Benutzer konnte YAML und APWorld erfolgreich hochladen; die Dateien lagen nachweislich unter `data/uploads/<game-id>/`. Beim späteren Bearbeiten stand im Browser-Dateifeld trotzdem „Keine ausgewählt“. **Das ist Browser-Standardverhalten**: Ein File-Input kann nicht mit einer zuvor hochgeladenen Datei vorausgefüllt werden.

**Behobener Zustand im aktuellen Repository:**

- `GET /api/state` enthält nun pro Spiel `has_yaml`, `yaml_size`, `has_apworld` und `apworld_size`.
- Im Spielbearbeitungsdialog wird ein separater **„Gespeichert“-Status mit Größe** angezeigt.
- Im Detail- und Bearbeitungsfenster gibt es Downloads für YAML/APWorld.
- Uploads bleiben bestehen, bis Nutzer explizit eine Ersatzdatei wählen oder etwas entfernen.
- Ein Integrationstest prüft, dass die YAML tatsächlich gespeichert ist und der Download dieselben Bytes liefert.

**Hinweis für Claude:** Die sichtbare Formulierung „Keine ausgewählt“ im nativen Windows-Dateifeld kann bleiben; die darunterliegende Statusanzeige ist die verlässliche Information. Nicht versuchen, File-Inputs programmatisch mit Serverdateien zu füllen.

## 7. Tests und tatsächliche Verifikation

```powershell
py -3.13 -m pip install -r requirements.txt
py -3.13 -m unittest discover -s tests -v
```

Stand `bb8a71f`: GitHub Actions **erfolgreich**, Python-Unit-/Integrationstests vorhanden. Integrationstests verwenden einen temporären Testserver und einen **simulierten** Archipelago-Generator.

Nicht durch diese Tests abgedeckt: tatsächliche Archipelago-Versionen, Mod-Kompatibilität, alle Custom-APWorlds, Browser-End-to-End-Tests, komplette reale Multiworld mit `archipelago.gg` und öffentliche Bereitstellung. Für eine echte Runde unbedingt mit kleinster Testgruppe und vertrauenswürdigen Worlds testen.

## 8. Bekannte Grenzen / Risiken / technische Schulden

1. **Host-Erstellung:** Das erste registrierte Konto wird Host; Registrierung vor Einrichtung sollte nur in geschützter lokaler Umgebung erfolgen.
2. **Datenverlust-Risiko bei Updates:** `data/` und `.env` sind bewusst nicht versioniert. Backup/Restore und klare Update-Dokumentation verbessern.
3. **Nur eine YAML pro Katalogspiel:** Für unterschiedliche Spielmodi/Presets künftig Modellierung „Spiel → mehrere Konfigurationen“, ohne bestehende Runden zu beschädigen.
4. **Welt-Kompatibilität:** Derzeit wird nur Grundstruktur validiert; ein hochgeladenes Spiel ist nicht automatisch mit der installierten Archipelago-Version kompatibel.
5. **APWorld-Ausführung:** Python-Code aus fremden Welten ist sicherheitskritisch; mittelfristig isolierter Generator, vertrauenswürdige Quellen, Version-Pinning und explizite Host-Freigabe.
6. **Build-Prozess:** Ein Generator-Job zur Zeit; 900-Sekunden-Timeout; Status/Logs vorhanden, aber keine Jobqueue und keine automatische Retry-/Recovery-Strategie.
7. **Hosting auf archipelago.gg:** Aktuell bewusst manueller Prozess. Eine nicht offiziell dokumentierte API nicht als stabil voraussetzen.
8. **Erreichbarkeit der Website:** Nur für privates LAN ausgelegt, keine HTTPS-/Cloud-Infrastruktur oder abgesicherter Mehrbenutzer-Betrieb im öffentlichen Internet.
9. **Client-Installation:** Nur textbasierte Anleitung und Links; keine automatische Mod-Installation.
10. **Upload-UX:** Dateiauswahl und sichtbarer Speicherstatus getrennt; zusätzliche Benachrichtigungen/Validierungsfeedback/Prüfung vorhandener World-Versionen wären hilfreich.

## 9. Empfohlene nächsten Aufgaben (Priorisierung)

**P0 – erst zuverlässig und nachvollziehbar machen:**

- Repo lokal aus VS Code starten, Status- und Downloadanzeige gespeicherter Dateien live überprüfen.
- Echte Generierung mit einer kleinen Archipelago-Runde (z. B. 2 Benutzer und bekannte kompatible Worlds) testen; Logs, Weltdateien, Seed-ZIP, archipelago.gg-Raum und Clientverbindung prüfen.
- Bessere Fehlermeldungen bei ungültigen YAMLs/APWorlds, Konflikten und Generator-Ausgaben.
- Backup-/Restore-Prozess für `data/` dokumentieren oder implementieren.
- Einrichtung und Update-Ablauf ohne Neuinstallation vereinfachen.

**P1 – spielerfreundlicher:**

- Mehrere YAML-Presets pro Spiel, ggf. pro Nutzer auswählbar, ohne Katalogvorlagen zu verändern.
- Pro Spiel geführter Setup-Assistent mit geprüften Mod-/APWorld-Quellen, Versionen und Installationshinweisen.
- Verfügbare Archipelago-Worlds erkennen und sichtbar zwischen „integriert“, „Custom erforderlich“, „nicht installiert“ unterscheiden.
- Übersicht aller Runde-Slots, Bereitschaftsstatus und verständliche Fehlermeldungen vor Generierung.
- Gepinnte APWorld-Hashes/Versionen und bessere Konfliktbehandlung.

**P2 – später, nicht blind automatisieren:**

- Sichere Bereitstellung für die Gruppe über VPN oder angemessen gehärtete Internet-Infrastruktur.
- Getrennte/isolierte Generator-Worker mit sauberer APWorld-Versionierung.
- **Automatisches** Hosting nur prüfen, wenn es einen autorisierten, tragfähigen Schnittstellenweg gibt; alternativ eigene Archipelago-Server-Infrastruktur.

## 10. Arbeitsanweisung für Claude

Du übernimmst eine **bereits existierende** Python-Webanwendung, nicht ein Greenfield-Projekt. **Lies vor Änderungen `README.md`, `server.py`, `core.py`, `web/app.js` und die Tests.**

- Die gemeinsame Spielebibliothek und die **unveränderten YAML-Vorlagen** sind zentrale Produktanforderungen.
- Bereits hochgeladene Nutzerdateien und Datenbank niemals bei Update/Refactoring löschen.
- Unterschied klar halten: Code auf GitHub, Laufzeitdateien im lokalen `data/`-Ordner.
- Zuerst kleine, überprüfbare Änderungen; passende Tests ergänzen; bei Fehlern den tatsächlichen Ablauf erklären.
- Keine Automatisierung von `archipelago.gg` behaupten, bevor sie nachweislich funktioniert und rechtlich/technisch vorgesehen ist.
- Keine ROMs, Secrets, `.env`, Nutzer-Uploads oder Datenbank in Git committen.
- Änderungen möglichst als nachvollziehbare Commits/PRs auf dem verbundenen Repository; Windows-Start und Python 3.13 berücksichtigen.
- Ziel ist eine **einfache Endnutzererfahrung**: Spieler sucht Spiel → wählt es → Host generiert und hostet mit möglichst wenig Handarbeit.

**Ausgangspunkt für die Zusammenarbeit:** https://github.com/Madness61/archipelago-game-hub
