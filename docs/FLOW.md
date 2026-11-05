# Rundenerstellung (technisches Ablaufdiagramm)

\`\`\`mermaid
flowchart TD
  A[Benutzer meldet sich an] --> B[Gemeinsame Spielebibliothek]
  B --> C[Spiel mit YAML und optional APWorld auswählen]
  C --> D[Spielauswahl pro Runde speichern]
  D --> E{Host startet Generierung?}
  E -- Nein --> F[YAML und APWorld Bundle exportieren]
  E -- Ja --> G[Host prüft und genehmigt Custom APWorlds]
  G --> H[Name in jeder YAML auf Benutzername setzen]
  H --> I[APWorld Versionen abgleichen]
  I --> J[Lokaler Archipelago Generator]
  J --> K[AP ZIP herunterladen]
  K --> L[Manueller Upload auf archipelago.gg]
  L --> M[Create Room auf archipelago.gg]
  M --> N[Raumlink im Hub speichern]
  N --> O[Mitspieler installieren Mods und verbinden Clients]
\`\`\`

Die Website hostet **keinen** externen Archipelago-Server. \`archipelago.gg\` erstellt den Raum nach dem Upload der generierten Datei. Ein automatisierter Cloud-Raumstart ist derzeit bewusst nicht implementiert.
