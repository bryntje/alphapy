# Testplan voor Innersync Core - Vision Root & Enhanced Telemetry

## Toegang & voorbereiding
1. Gebruik de meest recente build (production URL of actuele staging-link) en zorg dat alle noodzakelijke env-variabelen zijn ingesteld.
2. Vraag een Supabase testaccount + rolrechten op bij het team; bevestig dat audit/telemetry tabellen gevuld mogen worden.
3. Zorg dat `vision_blueprints` tabel is gedeployed naar shared database met RLS policies.
4. Leeg de browsercache vóór elke testcyclus zodat onboarding, statuspagina en API's schoon starten.

## 1. Dashboard & Statuspagina
- Bezoek `/` en controleer hero, navigatie, CTA's en alle "status highlights".
- Beweeg over HeroGlow/Halo componenten; noteer haperingen of kleurafwijkingen.
- Open `/status` en controleer de Snapshot kaarten (subsystemen, trends, incidents). Hover, tooltips en animaties moeten soepel verlopen.
- Controleer links (SiteHeader/Footer) en externe verwijzingen (`links.ts`) op correcte URLs.
- **NIEUW:** Bezoek `/dashboard/vision` en verificeer Vision Root UI functionaliteit.

## 2. API's & Telemetrie
- **GET /api/metrics**
  1. Roep de route aan zonder auth: verwacht 200 + JSON snapshot (subsystemen + trends).
  2. Controleer dat `telemetry.summary`, `telemetry.subsystem_snapshots` en `telemetry.trends` nieuwe rijen krijgen.
  3. Forceer meerdere requests kort na elkaar; bevestig dat trends alleen de nieuwste punten bijschrijven.
- **POST /api/metrics (indien aanwezig)**: zelfde controles, inclusief foutpad (bijv. ontbrekende service key).
- **/api/health**: moet service, versie en uptime tonen.

### **NIEUW: Vision CRUD API Tests (`/api/vision`)**
- **GET /api/vision**
  1. Test zonder auth header: verwacht 401 Unauthorized.
  2. Test met ongeldige JWT: verwacht 401 Unauthorized.
  3. Test met geldige JWT: verwacht 200 + `{ visions: VisionBlueprint[] }`.
  4. Controleer dat alleen user's eigen visions worden geretourneerd (RLS test).
- **POST /api/vision**
  1. Test zonder auth: verwacht 401.
  2. Test met `{"vision_text": "Test vision"}`: verwacht 201 + nieuwe VisionBlueprint.
  3. Controleer dat `vision.create` metric stijgt in telemetry.
- **PUT /api/vision**
  1. Test update van bestaande vision: verwacht 200 + bijgewerkte VisionBlueprint.
  2. Controleer dat `vision.update` metric stijgt.
- **DELETE /api/vision?id=<uuid>**
  1. Test delete van eigen vision: verwacht 200 + `{ success: true }`.
  2. Test delete van niet-bestaande vision: verwacht 404.
  3. Test delete van andere user's vision: verwacht 403 (RLS).
  4. Controleer dat `vision.delete` metric stijgt.

### **NIEUW: Enhanced Telemetry API (`/api/telemetry`)**
- **GET /api/telemetry**
  1. Controleer dat response alle 10 nieuwe metrics bevat:
     - `visionCreates`, `visionUpdates`, `visionDeletes`, `visionViews`
     - `reflectionCreates`, `reflectionUpdates`, `reflectionViews`
     - `habitCreates`, `habitCompletes`, `habitDeletes`
  2. Verificeer dat metrics real-time worden bijgewerkt.
  3. Test user-scoping: metrics moeten alleen voor ingelogde user gelden.

## 3. Database Schema & RLS Tests
- **Vision Blueprints Table**
  1. Controleer dat `vision_blueprints` tabel bestaat in shared database.
  2. Verificeer index `vision_user_date_idx` op `(user_id, date desc)`.
  3. Test RLS policies: alleen eigenaar kan eigen visions zien/bewerken.
  4. Test data types: `id` (uuid), `user_id` (uuid), `date` (date), `vision_text` (text).

- **Enhanced Telemetry Metrics**
  1. Controleer dat alle nieuwe metrics bestaan in telemetry.trends:
     - `vision.create`, `vision.update`, `vision.delete`, `vision.view`
     - `reflection.create`, `reflection.update`, `reflection.view`
     - `habit.create`, `habit.complete`, `habit.delete`
  2. Test metric aggregation: nieuwe events moeten real-time verschijnen.

