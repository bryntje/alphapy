# Google Cloud Security Best Practices

Dit document beschrijft de security best practices voor Google Cloud credentials en API keys binnen het Alphapy project, conform de aanbevelingen van Google Cloud Security.

## Overzicht

Alphapy gebruikt Google Cloud services voor:
- **Google Drive API**: PDF documenten lezen via service account credentials

Alle credentials worden beheerd via **Google Cloud Secret Manager** in productie, met fallback naar environment variables voor lokale development.

## Credential Lifecycle Management

### 1. Zero-Code Storage ✅

**Status**: Geïmplementeerd

- ✅ Credentials worden **nooit** gecommit naar source code of version control
- ✅ `.gitignore` sluit `.env` en `credentials/` uit
- ✅ Productie gebruikt **Google Cloud Secret Manager** voor credential storage
- ✅ Lokale development gebruikt environment variables (fallback)

**Implementatie**:
- `utils/gcp_secrets.py`: Helper voor Secret Manager access met caching
- `utils/drive_sync.py`: Laadt credentials vanuit Secret Manager of environment variable
- Configuratie via `GOOGLE_PROJECT_ID` en `GOOGLE_SECRET_NAME` environment variables

### 2. Secret Manager Setup

**Voor productie deployments**:

1. **Maak secret aan in Secret Manager**:
   ```bash
   # Via gcloud CLI
   echo -n '{"type":"service_account",...}' | \
     gcloud secrets create alphapy-google-credentials \
     --data-file=- \
     --project=YOUR_PROJECT_ID
   ```

2. **Configureer environment variables**:
   ```bash
   GOOGLE_PROJECT_ID=your-gcp-project-id
   GOOGLE_SECRET_NAME=alphapy-google-credentials  # Optioneel, default gebruikt deze naam
   ```

3. **Grant access aan service account**:
   ```bash
   gcloud secrets add-iam-policy-binding alphapy-google-credentials \
     --member="serviceAccount:YOUR_SERVICE_ACCOUNT@PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/secretmanager.secretAccessor" \
     --project=YOUR_PROJECT_ID
   ```

**Voor lokale development**:
- Gebruik `GOOGLE_CREDENTIALS_JSON` environment variable
- Secret Manager wordt automatisch overgeslagen als `GOOGLE_PROJECT_ID` niet is gezet

### 3. Disable Dormant Keys

**Handmatige actie vereist in GCP Console**:

1. Ga naar **"APIs & Services" > "Credentials"**
2. Review alle API keys en service account keys
3. Identificeer keys zonder activiteit (30+ dagen)
4. **Decommission inactive keys**:
   - Klik op de key
   - Selecteer "Delete" of "Disable"
   - Bevestig deactivering

**Audit procedure** (maandelijks):
- Check "APIs & Services" > "Credentials" voor inactive keys
- Review Cloud Audit Logs voor key usage patterns
- Document alle deactivated keys in project changelog

### 4. Enforce API Restrictions

**Handmatige configuratie in GCP Console**:

Voor **API Keys**:
1. Ga naar **"APIs & Services" > "Credentials"**
2. Selecteer een API key
3. Klik op "Restrict key"
4. **API restrictions**:
   - Selecteer "Restrict key"
   - Kies alleen de benodigde APIs (bijv. "Drive API")
   - Sla op
5. **Application restrictions** (indien van toepassing):
   - **IP addresses**: Voeg toegestane IP ranges toe
   - **HTTP referrers**: Voeg toegestane referrer URLs toe
   - **Android apps**: Voeg package names toe
   - **iOS apps**: Voeg bundle IDs toe

Voor **Service Account Keys**:
- Service accounts hebben automatisch beperkte scopes (zie code: `drive.readonly`)
- Geen extra API restrictions nodig (scopes zijn voldoende)

**Huidige implementatie**:
- ✅ Service account gebruikt alleen `https://www.googleapis.com/auth/drive.readonly` scope
- ⚠️ **TODO**: Configureer API key restrictions in GCP Console indien API keys worden gebruikt

### 5. Apply Least Privilege

**Service Account Permissions**:

**Huidige scopes** (geïmplementeerd in code):
- ✅ `https://www.googleapis.com/auth/drive.readonly` - Alleen lezen, geen schrijven

**IAM Permissions Review**:

1. **Gebruik IAM Recommender**:
   ```bash
   # Via gcloud CLI
   gcloud recommender recommendations list \
     --recommender=google.iam.policy.Recommender \
     --project=YOUR_PROJECT_ID \
     --location=global
   ```

2. **Review unused permissions**:
   - Ga naar **"IAM & Admin" > "IAM"**
   - Selecteer service account
   - Review toegewezen rollen
   - Verwijder ongebruikte rollen

3. **Minimale rollen voor Secret Manager**:
   - `roles/secretmanager.secretAccessor` - Alleen lezen van secrets
   - Geen `roles/secretmanager.admin` of `roles/secretmanager.secretAccessor` op project-level

**Huidige implementatie**:
- ✅ Service account gebruikt minimale scope (`drive.readonly`)
- ⚠️ **TODO**: Review IAM roles via IAM Recommender en verwijder unused permissions

