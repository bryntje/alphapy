---
layout: page
title: Privacy Policy
permalink: /privacy-policy/
---

# Alphapips Bot Privacy Policy

_Last updated: 2025-10-16_

This Privacy Policy explains how the Alphapips Discord Bot (“**Alphapips**”, “**Bot**”, “**we**”, “**us**”) collects, uses, and protects information when it operates on your Discord server. By installing or interacting with the Bot, you consent to the practices described here. If you do not agree with this Policy, do not use the Bot.

> **At a glance:** Alphapips stores the minimum data required to deliver its reminder, ticketing, analytics, and AI-assisted features. We rely primarily on legitimate interest to process interaction data, keep it only as long as needed, and provide GDPR-friendly export and deletion options.

## 1. Who is responsible?

The Alphapips Bot is maintained by the project owner reachable at `bryan.dhaen@gmail.com`. This individual acts as the data controller for personal data processed by hosted instances of the Bot. If you self-host the Bot, you become the controller for that deployment and must adapt this Policy accordingly.

## 2. What data we collect

Depending on the features you enable, the Bot may process the following categories of data:

- **Discord account identifiers**: User IDs, usernames, discriminator/tag, avatar URLs, and guild (server) IDs. Needed to identify who triggered a command, schedule reminders, or manage access control.
- **Server configuration data**: Channel IDs, role IDs, preference flags, and other settings stored via `/config` or environment variables.
- **Reminder content**: Event titles, dates, times, recurrence schedules, linked message URLs, and channel IDs captured from embeds or manual `/add_reminder` commands.
- **Interaction content**:
  - Growth check-in prompts and user responses;
  - Learning requests (`/learn_topic`) and ticket conversation summaries;
  - AI caption inputs and generated outputs (for context and troubleshooting).
- **Ticketing data**: Ticket channel IDs, message excerpts, GPT summaries, user and staff actions, and status updates.
- **Logging and audit events**: Internal logs for errors, status updates, and admin actions posted to designated log channels.
- **Support communications**: Emails or GitHub issues you send us about the Bot.

We do not intentionally collect sensitive categories of personal data, but users may include such information in free-form text fields. Server administrators should discourage sharing sensitive details and may redact them using the deletion options described below.

## 3. How we use the data

We use the data listed above to:

- Deliver requested features (e.g., send reminders, respond to commands, store ticket history);
- Provide AI-driven outputs by forwarding prompts to model providers such as OpenAI;
- Monitor performance, detect abuse, and debug issues;
- Send audit logs to staff-only channels that you configure;
- Comply with legal obligations and enforce the Terms of Service.

## 4. Legal bases (EU / UK GDPR)

For data subjects in the European Economic Area or the United Kingdom, we rely on the following legal bases:

- **Legitimate interest** for operating community tools (reminders, tickets, analytics) and ensuring platform security;
- **Consent** for optional AI features when server administrators explain and enable them for their community;
- **Legal obligation** if we must retain data to comply with tax, regulatory, or court requirements.

## 5. Sharing and disclosure

We do not sell or rent your data. We may share data with:

- **Discord** when responding to events and sending messages;
- **OpenAI or other AI providers** when you enable GPT-powered commands, limited to the prompt and necessary metadata;
- **Hosting and infrastructure providers** that store databases, logs, or backups;
- **Legal authorities** if required to comply with applicable laws, court orders, or government requests.

Each provider processes data under their own terms and policies. We aim to choose partners that meet GDPR adequacy standards or enter into appropriate transfer agreements.

## 6. Data retention

- Reminder entries persist until the scheduled job completes or an admin deletes them.
- Ticket transcripts and GPT summaries remain until manually removed.
- Growth check-in responses are stored for follow-up unless deleted.
- Audit logs in Discord channels follow Discord’s retention unless you purge them.
- Backups (if enabled) are kept for up to 30 days before automatic deletion.

You can request deletion sooner at any time using the methods below.

## 7. Your rights and controls

If you are located in the EU/EEA, UK, or other regions with similar rights, you may have the following rights regarding your personal data:

- Access, export, or receive a copy of the data (`/export_onboarding` and other exports);
- Request correction of inaccurate data;
- Object to or restrict certain processing;
- Request deletion of data (upcoming `/delete_my_data` command or email request);
- Withdraw consent for optional AI features.

To exercise a right, contact the data controller or use available commands. We will respond within 30 days where legally required.

## 8. Data deletion workflow

Server administrators can delete reminders, tickets, or check-in records via bot commands or database tools. Until the `/delete_my_data` command is released, individuals can request manual deletion by emailing the controller with their Discord username and ID. We may take reasonable steps to verify identity before fulfilling requests.

## 9. Security practices

We implement technical and organizational measures, including:

- Using role-restricted log channels and environment-based secrets management;
- Limiting database access to authorized maintainers;
- Encrypting connections to the database and third-party APIs using TLS;
- Monitoring dependencies and applying patches promptly.

No system is fully secure, so please notify us immediately if you discover a vulnerability or suspect unauthorized access.

## 10. International transfers

Your data may be processed in countries different from where you reside, including the European Union and the United States. When transferring personal data internationally, we rely on adequacy decisions or Standard Contractual Clauses where required by law.

## 11. Children’s data

The Bot is not intended for individuals under 13 (or the minimum age required in their jurisdiction to use Discord). We do not knowingly collect personal information from children. If you believe a child has provided data, contact us to remove it.

## 12. Changes to this Policy

We may update this Policy to reflect changes in the Bot or legal requirements. We will adjust the “Last updated” date and, when material changes occur, announce them via the GitHub repository or official communication channels. Continued use signifies acceptance of the updated Policy.

## 13. Contact

For questions, data requests, or concerns about this Policy, email `bryan.dhaen@gmail.com` or open an issue on the Github repository.

---

By installing or using Alphapips, you acknowledge that you have read and understood this Privacy Policy.