## 4. Alphapy/Mind integraties - Enhanced
- Navigeer naar docs onder `docs/alphapy`, `docs/mind`, etc. en verifieer dat cross-links werken.
- Controleer of de Status componenten correct verwijzen naar Alphapy en Mind endpoints.
- **NIEUW: Vision Data Integration**
  1. Kan Mind Vision metrics ophalen van `/api/telemetry`?
  2. Worden Vision activities correct geteld in real-time?
  3. Kan Mind Vision data tonen in user profiles?
  4. Werken nieuwe metric trends in bestaande charts?
- **NIEUW: Core API Proxy Tests**
  1. Kan Core Vision blueprints ophalen via API proxy?
  2. Werkt `/dashboard/summary` met Vision data?
  3. Zijn Vision metrics beschikbaar in Core's telemetry exports?
  4. Kan Core Vision activities doorsturen naar Mind?

## 5. Telemetry cron / scripts - Enhanced
- Voer het script of cronjob-equivalent uit dat `/api/metrics` triggert (zoals beschreven in README).
- Controleer logs: succesvolle snapshots moeten status + requests tonen; fouten moeten duidelijke meldingen geven.
- **NIEUW:** Test Vision activity tracking in cron jobs.
- **NIEUW:** Controleer dat nieuwe metrics (Vision/Reflection/Habit) worden geaggregeerd.

## 6. Metrics Accuracy Tests
- **Vision Metrics**
  1. Creëer nieuwe vision: `vision.create` metric moet stijgen.
  2. Update vision: `vision.update` metric moet stijgen.
  3. Delete vision: `vision.delete` metric moet stijgen.
  4. Bekijk vision lijst: `vision.view` metric moet stijgen.
- **Reflection Metrics**
  1. Sla daily reflection op: `reflection.create` metric moet stijgen.
  2. Update reflection: `reflection.update` metric moet stijgen.
  3. Bekijk reflection: `reflection.view` metric moet stijgen.
- **Habit Metrics**
  1. Creëer nieuwe habit: `habit.create` metric moet stijgen.
  2. Complete habit: `habit.complete` metric moet stijgen.
  3. Delete habit: `habit.delete` metric moet stijgen.

## 7. Cross-browser regressie
- Test desktop (Chrome, Firefox) en mobiel (Safari iOS, Chrome Android).
- Zet `prefers-reduced-motion` aan om te zien of hero/halo animaties zich aanpassen.
- Verhoog systeemcontrast en bekijk of tekst op glass componenten leesbaar blijft.
- **NIEUW:** Test Vision UI op `/dashboard/vision` across browsers.

## 8. Content & linkcontrole - Enhanced
- Loop de volledige homepage + statuspagina door en klik elke interne link (navigatie, CTA's, footer, hero-knoppen) om te checken of de bestemming klopt en geen 404 oplevert.
- Controleer alle externe links in `SiteHeader`, `SiteFooter`, `links.ts` en documentatiepagina's op juiste URLs (open ze in een nieuw tabblad en kijk of de host klopt).
- Valideer dat knop-/linkteksten overeenkomen met hun acties (bijv. "Bekijk status" → `/status`).
- Lees de hero copy, status-highlights en callouts door om typefouten of verouderde info te spotten; noteer exacte zinnen + locatie wanneer iets niet klopt.
- Op de statuspagina: klik elke subsystem-kaart, check tooltiptekst, en bevestig dat iconen/titels overeenkomen met de subsystemen uit `types/telemetry.ts`.
- **NIEUW:** Controleer Vision dashboard links en content op `/dashboard/vision`.

## 9. Security & Authentication Tests
- **Vision API Security**
  1. Alle Vision endpoints vereisen geldige JWT tokens.
  2. RLS policies isoleren user data correct.
  3. Vision metrics zijn user-scoped.
  4. API rate limiting werkt voor nieuwe endpoints.
- **Enhanced Telemetry Security**
  1. Telemetry data is user-isolated.
  2. Metrics aggregation respects user boundaries.

## Rapportage
1. Noteer per issue: pagina/onderdeel, device + browser, stappen, verwacht vs werkelijk, plus screenshots/video.
2. Meld elk issue via het `/report` commando in de Discord-server (volg de template voor snelle verwerking).
3. Wil je aanvullende context geven? Gebruik daarnaast de gedeelde issuetemplate in het trackerboard.

## Test Scenarios Checklist
- ✅ Kan Mind de nieuwe Vision metrics ophalen van /api/telemetry?
- ✅ Worden Vision activities correct geteld in real-time?
- ✅ Kan Mind Vision data tonen in user profiles?
- ✅ Werken de nieuwe metric trends in bestaande charts?
- ✅ Kan Core Vision blueprints ophalen via API proxy?
- ✅ Werkt /dashboard/summary met Vision data?
- ✅ Zijn Vision metrics beschikbaar in Core's telemetry exports?
- ✅ Functioneert RLS correct voor Vision data isolation?
- ✅ Kan Core Vision activities doorsturen naar Mind?

