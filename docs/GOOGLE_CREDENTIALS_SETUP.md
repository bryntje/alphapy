# Google Cloud Credentials Setup Guide

Stap-voor-stap gids voor het aanmaken van nieuwe Google Cloud service account credentials voor Alphapy.

## Overzicht

Je hebt nodig:
1. Een Google Cloud Project (of maak een nieuwe aan)
2. Een Service Account met Drive API toegang
3. Een JSON key file voor authenticatie

## Stap 1: Google Cloud Project

### 1.1 Maak een project aan (of gebruik bestaand)

1. Ga naar [Google Cloud Console](https://console.cloud.google.com/)
2. Klik op het project dropdown (bovenaan naast "Google Cloud")
3. Klik op **"NEW PROJECT"**
4. Vul in:
   - **Project name**: `alphapy-drive-integration` (of kies je eigen naam)
   - **Organization**: Laat leeg of kies je organisatie
5. Klik **"CREATE"**
6. Wacht tot het project is aangemaakt
7. Selecteer het nieuwe project in het dropdown

**Of gebruik een bestaand project:**
- Selecteer je bestaande project uit het dropdown

**Note:** Noteer je **Project ID** (niet de naam, maar het ID zoals `drive-integration-456012`)

## Stap 2: Enable Google Drive API

1. In Google Cloud Console, ga naar **"APIs & Services" > "Library"**
2. Zoek naar **"Google Drive API"**
3. Klik op **"Google Drive API"**
4. Klik op **"ENABLE"**
5. Wacht tot de API is enabled

## Stap 3: Maak Service Account

1. Ga naar **"IAM & Admin" > "Service Accounts"**
2. Klik op **"+ CREATE SERVICE ACCOUNT"**
3. Vul in:
   - **Service account name**: `alphapy-drive-reader` (of kies je eigen naam)
   - **Service account ID**: Wordt automatisch gegenereerd (bijv. `alphapy-drive-reader`)
   - **Description**: `Service account for Alphapy bot to read PDFs from Google Drive`
4. Klik **"CREATE AND CONTINUE"**

## Stap 4: Geef Permissions (optioneel)

Voor alleen lezen van Drive is geen extra IAM role nodig - we gebruiken alleen API scopes.

1. Laat **"Grant this service account access to project"** leeg (niet nodig)
2. Klik **"CONTINUE"**
3. Klik **"DONE"**

## Stap 5: Maak JSON Key

1. In de **Service Accounts** lijst, klik op je nieuwe service account
2. Ga naar de **"KEYS"** tab
3. Klik op **"ADD KEY" > "Create new key"**
4. Selecteer **"JSON"**
5. Klik **"CREATE"**
6. Een JSON bestand wordt automatisch gedownload

**Belangrijk:** 
- Bewaar dit bestand veilig - het bevat je private key
- Voeg het **NOOIT** toe aan git (staat al in `.gitignore`)
- Als je het verliest, moet je een nieuwe key maken

## Stap 6: Geef Drive Access

De service account heeft nu toegang tot Google Cloud, maar nog niet tot specifieke Drive bestanden.

### Optie A: Share Drive Folder/File met Service Account

1. Open Google Drive
2. Klik rechts op de folder/file die je wilt delen
3. Klik **"Share"**
4. Voeg het **service account email** toe (bijv. `alphapy-drive-reader@drive-integration-456012.iam.gserviceaccount.com`)
5. Geef **"Viewer"** rechten (alleen lezen)
6. Klik **"Send"**

**Service Account Email vinden:**
- Google Cloud Console > IAM & Admin > Service Accounts
- Klik op je service account
- Het email staat bovenaan (bijv. `alphapy-drive-reader@PROJECT_ID.iam.gserviceaccount.com`)

### Optie B: Share hele Drive (niet aanbevolen)

Als je wilt dat de service account alle Drive bestanden kan lezen:
1. Share je hele Google Drive met het service account email
2. Geef "Viewer" rechten

**Let op:** Dit geeft toegang tot alle bestanden - gebruik alleen als nodig.

## Stap 7: Configureer in Alphapy

### Voor Lokale Development (.env)

1. Open het gedownloade JSON bestand
2. Kopieer de **volledige** JSON inhoud
3. Open je `.env` file
4. Voeg toe (op één regel, zonder extra quotes):
   ```bash
   GOOGLE_CREDENTIALS_JSON={"type":"service_account","project_id":"...","private_key_id":"...","private_key":"...","client_email":"...","client_id":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"..."}
   ```

**Belangrijk:** 
- Zet de hele JSON op **één regel**
- Gebruik **geen** extra quotes rond de JSON (`""` of `''`)
- Of gebruik single quotes: `GOOGLE_CREDENTIALS_JSON='{...}'`

**Voorbeeld:**
```bash
GOOGLE_CREDENTIALS_JSON={"type":"service_account","project_id":"drive-integration-456012","private_key_id":"abc123","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n","client_email":"alphapy-drive-reader@drive-integration-456012.iam.gserviceaccount.com","client_id":"123456789","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"https://www.googleapis.com/robot/v1/metadata/x509/alphapy-drive-reader%40drive-integration-456012.iam.gserviceaccount.com"}
```

### Voor Productie (Secret Manager)

Als je Secret Manager gebruikt:

1. **Maak secret aan in Secret Manager:**
   ```bash
   # Via gcloud CLI
   cat your-service-account-key.json | \
     gcloud secrets create alphapy-google-credentials \
     --data-file=- \
     --project=YOUR_PROJECT_ID
   ```

2. **Of via Google Cloud Console:**
   - Ga naar **"Security" > "Secret Manager"**
   - Klik **"+ CREATE SECRET"**
   - **Name**: `alphapy-google-credentials`
   - **Secret value**: Plak de volledige JSON inhoud
   - Klik **"CREATE SECRET"**

3. **Geef Railway/service toegang:**
   - Zie [docs/RAILWAY_SECRET_MANAGER_SETUP.md](RAILWAY_SECRET_MANAGER_SETUP.md)

## Stap 8: Test de Configuratie

1. Herstart je bot
2. Check de logs voor:
   ```
   🔍 Verifying Google Drive configuration...
   🔐 Loading Google Service Account credentials from environment variable
   ✅ Google Drive service account authentication successful
   ✅ Google Drive configuration verified and ready
   ```

3. Test met `/learn_topic` command:
   - Gebruik een topic die een PDF in Drive heeft
   - Check of de bot de PDF kan lezen

## Troubleshooting

### Error: "Permission denied" of "Access denied"
- **Oplossing**: Share de Drive folder/file met het service account email
- Check of je het juiste email gebruikt (met `.iam.gserviceaccount.com`)

### Error: "Invalid credentials" of "JSON decode error"
- **Oplossing**: Check of de JSON correct is geformatteerd in `.env`
- Zorg dat de hele JSON op één regel staat
- Verwijder extra quotes aan het begin/einde

### Error: "Drive API not enabled"
- **Oplossing**: Enable Google Drive API in Google Cloud Console
- Ga naar APIs & Services > Library > Google Drive API > ENABLE

### Error: "Service account not found"
- **Oplossing**: Check of je het juiste project gebruikt
- Verifieer dat de service account bestaat in het project

## Security Best Practices

1. **Rotate keys regelmatig** (elke 90 dagen aanbevolen)
2. **Gebruik Secret Manager in productie** (niet environment variables)
3. **Geef minimale rechten** (alleen "Viewer" op specifieke folders)
4. **Monitor access** via Cloud Audit Logs
5. **Verwijder oude keys** wanneer je nieuwe maakt

## Samenvatting Checklist

- [ ] Google Cloud Project aangemaakt/geselecteerd
- [ ] Google Drive API enabled
- [ ] Service Account aangemaakt
- [ ] JSON key gedownload
- [ ] Drive folder/file gedeeld met service account email
- [ ] JSON toegevoegd aan `.env` (lokaal) of Secret Manager (productie)
- [ ] Bot herstart en logs gecheckt
- [ ] Test met `/learn_topic` command

## Hulp Nodig?

- [Google Cloud Service Accounts Documentation](https://cloud.google.com/iam/docs/service-accounts)
- [Google Drive API Documentation](https://developers.google.com/drive/api)
- [Alphapy Security Guide](SECURITY.md)
