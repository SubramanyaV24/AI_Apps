# hooks.md

## Overview
`hooks.py` defines the Frappe app configuration and integration points for the **Ai Apps** application. It contains metadata such as the app name, title, publisher, and various optional hook sections (JS/CSS includes, scheduled tasks, and API overrides).

## Key Sections

| Section | Purpose |
|---------|---------|
| **App Metadata** | Provides basic information used by Frappe to identify the app (name, title, version, license, etc.). |
| **Scheduler Events** | Demonstrates how to schedule a daily background job – in this case, `ai_apps.ai_screening.frappe_integration.daily_ai_screening_batch` runs every night at 23:00. |
| **Override Whitelisted Methods** | Shows an example of overriding a whitelisted method (`ai_apps.api.proctor_api.evidence.store_evidence`). |
| **Commented Hooks** | Various hook examples are left commented out (JS/CSS includes, web routes, notifications, etc.) for future use. |

## Usage
The file is loaded automatically by Frappe when the app is installed. No additional import is required. To customise behaviour, uncomment the relevant sections and provide the appropriate implementation.

---
*Generated automatically for documentation purposes.*
