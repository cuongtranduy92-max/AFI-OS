# AFI-OS Master Specification

Status: operator-approved scope, 2026-08-12

Benchmark-derived product and implementation decisions are recorded in
`docs/ATC_SPY_BENCHMARK_DECISIONS.md`.

## Product outcome

AFI-OS is the operating system for discovering, evaluating, launching and monitoring
affiliate projects. It retains every project and campaign. Policy uncertainty or a
prohibition creates a visible warning and audit trail; it never automatically removes a
project, pauses a campaign or performs a Google Ads write.

The normal path is automated. The operator is asked only for an ambiguous commercial
fact, external authentication, a risky decision, or approval of an outbound action.

## Non-negotiable safety rules

1. PPC permission, commission, fees and registration state are separate facts.
2. Missing PPC evidence remains `NOT_CHECKED`; it does not become allowed or prohibited.
3. Terms warnings are warning-only. Projects and campaigns remain included.
4. Conflicting official sources remain visible until the operator resolves the fact.
5. Google Ads access is read-only until the operator separately authorizes writes.
6. Email may be read, classified, summarized and drafted automatically. Sending always
   requires explicit operator approval.
7. Every automated fact stores its source URL, excerpt, checked time, confidence, scope,
   source authority and review state.
8. Every release requires a verified backup, checksum, updater and rollback tests, and
   a live post-check.

## End-to-end workflow

### 1. Project intake and operating state

Input may be a domain, product name, observed advertisement or existing campaign.
AFI-OS resolves the merchant, affiliate program, signup link, network, current operating
state and responsible next action.

Required states include discovered, researching, applying, pending approval, active,
registration blocked, paused, rejected by merchant and closed. A blocked registration
retains the project, sources and history and creates a retry/manual-review exception.

### 2. Terms, prohibitions and commercial facts

AFI-OS collects and compares official merchant pages, the exact partner portal and
written confirmations. It extracts and versions:

- paid search, brand keyword, non-brand keyword, direct-link and trademark/ad-copy rules;
- prohibited channels, geographies, claims, creatives and other restrictions;
- commission rate and whether it is one-time, recurring for a fixed duration, lifetime,
  hybrid, tiered, capped or a maximum claim;
- cookie duration, approval delay, payment cycle, minimum payout and supported payout
  methods;
- transaction, platform, payout, currency-conversion, refund and chargeback fees, with
  percentage/fixed amount, currency, basis and conditions.

Commission and fee facts never change PPC permissions. Conflicting official claims use
`CONFLICT` until the operator accepts/rejects the individual fact.

### 3. Advertiser intelligence graph

For each project AFI-OS reports:

- number of distinct advertisers and active advertisers in the selected period;
- first/last seen, geography, language and observed creatives for each advertiser;
- concentration and new-advertiser trend;
- every other project each advertiser is observed promoting;
- deduplicated advertiser-to-project graph and confidence/provenance for each edge.

The graph expands from seed projects and creates review items for unresolved advertiser
identity or project domains instead of guessing.

### 4. Economics, score and payback

Every project receives a source-aware score and scenario range. Inputs include product
price, accepted commission schedule, all applicable fees, approval/refund/chargeback
rates, conversion rate, recurring retention/churn, CPC, click volume and confidence.

Core calculations:

```text
gross commission LTV
  = commission per eligible period × expected active periods

net commission per referral
  = gross LTV × approval rate × (1 − refund/chargeback rate)
    − transaction/platform/payout fees

expected value per ad click
  = net commission per referral × sale probability per ad click

break-even CPC
  = expected value per ad click

safe CPC
  = break-even CPC × (1 − target margin) × confidence discount

estimated payback days
  = cumulative ad spend ÷ expected daily net commission
```

Actual payback uses attributed approved/paid commission rather than modeled commission.
If a required commercial fact is unresolved, AFI-OS shows a range and the missing-input
warning; it does not silently choose a source.

### 5. Google Ads launch pack

Before launch, AFI-OS prepares one editable, validated asset pack per project:

- 15 English headlines; at least 2 use the exact project name/main brand keyword;
- 4 English descriptions; each naturally uses 1–2 product-relevant keywords;
- 4 sitelinks, each with an explicit referral URL and final-domain validation;
- 4 callouts;
- proposed English international keyword set, negatives, match types and landing pages;
- policy/registration warnings shown beside the pack without blocking export.

The pack validates Google Ads length/uniqueness requirements and referral-link integrity.
Generation is a proposal. Creating or modifying a Google Ads campaign requires separate
write authorization and an operator confirmation.

### 6. Campaign monitoring and optimization

