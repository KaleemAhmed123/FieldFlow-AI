# Operational data — rich, connected SF + e-com, and price from inventory

## 1. Task
- **Name:** Make the demo data real/operational across Salesforce + e-com; quote price from e-com.
- **Status:** shipped (code committed + pushed; both seeds run + verified live) — one pending: a live
  end-to-end fire on the new data. Started 2026-10-21, last updated 2026-10-21.

## 2. What you asked for
- **Price:** when we have inventory, the part price comes from **e-com**, not the hardcoded book
  (fallback to the book if e-com has no price).
- **Salesforce:** wipe + reseed **rich, connected** data — fill many fields, create the missing
  Service Territories / members / skills / technician assignments, make every object connect like a
  real org, so **any scenario** (delay / parts / complex × in/out warranty × stock) is firable.
- **E-com:** same — rich/real stock aligned to the assets' parts.

## 3. Open questions (answered)
1. Wipe + reseed (not patch). ✅
2. All scenario coverage. ✅
3. Price falls back to the hardcoded book when e-com has none. ✅
4. Territories: Noida / Delhi / Gurgaon, techs split across them, connected to appointments. ✅

## 4. Plan
**A. Price from e-com (code).** e-com `/api/stock/{partNo}` also returns `pricePaise`; the inventory
adapter gains `price_paise()`; `build_quote` uses it, falling back to `PRICE_BOOK_PAISE`.

**B. SF seed rewrite (`seed_demo_data.py`, run by the user).** Catalog-driven, idempotent, `--clean`
wipes. Creates/connects:
- **Service Territories** (Noida/Delhi/Gurgaon) on real Operating Hours, with addresses.
- **Skills** (one per `model.requiresSkill`), **ServiceResourceSkill** (each tech skilled on a
  cluster so every skill is covered ≥2 techs), **ServiceTerritoryMember** (techs → territories).
- **Rich fields** everywhere: Account (industry, phone, billing address), Contact (email, phone,
  mailing address), Asset (serial, install/purchase date, price, status, description from specs),
  WorkOrder (subject, description, priority, status, address), ServiceAppointment (subject,
  description, territory, schedule, duration, address, earliest-start / due).
- **AssignedResource:** each appointment gets a tech who **has the asset's skill** and is a **member
  of the appointment's territory** (so FS scheduling accepts it + policy's skill check is real).

**C. E-com (`seed.mjs`).** Already catalog-driven with prices + stock; confirm stock is plentiful for
repeated testing (scarce stays 1 for the NFR-5 race).

## 5. Tasks
- [x] A: e-com `/api/stock` returns `pricePaise`; `price_paise()` adapter; `build_quote` uses it
      (book fallback); `inventory.price` tool; graph node; trace shows `priceAuthority`. 126 tests.
- [x] B: rewrote `seed_demo_data.py` — Operating Hours, 3 Territories (addressed), Skills per
      `requiresSkill`, ServiceResourceSkill (coverage ≥2 techs), ServiceTerritoryMember, rich fields
      on Account/Contact/Asset/WorkOrder/ServiceAppointment, and AssignedResource matched by
      skill+territory. Idempotent; `--clean` wipes incl. territories/members. ruff clean.
- [x] C: e-com `seed.mjs` → 3 stock locations (Noida/Gurgaon/Delhi) mirroring the territories.
- [x] **User ran** both seeds 2026-10-21. Verified live: SF connectivity AssignedResource 1→29,
      Skill 2→9, ServiceResourceSkill 1→15, ServiceTerritory 1→4, ServiceTerritoryMember 1→7; e-com
      serves `pricePaise` + 3 locations. SA-0060 reads a full technician (Kavya Rao, skills
      inverter-ac + kitchen-appliance) via the pipeline endpoints.
- [ ] **Pending:** live end-to-end fire on SA-0060 (needs Render redeployed to the new tip first).

## 6. Updates
**2026-10-21** — Audited the live org: 29/30 appointments had no territory, no technician, no skills,
no schedule; e-com already carries real prices. Plan approved (wipe+reseed, all coverage, price
fallback, 3 territories). Building A–C.

**2026-10-21 (later)** — A/B/C built, committed (conventional prefixes), pushed. User ran both seeds.
Verified live: full SF connectivity (counts above), e-com `pricePaise` + 3 locations. **Demo
appointment chosen: SA-0060** (out-of-warranty XYZ-492 AC, tech Kavya Rao, FFDemo Noida territory —
the paid path). **Two blockers for the live fire:** (1) Render still runs the OLD tip (`f2599e5`) — the
force-push didn't auto-redeploy; needs a manual "Deploy latest commit" to get `89a56ad` (price-from-
ecom). Not functionally blocking (CAP-492 book price == e-com price). (2) Both XYZ-492 parts are in
stock, so the AI may pick PCB-492 (₹5,300 ≥ ₹5,000 → high-value approval gate); set **PCB-492 = 0** on
the e-com dashboard for a clean ₹3,700 no-gate quote.

## 7. Explanation
**Price from e-com.** The quote's part price now comes from the inventory service: e-com's
`GET /api/stock/{partNo}` returns `pricePaise`; `RestInventory.price_paise` reads it (FakeInventory
reads the catalog, e-com's own seed source); the graph's `build_quote` node fetches it and passes it
to `commerce.build_quote`, which uses it when present and falls back to the in-code `PRICE_BOOK_PAISE`
otherwise. The quote records `priceAuthority` = `ecom` or `price_book`, so the trace shows which
priced it.

**Operational SF data.** The seed now builds the backbone the org lacked and connects everything:
real Operating Hours → 3 addressed Territories → Skills (one per catalog `requiresSkill`) → each
technician made a territory **member** and given a **skill cluster** (every skill covered by ≥2
techs) → every appointment assigned a **territory + schedule + a technician who has the asset's skill
and is a member of that territory**. Rich fields (addresses, serial/dates/price, priority,
subject/description, duration/due) fill the records out; cosmetic writes are best-effort so a
restricted picklist is skipped, never failing the connections. This makes every scenario
(delay/parts/complex × in/out warranty × stock) firable against real, connected data.

**E-com.** Stock seeds across three locations mirroring the territories (Noida primary, Gurgaon
secondary buffer, Delhi empty for the race); scarce parts stay Noida-only at 1 so NFR-5 still fires.
