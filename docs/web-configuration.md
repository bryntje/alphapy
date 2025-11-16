# 🔧 Alphapy Bot Web Configuration Interface

**⚠️ IMPORTANT: This is NOT the same as `app.innersync.tech`**

This dashboard is specifically for **configuring your Alphapy Discord bot** across your servers. It is designed exclusively for **server administrators** to manage bot settings, reminders, onboarding, and more.

**For personal reflection and growth tracking, visit [`app.innersync.tech`](https://app.innersync.tech) instead.**

---

**Phase 1.75 Feature** - Modern web-based administration dashboard for Alphapy Discord bot.

The web configuration interface provides server administrators with a user-friendly alternative to Discord slash commands for managing bot settings, onboarding flows, and viewing system history.

## 🎯 Overview

Instead of using complex slash commands like `/config system set_log_channel #logs`, administrators can now use a visual web interface with:
- **Drag-and-drop** onboarding question/rule management
- **Batch operations** for updating multiple settings
- **Settings history** with rollback capabilities
- **Visual previews** of configuration changes
- **Mobile-friendly** responsive design

## 🚀 Getting Started

### 1. Access the Dashboard

Navigate to: **https://alphapy.innersync.tech/dashboard**

### 2. Discord Authentication

1. Click the login prompt
2. Authorize the Discord OAuth application
3. Grant permissions for accessing your servers
4. Select the server you want to configure

### 3. Dashboard Overview

The main dashboard shows all your administrated servers. Click on any server to access its configuration panel.

## 📋 Features

### Settings Management

#### System Settings
Configure core Discord channels and bot behavior:
- **Log Channel**: Where bot messages and errors are sent
- **Onboarding Channel**: For new member welcome flows
- **Rules Channel**: Server guidelines and community rules

#### Feature-Specific Settings
- **Embed Watcher**: Auto-reminder creation from announcements
- **Reminders**: Manual reminder scheduling and @everyone permissions
- **GPT Settings**: AI model selection and response parameters
- **Invite Tracker**: Welcome messages and milestone announcements
- **GDPR Compliance**: Data privacy and user rights management

### Onboarding Builder

#### Questions Management
Create custom onboarding flows with:
- **Question Types**: Single choice, multiple choice, text input, email collection
- **Conditional Follow-ups**: Ask additional questions based on previous answers
- **Drag-and-Drop Reordering**: Change question sequence easily

#### Rules Management
Define community guidelines with:
- **Visual Rule Editor**: Title and description for each rule
- **Priority Ordering**: Drag rules to set display order
- **Enable/Disable**: Toggle rules on/off without deleting

### Settings History

#### Change Tracking
View complete audit trail of all configuration changes:
- **Who**: Discord user who made the change
- **When**: Timestamp of the modification
- **What**: Before/after values for each setting
- **Type**: Created, Updated, Deleted, or Rollback actions

#### Rollback Functionality
- **One-Click Rollback**: Restore previous setting values
- **Safe Operations**: Only applicable to update operations
- **History Preservation**: Rollback actions are also logged

## 🔧 Technical Implementation

### Architecture

#### Frontend (Next.js)
- **TypeScript**: Full type safety with custom schemas
- **React Components**: Modular, reusable UI components
- **Authentication**: Discord OAuth2 with PKCE flow
- **State Management**: React hooks with optimistic updates

#### Backend (FastAPI)
- **REST API**: CRUD operations for all configuration data
- **Guild Isolation**: All data scoped to specific Discord servers
- **Audit Logging**: Automatic history tracking for all changes
- **Type Validation**: Pydantic models for request/response validation

#### Database Schema
```sql
-- Settings storage
CREATE TABLE bot_settings (
    guild_id BIGINT NOT NULL,
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    PRIMARY KEY(guild_id, scope, key)
);

-- Onboarding questions
CREATE TABLE guild_onboarding_questions (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    step_order INTEGER NOT NULL,
    question TEXT NOT NULL,
    question_type TEXT NOT NULL,
    options JSONB,
    followup JSONB,
    required BOOLEAN DEFAULT TRUE
);

-- Community rules
CREATE TABLE guild_rules (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    rule_order INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL
);

-- Settings history
CREATE TABLE settings_history (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    old_value JSONB,
    new_value JSONB NOT NULL,
    changed_by BIGINT,
    change_type TEXT NOT NULL
);
```

### API Endpoints

#### Settings Management
```
GET    /api/dashboard/{guild_id}/settings                    # Get all guild settings
POST   /api/dashboard/{guild_id}/settings                    # Update settings by category
GET    /api/dashboard/{guild_id}/settings/history            # Get settings change history
POST   /api/dashboard/{guild_id}/settings/rollback/{entry_id} # Rollback to previous value
```

#### Onboarding Management
```
GET    /api/dashboard/{guild_id}/onboarding/questions        # Get onboarding questions
POST   /api/dashboard/{guild_id}/onboarding/questions        # Create/update question
DELETE /api/dashboard/{guild_id}/onboarding/questions/{id}   # Delete question

GET    /api/dashboard/{guild_id}/onboarding/rules            # Get community rules
POST   /api/dashboard/{guild_id}/onboarding/rules            # Create/update rule
DELETE /api/dashboard/{guild_id}/onboarding/rules/{id}       # Delete rule

POST   /api/dashboard/{guild_id}/onboarding/reorder          # Reorder questions/rules
```

## 🔐 Security & Permissions

### Authentication
- **Discord OAuth2**: Secure login with user's Discord account
- **Guild Verification**: Only servers where user has admin permissions are accessible
- **Session Management**: HTTP-only cookies with automatic expiration

### Authorization
- **Guild-Scoped Access**: Users can only modify settings for servers they administer
- **Permission Checks**: Verified against Discord API permissions
- **Audit Trail**: All changes logged with user attribution

### Data Privacy
- **No Cross-Guild Leakage**: Settings are completely isolated between servers
- **GDPR Compliance**: Built-in data export and deletion capabilities
- **Secure Storage**: All sensitive data encrypted at rest

## 📱 User Experience

### Dashboard Layout
```
┌─────────────────────────────────────────────────────────┐
│ Alphapy Bot Configuration - Server Name                  │
│                                                         │
│ ┌─ System ─┬─ Reminders ─┬─ Embed Watcher ─┬─ GPT ─┐     │
│ │ Settings ││ Settings   ││ Settings        ││ Settings │    │
│ │ [Form]   ││ [Form]     ││ [Form]          ││ [Form]   │    │
│ └─────────┴┴────────────┴┴─────────────────┴┴─────────┘     │
│                                                         │
│ ┌─ Onboarding ─┬─ History ─┐                            │
│ │ Questions    ││ Changes  │                            │
│ │ [Drag/Drop]  ││ [Table]  │                            │
│ └──────────────┴┴─────────┘                            │
│                                                         │
│ [Save All Changes] [Reset Changes] [Onboarding] [History] │
└─────────────────────────────────────────────────────────┘
```

### Responsive Design
- **Desktop**: Full-width layout with side-by-side forms
- **Tablet**: Stacked layout with collapsible sections
- **Mobile**: Single-column with bottom navigation

### Accessibility
- **Keyboard Navigation**: Full keyboard support for all interactions
- **Screen Reader**: Proper ARIA labels and semantic HTML
- **Color Contrast**: WCAG AA compliant color schemes
- **Focus Management**: Clear focus indicators and logical tab order

## 🛠️ Development & Deployment

### Local Development
```bash
# Install dependencies
cd shared/innersync-core
pnpm install

# Start development server
pnpm dev

# Access at http://localhost:3000/dashboard
```

### Discord OAuth2 Setup

#### 1. Create Discord Application
1. Ga naar [Discord Developer Portal](https://discord.com/developers/applications)
2. Klik op "New Application"
3. Geef je app een naam (bijv. "Alphapy Web Dashboard")
4. Noteer de **Application ID** (dit is je CLIENT_ID)

#### 2. Configure OAuth2
1. Ga naar "OAuth2" tab in je Discord app
2. Klik op "Add Redirect" onder "Redirects"
3. Voeg toe: `https://alphapy.innersync.tech/api/auth/discord/callback`
4. Klik op "Save Changes"

#### 3. Create Client Secret
1. Klik op "Reset Secret" om een nieuwe CLIENT_SECRET te genereren
2. **BELANGRIJK**: Bewaar deze secret veilig - deze wordt nooit meer getoond!

#### 4. Environment Variables
```bash
# Discord OAuth2 (Vereist voor web dashboard)
DISCORD_CLIENT_ID=123456789012345678  # Jouw Application ID
DISCORD_CLIENT_SECRET=abcdefghijklmnop  # Jouw Client Secret
DISCORD_OAUTH_REDIRECT_URI=https://alphapy.innersync.tech/api/auth/discord/callback

# URLs
ALPHAPY_BASE_URL=https://alphapy.innersync.tech
NEXT_PUBLIC_BASE_URL=https://alphapy.innersync.tech
```

#### 5. OAuth2 Scopes
De app gebruikt automatisch deze scopes:
- `identify` - Basis user info
- `guilds` - Lijst van servers
- `guilds.members.read` - Server member info (voor admin checks)

### Deployment
The interface is deployed alongside the main Alphapy application and shares the same infrastructure:
- **Railway**: Containerized Next.js deployment
- **Database**: Shared PostgreSQL instance
- **CDN**: Static assets served via Railway CDN

## 📚 Migration Guide

### From Slash Commands to Web Interface

Existing slash command configurations remain functional. The web interface provides an **alternative** method for configuration with these advantages:

| Feature | Slash Commands | Web Interface |
|---------|----------------|---------------|
| **Ease of Use** | Command syntax required | Visual forms |
| **Batch Operations** | Individual commands | Save multiple at once |
| **Onboarding Builder** | Manual text editing | Drag-and-drop interface |
| **History Tracking** | Limited audit logs | Complete change history |
| **Mobile Access** | Discord mobile app | Dedicated mobile interface |
| **Validation** | Basic parameter checks | Real-time form validation |

### Data Compatibility
- **Full Backward Compatibility**: All existing slash command configurations work unchanged
- **Shared Database**: Web interface modifies the same settings as slash commands
- **Unified Audit Trail**: Both interfaces log changes to the same history table

## 🔍 Troubleshooting

### Login Issues
- **"No servers found"**: Ensure you have Administrator or Manage Server permissions
- **"Authentication failed"**: Check Discord OAuth2 configuration
- **"Session expired"**: Refresh the page and login again

### Permission Errors
- **"Access denied"**: Verify your Discord role permissions in the server
- **"Settings not saved"**: Check that you have administrator permissions

### Configuration Issues
- **Settings not applying**: Try refreshing the page or clearing browser cache
- **Onboarding not working**: Ensure onboarding channel is configured
- **History not loading**: Check database connectivity

## 🚀 Future Enhancements

### Planned Features
- **Template Library**: Pre-built configuration templates for common use cases
- **Bulk Server Management**: Configure multiple servers simultaneously
- **Advanced Analytics**: Usage statistics and engagement metrics
- **Automated Backups**: Scheduled configuration backups
- **Team Collaboration**: Multiple admins per server with permission levels

### API Expansions
- **Webhook Integrations**: Real-time notifications for configuration changes
- **Bulk Import/Export**: CSV/JSON configuration management
- **Scheduled Changes**: Plan configuration updates for future deployment

---

**Version**: Phase 1.75 - Web Configuration Interface  
**Status**: ✅ **Fully Implemented & Production Ready**  
**Documentation Date**: November 16, 2025
