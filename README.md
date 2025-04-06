# Discord Bot Project

Een modulair en uitbreidbaar Discord bot project met GPT-integraties en Google Drive synchronisatie.

## Overzicht

Deze bot is ontworpen om gebruikers te ondersteunen met verschillende interactieve functies, zoals coaching via `/growthcheckin`, kennisopbouw met `/learn_topic`, en het genereren van captions via `/create_caption`. Het project is modulair opgebouwd, zodat nieuwe features eenvoudig kunnen worden toegevoegd en bestaande modules makkelijk aangepast kunnen worden.

## Projectstructuur
. ├── cogs/ # Legacy bestanden en command modules ├── gpt/ # GPT-integraties, helper functies en dataset loaders │ ├── helpers.py # Centrale GPT logica (ask_gpt, log_gpt_success, log_gpt_error) │ └── dataset_loader.py # Laadt topic data uit de lokale prompts folder ├── utils/ # Hulpfuncties zoals Drive synchronisatie │ └── drive_sync.py # Haalt PDF's op en parsed ze van Google Drive ├── requirements.txt # Projectafhankelijkheden (o.a. pydrive2, PyMuPDF) ├── README.md # Deze README └── CHANGELOG.md # Documentatie van wijzigingen

## Installatie

1. **Clone de repository:**
   ```bash
   git clone https://github.com/jouw_gebruikersnaam/discord-bot-project.git
   cd discord-bot-project
   
2. Installeer de benodigde pakketten:
  bash
  Copy
  pip install -r requirements.txt

3. Configureer de bot:
 Voeg je Discord token, Google Drive API credentials en andere benodigde configuraties toe aan de environment variabelen of een configuratiebestand.

4. Start de bot:
  python bot.py

## Functionaliteiten
``` plaintext
- `/growthcheckin`: Biedt zachte coaching met GPT-ondersteuning voor doelen, obstakels en emoties.
- `/learn_topic`: Een hybride kenniscommando dat informatie uit .md bestanden of Drive PDF's haalt als context.
- `/create_caption`: Genereert style-based captions voor sociale media, gebaseerd op GPT.
```

# Contributing
Wij verwelkomen bijdragen van andere ontwikkelaars! Als je wilt bijdragen:

- Fork de repository.
- Maak een feature branch: git checkout -b feature/naam-van-je-feature
- Commit je wijzigingen: git commit -am 'Voeg een nieuwe feature toe'
- Push naar de branch: git push origin feature/naam-van-je-feature
- Open een Pull Request
- Zorg ervoor dat je de projectrichtlijnen en de bestaande codeconventies volgt.

# Licentie
Dit project is gelicentieerd onder de MIT License.

# Contact
Voor vragen of suggesties kun je contact opnemen via bryan.dhaen@gmail.com of een issue openen op GitHub.

