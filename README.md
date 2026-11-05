# Archipelago Game Hub

Ein privater Team-Hub für Archipelago-Multiworlds: **eine geteilte Spielebibliothek**, aus der jeder Spieler ein Spiel für die aktuelle Runde auswählt. Die Bibliothek enthält pro Spiel eine YAML-Vorlage, optional eine Custom-APWorld, Cover und eine Anleitung. Der Host generiert daraus eine Multiworld auf seiner Archipelago-Installation.

> **Hosting auf archipelago.gg:** Der Hub **startet derzeit keine Räume automatisch** auf archipelago.gg. Die [offizielle Upload-Seite](https://archipelago.gg/uploads) nimmt lokal erzeugte Seed-ZIPs entgegen, danach erstellt der Host dort den Raum. Eine stabile, öffentliche API für diesen Schritt konnte nicht verifiziert werden. Die Website öffnet den Upload und speichert anschließend den Raumlink.

## Schnellstart unter Windows

1. [Python 3.11–3.13](https://www.python.org/downloads/) installieren (Python 3.14 ist derzeit für Archipelago nicht vorgesehen).
2. Repository klonen oder ZIP entpacken.
3. `.env.example` nach `.env` kopieren. `AP_JOIN_CODE` auf einen langen eigenen Gruppencode setzen. `ARCHIPELAGO_DIR` auf die lokale Archipelago-Installation setzen, zum Beispiel `C:\ProgramData\Archipelago`.
4. `start.bat` ausführen. Beim ersten Start wird `PyYAML` installiert.
5. `http://localhost:8765` öffnen und **zuerst das Host-Konto registrieren**. Es erhält die Host-Rolle.
6. Für Spieler im selben Heimnetz: `AP_BIND=0.0.0.0` in `.env` setzen, den Server neu starten und die Windows-Firewall für Port 8765 im privaten Netzwerk erlauben. Mitspieler öffnen `http://HOST-IP:8765`. **Nicht direkt ins Internet freigeben.**

macOS/Linux: `python3 -m pip install -r requirements.txt && python3 server.py`, beziehungsweise `sh start.sh`.

## Von der Spielebibliothek zur Runde

1. **Jeder registrierte Benutzer** kann ein Spiel hinzufügen. Es braucht einen Titel und eine funktionsfähige YAML-Datei. Zusätzlich möglich: `.apworld`, Cover (PNG/JPG/WebP), Mod-/Setup-Link und Schritt-für-Schritt-Anleitung. Die Bibliothek gehört allen, nicht dem jeweiligen Uploadenden.
2. Die YAML bleibt eine **Vorlage**. In ihr muss `game: NAME`, `name: BeliebigerName` und ein Optionsabschnitt `NAME:` enthalten sein. Beispiel:
   ```yaml
   name: Vorlage
   game: Hollow Knight
   Hollow Knight: {}
   ```
   Dieses minimale Beispiel ist nur zur Demonstration gedacht; gültige Spieloptionen und die tatsächlich installierte World-Version prüfen.
3. Der Host erstellt unter **Meine Runde** eine neue Runde. **Jeder Mitspieler** wählt ein Spiel aus der Bibliothek. Das gleiche Spiel darf mehrfach gewählt werden.
4. Beim Export bzw. bei der Generierung bekommt jeder Slot automatisch den **eigenen Benutzernamen als `name:`**. Die anderen YAML-Optionen bleiben erhalten. Der Hub begrenzt Slotnamen auf **16 Zeichen**, damit Archipelagos Namenskürzung keine Überraschungen verursacht.
5. Mit **YAML & APWorld-Paket** wird ein ZIP zur manuellen Verwendung erstellt. Alternativ startet der Host **Seed serverseitig generieren**, sofern die Archipelago-Installation eingebunden ist.
6. Die erzeugte `AP_*.zip` herunterladen, auf [archipelago.gg/uploads](https://archipelago.gg/uploads) hochladen, dort den Raum erstellen und den Raumlink im Hub speichern. Die Mitspieler öffnen unter **Installation** ihre Setup-Anleitung und verbinden die benötigten Clients.

Die offizielle Dokumentation erklärt [YAMLs, Custom Worlds und das lokale Generieren](https://archipelago.gg/tutorial/Archipelago/setup_en).

## Archipelago-Generator / Voraussetzungen

- Der Host-Computer benötigt Archipelago mit den Worlds, die in der Runde vorkommen. In der Installation enthaltene Worlds benötigen keine zusätzliche `.apworld`.
- **Custom APWorlds sind Python-Code.** Nur vertrauenswürdige Welten hochladen/installieren. Die Generierung verlangt eine ausdrückliche Host-Freigabe. Uploads werden nur auf ZIP-Struktur geprüft – **nicht** auf Schadcode.
- Beim ersten Generieren werden Custom APWorlds in den `custom_worlds`-Ordner der Host-Installation kopiert. Bereits vorhandene abweichende Versionen blockieren die Generierung; keine automatische Überschreibung. Für wechselnde Versionen möglichst separate Archipelago-Installationen nutzen.
- Spiele mit ROM-Abhängigkeiten oder plando-/spezifischen Zusatzdateien können zusätzliche Schritte auf dem Host benötigen. Modifikationen und Patches müssen die Mitspieler selbst installieren.
- Die Generation nutzt `ArchipelagoGenerate.exe` unter Windows oder `Generate.py`, mit isolierten `Players`- und Output-Ordnern und einem 15-Minuten-Limit. Pro Installation läuft maximal ein Build gleichzeitig.
- Kein Seed wird extern hochgeladen und kein Raum wird auf archipelago.gg automatisch gestartet.

## Architektur

```text
Browser → Python HTTP Backend (server.py) → SQLite + lokale Upload-Dateien
                                                └→ core.py (YAML/APWorld Prüfung)
Runde → temporärer YAML-Satz → lokale Archipelago-Installation → AP_*.zip
                                                            ↓
                                               manuell archipelago.gg/uploads
```

Die Weboberfläche ist statisch und ohne JavaScript-Framework gebaut (`web/`). Das Backend benutzt die Python-Standardbibliothek, `PyYAML` ist die einzige Python-Abhängigkeit.

| Ordner/Datei | Zweck |
|---|---|
| `server.py` | HTTP-Server, Benutzer, Runden, Uploads und Generator-Job |
| `core.py` | YAML-Validierung, Slotnamenänderung, APWorld-Prüfung, ZIP-Bundle |
| `web/` | Frontend und responsive Styles |
| `tests/` | Unittests / Integrationstests |
| `.env.example` | Lokale Konfigurationsvorlage |
| `data/` | **Nicht versionierte** SQLite-Datenbank, Uploads und Builds |

### Konfiguration (`.env`)

| Variable | Standard | Bedeutung |
|---|---|---|
| `AP_BIND` | `127.0.0.1` | IP, an der der HTTP-Server lauscht (`0.0.0.0` für LAN) |
| `AP_PORT` | `8765` | HTTP-Port |
| `AP_JOIN_CODE` | leer | Gruppencode für nachfolgende Registrierungen (setzen!) |
| `ARCHIPELAGO_DIR` | Windows: `C:\ProgramData\Archipelago` | Installationsverzeichnis, alternativ im Host-Menü änderbar |
| `AP_DATA_DIR` | `./data` | Datenbank/Uploads/Builds |
| `AP_SECURE_COOKIES` | `0` | Bei HTTPS-Proxy auf `1` setzen |

Die `.env` wird beim Start eingelesen; explizit gesetzte System-Umgebungsvariablen haben Vorrang.

## Sicherheit / Grenzen

**Für eine vertrauenswürdige private Gruppe im LAN entwickelt, nicht für einen offenen Internetbetrieb.** Die Anwendung hat lokale Benutzerkonten (gesalzene PBKDF2-Passworthashes), sessionbasierte Cookies, CSRF-Tokens und Dateigrößen-/Dateitypprüfungen, ist aber **kein öffentlich gehärteter Dienst**. Für Internetzugriff wären unter anderem HTTPS/TLS, sicherer Reverse-Proxy, Ratenbegrenzung, Upload-Isolation, getrennte Worker und weitere Zugriffsprüfungen notwendig.

- Daten und hochgeladene Binärdateien werden lokal gespeichert, **nicht in GitHub**. Sie sind durch `.gitignore` ausgeschlossen.
- Achtung: Repository-Code gehört in Git; Spiel-Dateien/ROMs/Mods nur nutzen, wenn Berechtigung und Lizenz das erlauben. **Keine ROMs hochladen.**
- Vor Einbindung fremder `.apworld` deren Quelle und Versionskompatibilität prüfen.
- Ein späterer automatischer Room-Upload wäre nur über einen offiziell dokumentierten und autorisierten Endpunkt oder eine eigene Server-Infrastruktur sinnvoll.

## Tests

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

GitHub Actions führt die Tests bei Push und Pull Request aus.

## GitHub-Repository erstellen

In GitHub ein **leeres privates Repository** namens `archipelago-game-hub` anlegen (ohne zusätzliche README). Dann im Projektordner:

```bash
git init
git add .
git commit -m "Initial Archipelago Game Hub"
git branch -M main
git remote add origin https://github.com/DEIN-NAME/archipelago-game-hub.git
git push -u origin main
```

Falls GitHub im Chat mit Schreibzugriff zur Verfügung steht, kann das Repository alternativ direkt darüber angelegt werden. Dieser Download stellt zunächst alle benötigten Dateien bereit.