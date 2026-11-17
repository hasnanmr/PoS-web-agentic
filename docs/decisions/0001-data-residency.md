# ADR 0001 — Data residency for Supabase and Railway (T-108)

- **Status:** Partly decided (2026-11-17). Demo: decided. Pilot with real data: **open, blocked on legal review**.
- **Stories:** US-039, US-049. **PRD:** NFR1, §13 open question "Hosting region".

## Context

Indonesia's PDP Law (Law No. 27/2022) restricts cross-border transfer of personal data. The PRD and task breakdown record (T-108, checked 2026-11-18 per the task text) that neither Supabase nor Railway lists an Indonesia region; the nearest for both is Singapore (`ap-southeast-1` on Supabase, `asia-southeast1` on Railway). Moving off Supabase is not planned (NFR1).

This could not be re-checked from the authoring environment (no access to the providers' sites), so the region facts above are taken from the PRD as written.

## Decision

1. **Demo:** Supabase and Railway in Singapore, **dummy data only**. `supabase/seed.sql` and every demo dataset contain no real merchant or customer data.
2. **Pilot / production:** no real merchant or customer data is stored until a legally reviewed cross-border transfer basis is recorded in this ADR (status → Accepted), and the privacy notice (T-106) and consent text (T-076) say where data is stored.
3. Config files default to Singapore: `supabase/config.toml` (local only; hosted region is chosen at project creation) and `railway.toml` region set when the project is created (T-109).

## Open items (owner: product owner + legal)

- [ ] Who obtains the cross-border transfer basis, and on what legal ground.
- [ ] Required wording for the privacy notice and WhatsApp consent message.
- [ ] Record the decision here, then promote demo → pilot with the T-114 checklist.

## Consequences

- Engineering can proceed with all MVP work on dummy data.
- Pilot onboarding of real merchants is blocked until this ADR is accepted (ACN1).