AFI-OS continuously ingests, at minimum, Customer ID, Campaign ID, campaign state,
campaign type, currency, date, cost, impressions, clicks and conversions. When available
it also ingests search terms, keyword/match type, CPC, impression share, ad/asset status,
quality signals and conversion value.

The default campaign CTR target is **40.0%**. CTR below 40% creates a warning and an
optimization checklist; it never changes the campaign. The target is configurable per
campaign but 40% remains the default.

Optimization checks cover:

- CTR and trend by campaign, ad group, ad, keyword, search term, country and device;
- spend without conversion, CPC versus safe CPC and payback deterioration;
- low-volume/irrelevant search terms and negative-keyword proposals;
- missing or weak assets, final URL/referral-link problems and policy disapprovals;
- budget limitation, impression share and query-to-ad/landing-page relevance;
- whether the campaign has received a fresh data snapshot and fresh optimization review.

International English keyword demand must use a dated, attributed source (preferably
Google Ads Keyword Planner via read-only API) and report location/language/network/date
range, average monthly searches, competition and bid ranges. AFI-OS must not label a
keyword “most searched” without comparable source data.

### 7. Attribution, revenue and payout

AFI-OS joins Google Ads click/campaign/keyword to affiliate SubID, conversion,
commission and payout. It reports per project and campaign:

- ad cost;
- referral/click and conversion counts;
- pending, approved, rejected, refunded, chargeback, locked and paid commission;
- gross earned amount, fees, net earned amount, currently withdrawable amount and amount
  actually withdrawn/paid;
- normalized base-currency values, FX source/confidence and reconciliation exceptions;
- modeled versus observed data and unattributed items.

### 8. Project workspace and support communication

Each project has one workspace containing state, owner/next action, registration history,
terms/commercial facts, advertiser graph, economics, launch pack, campaign performance,
finance, support contacts, conversations and audit history.

Support chat and email records store channel, participants, timestamps, subject, bounded
summary, required action, promised deadline and links to the original source. Gmail intake
matches messages to projects by verified sender/domain plus thread context; ambiguous
messages go to Operations Inbox.

For each relevant inbound email AFI-OS may automatically:

1. link it to the project or request a mapping;
2. summarize what changed and extract questions/deadlines;
3. update the project's next action and communication timeline;
4. propose a reply grounded in the thread, known terms and project facts;
5. save a draft after operator-requested/approved automation.

AFI-OS never sends the proposed reply without explicit operator approval.

## Durable automation runtime

All long-running discovery, research and import work uses a database-backed queue. Every
job has a stable dedupe key, type, priority, bounded payload/result, attempt counter,
`run_after`, lease owner/expiry and terminal state. Claiming is compare-and-swap: two
workers cannot both own the same lease. A completion with a stale lease token is rejected.

Transient failures enter `RETRY_WAIT` with bounded exponential backoff. A crashed worker's
expired lease is recovered; after the maximum attempt count the job enters `DEAD_LETTER`
and requires an audited local retry. Jobs are never retried forever. Credentials, cookies,
authorization values, secrets, passwords and tokens are redacted before queue persistence.

Queue execution may collect and normalize evidence or metrics. It has no authority to open
PPC permission, decide unresolved commercial facts, remove projects, mutate remote Google
Ads or send email.

## Exception-driven Operations Inbox

Operator-required items include unresolved commission/fee conflicts, registration failure,
ambiguous advertiser/project/email mapping, missing credentials, reconciliation problems,
and approval of an outbound email or Google Ads write. Warning-only items include missing
PPC permission, CTR below target, stale data, policy risk and modeled economics.

Every item states what happened, why it matters, the affected project/campaign, source,
safe recommendation and exact action needed from the operator.

## Definition of done

The full product is complete only when one project can pass through the entire workflow
with real data: domain intake → sourced terms/commercial facts → advertiser graph → score
and payback → validated asset pack → campaign snapshot and CTR optimization warnings →
affiliate conversion/commission/payout reconciliation → linked support email and an
operator-approved reply draft. Tests must prove warnings never exclude projects or mutate
Google Ads and that outbound email is never sent implicitly.
# Project network journey (0.2.96)

The operator journey starts with `Tìm dự án`. Opening one Project must render the
Project profile and automatically expand all sourced advertisers plus every other
known Project for each advertiser. Advertiser nodes do not require a separate click.
Selecting a related Project recenters and repeats the expansion. The UI and API must
deduplicate stored entities, preserve source URL and observation dates, prevent
unbounded automatic recursion, and label absent observations `NOT_COLLECTED` rather
than zero. This read-only graph must never mutate Terms permissions, commission facts,
campaigns or Google Ads.