### 6. Mandatory Rotation

**Organization Policies** (moet worden geconfigureerd door GCP admin):

1. **Key Expiry Policy**:
   ```bash
   # Set maximum key lifetime (bijv. 90 dagen)
   gcloud resource-manager org-policies set \
     iam.serviceAccountKeyExpiryHours \
     --organization=ORGANIZATION_ID \
     --policy-file=policy.json
   ```
   
   Policy file (`policy.json`):
   ```json
   {
     "spec": {
       "rules": [{
         "values": {
           "allowedValues": ["2160"]  # 90 dagen in uren
         }
       }]
     }
   }
   ```

2. **Disable Key Creation** (als keys niet nodig zijn):
   ```bash
   gcloud resource-manager org-policies set \
     iam.disableServiceAccountKeyCreation \
     --organization=ORGANIZATION_ID \
     --enforce
   ```

**Voor dit project**:
- ⚠️ **TODO**: Configureer `iam.serviceAccountKeyExpiryHours` policy (aanbevolen: 90 dagen)
- Service account keys worden gebruikt, dus disable policy is niet van toepassing

**Rotation procedure** (wanneer key expireert):
1. Genereer nieuwe service account key in GCP Console
2. Update secret in Secret Manager:
   ```bash
   echo -n 'NEW_CREDENTIALS_JSON' | \
     gcloud secrets versions add alphapy-google-credentials \
     --data-file=-
   ```
3. Cache wordt automatisch geïnvalideerd na TTL (1 uur)
4. Oude key versie kan worden verwijderd na verificatie

## Operational Safeguards

### 1. Essential Contacts

**Configuratie in GCP Console**:

1. Ga naar **"IAM & Admin" > "Essential Contacts"**
2. Voeg contacten toe voor:
   - **Security**: Security team email
   - **Billing**: Finance team email
   - **Technical**: DevOps team email
3. Selecteer notification categories:
   - Security notifications
   - Billing notifications
   - Technical notifications

**Voor dit project**:
- ⚠️ **TODO**: Configureer Essential Contacts met juiste email adressen

### 2. Billing Anomaly and Budget Alerts

**Configuratie in GCP Console**:

1. **Budget Alerts**:
   - Ga naar **"Billing" > "Budgets & alerts"**
   - Maak nieuwe budget alert
   - Stel threshold in (bijv. 80% van maandelijks budget)
   - Voeg email notificaties toe

2. **Anomaly Detection**:
   - Ga naar **"Billing" > "Budgets & alerts"**
   - Enable "Anomaly detection"
   - Configureer threshold (bijv. 150% van gemiddelde daily spend)
   - Voeg email notificaties toe

**Voor dit project**:
- ⚠️ **TODO**: Configureer budget alerts en anomaly detection
- ⚠️ **TODO**: Stel threshold in op basis van verwacht gebruik

## Security Checklist

### Code-Level (Geïmplementeerd) ✅

- [x] Credentials niet gecommit in source code
- [x] Secret Manager integration met caching
- [x] Fallback naar environment variables voor local dev
- [x] Error handling voor Secret Manager failures
- [x] Logging voor security events (welke methode wordt gebruikt)
- [x] Minimale scopes (`drive.readonly`)

### Infrastructure-Level (Handmatig te configureren) ⚠️

- [ ] API key restrictions geconfigureerd (indien van toepassing)
- [ ] Service account IAM permissions gereviewed via IAM Recommender
- [ ] Unused permissions verwijderd
- [ ] Key rotation policy geconfigureerd (`iam.serviceAccountKeyExpiryHours`)
- [ ] Essential Contacts geconfigureerd
- [ ] Budget alerts geconfigureerd
- [ ] Anomaly detection enabled
- [ ] Dormant keys audit uitgevoerd (30+ dagen inactief)

## Monitoring en Alerting

### Secret Manager Access Logs

Monitor Secret Manager access via Cloud Audit Logs:

```bash
# View Secret Manager access logs
gcloud logging read "resource.type=secretmanager.googleapis.com/Secret" \
  --project=YOUR_PROJECT_ID \
  --limit=50
```

### Anomaly Detection

- Monitor voor onverwachte Secret Manager access patterns
- Alert op failed authentication attempts
- Review logs maandelijks voor security events

## Incident Response

Als credentials gecompromitteerd zijn:

1. **Immediate Actions**:
   - Disable de gecompromitteerde key in GCP Console
   - Rotate secret in Secret Manager
   - Clear cache in applicatie (restart of `clear_cache()` call)

2. **Investigation**:
   - Review Cloud Audit Logs voor unauthorized access
   - Check voor onverwachte API calls
   - Document incident in security log

3. **Prevention**:
   - Review security configuraties
   - Update IAM permissions indien nodig
   - Verifieer dat alle best practices zijn gevolgd

## Referenties

- [Google Cloud Secret Manager Documentation](https://cloud.google.com/secret-manager/docs)
- [Google Cloud Security Best Practices](https://cloud.google.com/security/best-practices)
- [IAM Recommender](https://cloud.google.com/iam/docs/recommender-overview)
- [Service Account Key Management](https://cloud.google.com/iam/docs/service-accounts)
