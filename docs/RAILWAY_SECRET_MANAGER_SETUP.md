# Railway Secret Manager Setup Guide

Stap-voor-stap gids voor het configureren van Google Cloud Secret Manager op Railway.

## Overzicht

Deze gids helpt je om Google Drive credentials veilig op te slaan in Secret Manager en deze te gebruiken vanuit Railway, in plaats van credentials direct in Railway environment variables op te slaan.

## Vereisten

- Google Cloud Project met Secret Manager API enabled
- Railway account met toegang tot je project
- Service account credentials JSON (voor Google Drive)

## Stap 1: Secret aanmaken in Google Cloud Secret Manager

### 1.1 Via Google Cloud Console

1. Ga naar [Google Cloud Console](https://console.cloud.google.com/)
2. Selecteer je project (of maak een nieuw project aan)
3. Ga naar **"Security" > "Secret Manager"**
4. Klik op **"+ CREATE SECRET"**
5. Vul in:
   - **Name**: `alphapy-google-credentials` (of gebruik `GOOGLE_SECRET_NAME` als je een andere naam wilt)
   - **Secret value**: Plak je volledige service account credentials JSON
   - **Version**: Laat "Automatic" staan
6. Klik op **"CREATE SECRET"**

### 1.2 Via gcloud CLI (alternatief)

```bash
# Zorg dat je ingelogd bent
gcloud auth login

# Set je project
gcloud config set project YOUR_PROJECT_ID

# Maak het secret aan
echo -n '{"type":"service_account","project_id":"...","private_key_id":"...","private_key":"...","client_email":"...","client_id":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"..."}' | \
  gcloud secrets create alphapy-google-credentials \
  --data-file=- \
  --project=YOUR_PROJECT_ID
```

**Belangrijk:** Vervang `YOUR_PROJECT_ID` met je echte GCP project ID.

## Stap 2: Railway Service Account Toegang Geven

Railway gebruikt een service account om toegang te krijgen tot externe services. Er zijn twee manieren om dit te configureren:

### Optie A: Railway's Service Account (aanbevolen voor Railway-hosted)

Als Railway een service account gebruikt, moet je deze toegang geven:

1. **Vind Railway's Service Account Email**:
   - Ga naar Railway dashboard → je project → Settings → Variables
   - Kijk of er een `RAILWAY_SERVICE_ACCOUNT_EMAIL` of vergelijkbare variabele is
   - Of gebruik de default Railway service account (meestal iets als `railway@railway.iam.gserviceaccount.com`)

2. **Geef toegang via gcloud CLI**:
   ```bash
   gcloud secrets add-iam-policy-binding alphapy-google-credentials \
     --member="serviceAccount:RAILWAY_SERVICE_ACCOUNT_EMAIL@PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/secretmanager.secretAccessor" \
     --project=YOUR_PROJECT_ID
   ```

3. **Of via Google Cloud Console**:
   - Ga naar Secret Manager → klik op `alphapy-google-credentials`
   - Klik op **"PERMISSIONS"** tab
   - Klik op **"ADD PRINCIPAL"**
   - Voer Railway service account email in
   - Selecteer rol: **"Secret Manager Secret Accessor"**
   - Klik **"SAVE"**

### Optie B: Application Default Credentials (ADC) - voor lokale testing

Voor lokale development kun je Application Default Credentials gebruiken:

```bash
# Login met je persoonlijke account
gcloud auth application-default login

# Dit maakt credentials aan die automatisch worden gebruikt
```

**Let op:** Dit werkt alleen lokaal. Voor Railway moet je Optie A gebruiken.

### Optie C: Service Account Key voor Railway (als Optie A niet werkt)

Als Railway geen service account heeft, kun je een service account key maken en deze als Railway secret gebruiken:

1. **Maak service account aan**:
   ```bash
   gcloud iam service-accounts create railway-secret-accessor \
     --display-name="Railway Secret Accessor" \
     --project=YOUR_PROJECT_ID
   ```

2. **Geef toegang tot Secret Manager**:
   ```bash
   gcloud secrets add-iam-policy-binding alphapy-google-credentials \
     --member="serviceAccount:railway-secret-accessor@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/secretmanager.secretAccessor" \
     --project=YOUR_PROJECT_ID
   ```

3. **Maak service account key**:
   ```bash
   gcloud iam service-accounts keys create railway-key.json \
     --iam-account=railway-secret-accessor@YOUR_PROJECT_ID.iam.gserviceaccount.com
   ```

4. **Zet key als Railway environment variable**:
   - Ga naar Railway → je project → Variables
   - Voeg toe: `GOOGLE_APPLICATION_CREDENTIALS_JSON` met de inhoud van `railway-key.json`
   - **Let op:** Dit is alleen voor authenticatie met Secret Manager, niet voor Drive credentials zelf

## Stap 3: Environment Variables Configureren op Railway

### 3.1 Via Railway Dashboard

**Belangrijk:** De variabelen die je ziet (zoals `RAILWAY_PUBLIC_DOMAIN`, `RAILWAY_PROJECT_ID`, etc.) zijn **system variables** die Railway automatisch beschikbaar stelt. Je moet **custom variables** toevoegen voor Secret Manager.

**Stappen:**

1. Ga naar je Railway project
2. Klik op je **service** (waar Alphapy draait) - niet op "Variables" in het project menu
3. Ga naar de **"Variables"** tab in je service (niet de system variables)
4. Klik op **"+ New Variable"** of **"Add Variable"**
5. Voeg de volgende **custom environment variables** toe:

```bash
# Verplicht voor Secret Manager
GOOGLE_PROJECT_ID=your-gcp-project-id

# Optioneel (als je een andere secret naam gebruikt)
# Default is "alphapy-google-credentials" als je dit niet zet
GOOGLE_SECRET_NAME=alphapy-google-credentials
```

**Waar vind je dit?**
- Railway Dashboard → Je Project → Je Service (bijv. "alphapy-bot") → **Variables** tab
- Dit is een andere sectie dan de system variables die je hierboven ziet
- Je custom variables verschijnen onderaan de lijst, na de system variables

**Tip:** Je kunt `RAILWAY_PROJECT_ID` en `RAILWAY_SERVICE_NAME` gebruiken voor logging/debugging, maar deze zijn niet nodig voor Secret Manager configuratie.

### 3.2 Verwijder Oude Credentials (optioneel maar aanbevolen)

Als je `GOOGLE_CREDENTIALS_JSON` in Railway hebt staan, kun je deze nu verwijderen:
- De code gebruikt automatisch Secret Manager als `GOOGLE_PROJECT_ID` is gezet
- Dit verbetert security omdat credentials niet meer in Railway environment variables staan

**Let op:** Verwijder `GOOGLE_CREDENTIALS_JSON` alleen als je zeker weet dat Secret Manager werkt!

### 3.3 Via Railway CLI (alternatief)

```bash
# Installeer Railway CLI als je die nog niet hebt
npm i -g @railway/cli

# Login
railway login

# Link naar je project
railway link

# Set environment variables
railway variables set GOOGLE_PROJECT_ID=your-gcp-project-id
railway variables set GOOGLE_SECRET_NAME=alphapy-google-credentials
```

## Stap 4: Verifieer Setup

### 4.1 Check Logs

Na deployment, check de Railway logs voor:

```
🔐 Attempting to load Google credentials from Secret Manager (secret: alphapy-google-credentials)
✅ Loaded Google credentials from Secret Manager
✅ Google Drive service account authentication successful
```

Als je deze berichten ziet, werkt Secret Manager correct!

### 4.2 Test Drive Functionaliteit

Test of Google Drive features werken:
- Gebruik een command die Drive gebruikt (bijv. `/learn_topic` met Drive content)
- Check logs voor errors

### 4.3 Troubleshooting

**Error: "Permission denied" of "Access denied"**
- Check of Railway service account toegang heeft tot het secret
- Verifieer IAM permissions in GCP Console

**Error: "Secret not found"**
- Check of secret naam overeenkomt met `GOOGLE_SECRET_NAME`
- Verifieer dat secret bestaat in het juiste project

**Error: "Project not found"**
- Check of `GOOGLE_PROJECT_ID` correct is
- Verifieer dat project bestaat en Secret Manager API enabled is

**Fallback naar environment variable**
- Als Secret Manager faalt, valt code terug op `GOOGLE_CREDENTIALS_JSON`
- Check logs voor: "Loading Google Service Account credentials from environment variable"
- Dit betekent dat Secret Manager niet werkt, maar fallback wel

## Stap 5: Enable Secret Manager API (als nodig)

Als je errors krijgt over API niet enabled:

```bash
# Enable Secret Manager API
gcloud services enable secretmanager.googleapis.com --project=YOUR_PROJECT_ID
```

Of via Console:
1. Ga naar **"APIs & Services" > "Library"**
2. Zoek "Secret Manager API"
3. Klik **"ENABLE"**

## Security Best Practices

Na setup, volg deze best practices:

1. **Rotate credentials regelmatig**:
   - Maak nieuwe service account key
   - Update secret in Secret Manager
   - Cache wordt automatisch geïnvalideerd na 1 uur

2. **Monitor access**:
   - Check Cloud Audit Logs voor Secret Manager access
   - Alert op onverwachte access patterns

3. **Least Privilege**:
   - Railway service account heeft alleen `secretmanager.secretAccessor` rol
   - Geen admin of andere permissions

4. **Backup**:
   - Bewaar service account key veilig (niet in git!)
   - Document rotation procedure

## Samenvatting Checklist

- [ ] Secret aangemaakt in Secret Manager (`alphapy-google-credentials`)
- [ ] Railway service account heeft `roles/secretmanager.secretAccessor` op secret
- [ ] Secret Manager API enabled in GCP project
- [ ] `GOOGLE_PROJECT_ID` gezet in Railway environment variables
- [ ] `GOOGLE_SECRET_NAME` gezet (optioneel, default werkt ook)
- [ ] Deployment gedaan en logs gecheckt
- [ ] Drive functionaliteit getest
- [ ] Oude `GOOGLE_CREDENTIALS_JSON` verwijderd (na verificatie)

## Hulp Nodig?

- Check [docs/SECURITY.md](SECURITY.md) voor algemene security best practices
- Check Railway logs voor specifieke errors
- Verifieer GCP IAM permissions in Console
