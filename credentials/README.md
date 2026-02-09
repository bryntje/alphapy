# Credentials Directory

Store private service credentials in this folder, such as `credentials.json` for Google integrations. These files should never be committed to version control.

## Google Cloud Credentials

### Production (Recommended): Google Cloud Secret Manager

For production deployments, credentials are stored securely in **Google Cloud Secret Manager**:

1. **Create secret in Secret Manager**:
   ```bash
   # Via gcloud CLI
   echo -n '{"type":"service_account",...}' | \
     gcloud secrets create alphapy-google-credentials \
     --data-file=- \
     --project=YOUR_PROJECT_ID
   ```

2. **Configure environment variables**:
   ```bash
   GOOGLE_PROJECT_ID=your-gcp-project-id
   GOOGLE_SECRET_NAME=alphapy-google-credentials  # Optional, defaults to this name
   ```

3. **Grant access to service account**:
   ```bash
   gcloud secrets add-iam-policy-binding alphapy-google-credentials \
     --member="serviceAccount:YOUR_SERVICE_ACCOUNT@PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/secretmanager.secretAccessor" \
     --project=YOUR_PROJECT_ID
   ```

See [docs/SECURITY.md](../docs/SECURITY.md) for detailed security best practices.

### Local Development: Environment Variable

For local development, you can use the `GOOGLE_CREDENTIALS_JSON` environment variable:

1. **Get service account credentials**:
   - Download JSON key from GCP Console
   - Or use existing `credentials.json` file

2. **Set environment variable**:
   ```bash
   # Option 1: Export as JSON string
   export GOOGLE_CREDENTIALS_JSON='{"type":"service_account",...}'
   
   # Option 2: Load from file (in .env)
   GOOGLE_CREDENTIALS_JSON=$(cat credentials/credentials.json | jq -c)
   ```

3. **Fallback behavior**:
   - If `GOOGLE_PROJECT_ID` is not set, the bot will use `GOOGLE_CREDENTIALS_JSON`
   - If `GOOGLE_PROJECT_ID` is set, Secret Manager is tried first, then falls back to env var

### Legacy: File-based Credentials (Deprecated)

The old file-based approach is still supported but **not recommended**:

1. Copy the credential file into this directory on your local machine.
2. Keep the original filename (e.g., `credentials.json`) so the bot can load it.
3. If you need to share defaults, create a sanitized template like `credentials.example.json` instead of the real file.

> **Security Reminder**: `.gitignore` already excludes this directory, but if a secret was committed earlier you must rotate that credential because it may exist in Git history.

## Security Best Practices

- ✅ **Production**: Always use Google Cloud Secret Manager
- ✅ **Local Dev**: Use environment variables, never commit credentials
- ✅ **Rotation**: Rotate credentials regularly (see [docs/SECURITY.md](../docs/SECURITY.md))
- ❌ **Never**: Commit credentials to version control
- ❌ **Never**: Share credentials via insecure channels
