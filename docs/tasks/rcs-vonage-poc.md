# RCS x Vonage POC

**Status:** In Progress
**Started:** 2026-09-29
**Last Updated:** 2026-09-29
**Owner:** Kaleem

---

## 1. What You Asked For

- Build a POC showcasing RCS via Vonage with a complex, enterprise-grade use case
- Learn the technology from scratch (developer background)
- Get access clarity from Vonage (managed account, RCS enablement, India availability)
- Design a conversation flow good enough to impress stakeholders
- Potentially integrate AI + n8n into the RCS conversation

---

## 2. Open Questions

| # | Question | My Recommendation | Your Answer |
|---|---|---|---|
| 1 | Does your company have a Vonage managed account already? | Confirm before anything else | **YES** ($100 credits, Agent Builder unlocking soon) |
| 2 | Have Vonage given you any credentials (API key, app ID, agent ID)? | You need these to build | *Pending Agent Builder* |
| 3 | Do you have an RCS-capable Android phone with Indian SIM for testing? | Android + Jio/Airtel/Vi that supports RCS | — |
| 4 | Which POC domain? (banking, e-comm, healthcare, logistics, other) | E-commerce full lifecycle — widest demo value | **E-commerce** |
| 5 | Is the Vonage partnership confirmed or still in discussion? | Affects urgency of access questions | — |

---

## 3. Plan

**Approach:** Learn -> Access -> Design -> Build -> Demo

**Files this task will touch:**
- `docs/tasks/rcs-vonage-poc.md` (this file)
- `src/` (Express backend, built incrementally)
- `docs/tasks/rcs-conversation-flow.md` (state machine design)

**What we are NOT doing yet:**
- Writing production code
- Picking a cloud provider
- Building a frontend
- Integrating AI (until architecture is decided)

---

## 4. Task Checklist

### Phase 0 — Knowledge and Access
- [x] Understand what RCS is
- [x] Understand Vonage's role
- [x] Understand Brand / Agent / Application concepts
- [x] Understand India-specific rules
- [x] Send manager message to Vonage, get answers
- [x] Confirm managed account + RCS enabled
- [ ] Get Developer Mode activated
- [ ] Allow-list test phone numbers

### Phase 1 — API Foundations
- [ ] Create Vonage Application
- [ ] Generate private key + application ID
- [ ] Implement JWT generation
- [ ] Send first RCS text message
- [ ] Receive first webhook
- [ ] Confirm delivery + read status

### Phase 2 — Rich Messages
- [ ] Send image message
- [ ] Send rich card
- [ ] Send carousel (2-3 cards)
- [ ] Send suggested replies (structured buttons)
- [ ] Send suggested actions (URL, dial, calendar)
- [ ] Handle inbound reply webhook

### Phase 3 — Conversation State Machine
- [ ] Design full POC conversation flow
- [ ] Implement state machine in Express
- [ ] Connect CRM/mock data layer
- [ ] Handle edge cases (unknown input, timeout, error)

### Phase 4 — AI + Fallback
- [ ] Add LLM layer for free-text understanding
- [ ] Add RCS to SMS fallback
- [ ] Add capability checking per device

### Phase 5 — Demo Polish
- [ ] End-to-end working demo on test device
- [ ] Observability (logs, status events)
- [ ] Presentation / walkthrough

---

## 5. Updates

### 2026-09-29 — Session 1
- Read full ChatGPT RCS briefing
- Workspace created at c:\Users\hp\Desktop\RCS-VONAGE-POC
- Task doc created
- Manager message drafted (see Section 7)
- Blocked on: Vonage access confirmation

### 2026-10-06 — Update
- Confirmed $100 credits available on the account.
- Agent builder will be enabled soon. We are unblocked on the account phase.
- Currently blocked on: Agent builder enablement and picking a POC domain.

### 2026-10-06 — Pivot to Complex AI Scenario
- Reviewed Kaleem's resume (Eudoro, Primble, Onlycouplez).
- Pivoting away from basic e-commerce to a complex Agentic AI use case using LangGraph, MCP, Salesforce, and RabbitMQ.
- Completed deep research on 2026 enterprise pain points and proposed 3 advanced scenarios in `docs/tasks/2026-enterprise-rcs-research.md`.

---

## 6. Full RCS + Vonage Knowledge Base

This section is the elaborated reference. Read it before building anything.

---

### 6.1 What Is RCS — The Real Mental Model

RCS stands for Rich Communication Services.

SMS was designed in 1992 for 160-character text over a 2G network. RCS is what SMS would look like if designed today — for smartphones, internet, and interactive business communication.

SMS gives you a one-way text. RCS gives you an interactive experience inside the phone's native messaging app. No separate app download needed by the customer.

```
SMS:
  Business sends: "Your order #1234 has shipped."

RCS:
  Business sends:
  +----------------------------------+
  |  Order #1234 Shipped             |
  |                                  |
  |  iPhone 17 Pro                   |
  |  ETA: Tomorrow, 3-6 PM           |
  |                                  |
  |  [ Track Order ] [ Need Help ]   |
  +----------------------------------+
```

The customer taps "Track Order" and your backend receives a structured event. No typing, no ambiguity.

---

### 6.2 RCS Is a Channel, Not a Technology Stack

This is the single most important thing to lock in.

```
RCS is NOT AI
RCS is NOT n8n
RCS is NOT a chatbot
RCS is NOT WhatsApp Business API (though they are similar concepts)

RCS IS a communication channel and interface
```

The full picture:

```
  Customer (phone's native messaging app)
                  |
                 RCS
                  |
               Vonage
                  |
            Your Backend
                  |
     +------------+------------+
     |            |            |
    CRM          ERP           AI
                  |
                 n8n
             (orchestration)
```

AI decides what to do.
n8n orchestrates which system to call.
RCS is how the customer interacts with the result.

None of them replace each other. They stack.

---

### 6.3 Why RCS Will Not Be Obsolete Soon

AI agents still need a delivery surface to talk to customers. That surface is either:
- An app (requires download)
- A web page (requires browser navigation)
- Email (no real interactivity)
- WhatsApp (requires WhatsApp account, Meta dependency)
- RCS (phone-native, no download, works on Android + iOS 18+)

Google announced end-to-end encrypted RCS between Android and iPhone in May 2026. Apple added RCS support in iOS 18. The channel is growing, not shrinking.

What CAN change quickly:
- Carrier availability in specific countries
- Pricing per message
- Business rules (e.g., promotional limits)
- Feature availability per region

The channel itself is not going away.

---

### 6.4 RCS Message Types — Complete Reference

#### A. Text

Simple text notification.

```json
{
  "channel": "rcs",
  "message_type": "text",
  "text": "Your appointment is confirmed for tomorrow at 10 AM."
}
```

When to use: simple notifications, confirmations, status updates.

---

#### B. Image

```json
{
  "channel": "rcs",
  "message_type": "image",
  "image": {
    "url": "https://yourcdn.com/invoice-preview.jpg"
  }
}
```

When to use: product images, invoice previews, QR codes, promotional banners.

---

#### C. Video

```json
{
  "channel": "rcs",
  "message_type": "video",
  "video": {
    "url": "https://yourcdn.com/how-to-use.mp4"
  }
}
```

When to use: product demos, how-to guides, claim walkthroughs.

---

#### D. File

```json
{
  "channel": "rcs",
  "message_type": "file",
  "file": {
    "url": "https://yourcdn.com/invoice-1234.pdf"
  }
}
```

When to use: invoices, receipts, policy documents, e-tickets.

---

#### E. Rich Card

A card combines image/video + title + description + action buttons into a single interactive unit.

```
+------------------------------+
|      [product image]         |
|                              |
|  iPhone 17 Pro               |
|  Rs. 1,29,999                |
|  Latest model, 256GB         |
|                              |
|  [ Buy Now ]  [ Details ]    |
+------------------------------+
```

Components:
- Media: image or video (tall/medium/short height)
- Title: bold heading
- Description: supporting text
- Suggestions: up to 4 action buttons

When to use: product display, service selection, document approval, appointment slots.

---

#### F. Carousel

Multiple cards in a horizontal scrollable list.

```
<-- [  Plan A  ] [  Plan B  ] [  Plan C  ] -->
    |          | |          | |          |
    | Rs.499/m | | Rs.999/m | | Rs.1999/m|
    | [Select] | | [Select] | | [Select] |
    +----------+ +----------+ +----------+
```

Vonage supports up to 10 cards in a carousel.

When to use: product catalog, appointment time slots, plan comparison, nearby branches.

---

#### G. Suggested Replies

Tappable buttons that remove the need to type.

```
What would you like to do?

[ Track Order ]  [ Return Item ]  [ Change Address ]
```

When user taps, your webhook receives:

```json
{
  "message_type": "reply",
  "reply": {
    "id": "return_item",
    "title": "Return Item"
  }
}
```

This is structured input. You get a clean event ID, not a typed string to interpret.

---

#### H. Suggested Actions

These trigger native phone-level actions:

| Action | What happens on the phone |
|--------|--------------------------|
| open_url | Opens a URL in browser or webview |
| dial | Opens phone dialer with number pre-filled |
| view_location | Opens maps to a specific location |
| share_location | User shares their GPS location to your backend |
| create_calendar_event | Opens calendar with event details pre-filled |

Example:
```
Your appointment is confirmed.

[ Add to Calendar ]  [ Get Directions ]  [ Call Clinic ]
```

---

### 6.5 Vonage's Role — The Real Picture

Vonage is a CPaaS (Communications Platform as a Service).

CPaaS means: a cloud platform that gives developers programmable REST APIs to add messaging, voice, and video into their applications without building telecom infrastructure from scratch.

Vonage's job:
- Manages connectivity to Google's RCS for Business infrastructure and carriers
- Exposes a clean REST API (Messages API) that works the same for RCS, WhatsApp, SMS, Viber etc.
- Handles agent registration, brand verification, carrier onboarding
- Delivers webhooks to your backend when messages arrive or status changes

```
YOUR EXPRESS APP
      |
      |  POST /v1/messages
      v
VONAGE MESSAGES API
      |
      v
VONAGE RCS PLATFORM
      |
      v
GOOGLE RCS FOR BUSINESS INFRASTRUCTURE
      |
      v
CARRIER (Jio / Airtel / Vi)
      |
      v
CUSTOMER'S PHONE (native Messages app)
```

You never talk directly to Google or the carrier. Vonage abstracts that entirely.

---

### 6.6 The Three Concepts You Must Never Confuse

#### Brand
The business or legal entity that owns the messaging identity.
Example: Acme Technologies Pvt Ltd

A Brand is an organizational container. It can have multiple Agents under it.

#### Agent
The RCS messaging identity — what the customer actually sees in their messaging app.
Example: Acme Support or Acme Orders

An Agent has:
- Display name (shown to the customer)
- Logo
- Description / purpose
- Sender ID
- Use case category (OTP / Transactional / Promotional)
- Billing category

#### Vonage Application
Your software integration inside Vonage's system.

Stores:
- Application ID
- Private key (for JWT authentication)
- Inbound webhook URL (where Vonage sends customer messages)
- Status webhook URL (where Vonage sends delivery state changes)

Relationship:
```
Brand
  |
  v
RCS Agent
  |
  v
Vonage Application
  |
  v
Your Express Backend
```

Summary:
- Brand = the company's identity in the telecom world
- Agent = the sender identity the customer sees (like a verified WhatsApp number)
- Vonage Application = the API integration that connects Agent to your code

---

### 6.7 Authentication — JWT in Detail

Vonage supports two authentication methods:

| Method | Use when |
|--------|----------|
| Basic Auth (API Key + Secret) | Quick testing, sandbox exploration |
| JWT (JSON Web Token) | Production — this is the correct approach |

JWT is the production-grade approach. Here is how it works:

```
You have:
  - Application ID    (from Vonage dashboard)
  - Private Key       (PEM file, downloaded once at app creation)

You generate:
  JWT = sign({ application_id, issued_at, expires_at })
        using your private key (RS256 algorithm)

You call:
  POST /v1/messages
  Authorization: Bearer <JWT>

Vonage verifies:
  JWT signature using your stored public key
  If valid, request is allowed
```

Your private key never leaves your server. Vonage holds the matching public key.
This is standard asymmetric cryptography (RS256 = RSA + SHA-256).

JWT has a short expiry (typically 15 minutes). Generate a fresh one per request or cache with sliding window.

Implementation in Node.js:

```typescript
import jwt from 'jsonwebtoken';
import fs from 'fs';

const privateKey = fs.readFileSync('./private.key');

function generateVonageJWT(): string {
  return jwt.sign(
    {
      application_id: process.env.VONAGE_APP_ID,
    },
    privateKey,
    {
      algorithm: 'RS256',
      expiresIn: '15m',
    }
  );
}
```

---

### 6.8 Messages API — The Core Payload Structure

Every outbound message follows this base pattern:

```typescript
interface VonageRCSPayload {
  to: string;         // recipient phone in E.164 format: 919876543210
  from: string;       // your RCS Agent ID
  channel: 'rcs';
  message_type: 'text' | 'image' | 'video' | 'file' | 'rich_card' | 'carousel';
  // ...type-specific fields below
}
```

API Endpoint:
```
POST https://api.nexmo.com/v1/messages
Authorization: Bearer <JWT>
Content-Type: application/json
```

The same endpoint handles SMS, RCS, WhatsApp, Viber. The `channel` field controls the routing. This is the key Vonage abstraction — your backend does not need separate code paths per channel in most cases.

---

### 6.9 Webhooks — The Event-Driven Side

You configure two webhook URLs on your Vonage Application:

#### Inbound Webhook
Triggered when the customer sends a message to your Agent.

Vonage POSTs to your URL:

```json
{
  "from": "919876543210",
  "to": "YOUR_AGENT_ID",
  "channel": "rcs",
  "message_uuid": "aaaabbbb-cccc-dddd-eeee-ffffffffffff",
  "timestamp": "2026-09-29T10:00:00Z",
  "message_type": "text",
  "text": "I want to return my order"
}
```

Or when user taps a suggested reply button:

```json
{
  "from": "919876543210",
  "channel": "rcs",
  "message_type": "reply",
  "reply": {
    "id": "return_item",
    "title": "Return Item"
  }
}
```

#### Status Webhook
Triggered when delivery state of a message you sent changes.

```json
{
  "message_uuid": "aaaabbbb-cccc-dddd-eeee-ffffffffffff",
  "status": "delivered",
  "timestamp": "2026-09-29T10:00:05Z",
  "channel": "rcs"
}
```

Possible statuses:

| Status | Meaning |
|--------|---------|
| submitted | Vonage accepted and queued it |
| delivered | Message reached the device |
| read | Customer opened/read the message |
| rejected | Carrier or Google rejected it |
| undeliverable | Could not be delivered at all |

Your Express webhook endpoint must:
1. Return HTTP 200 immediately (Vonage retries if you do not respond fast)
2. Process the event asynchronously (do not block the HTTP response)
3. Use message_uuid to correlate with your conversation state

---

### 6.10 India-Specific Rules — Critical for POC Design

#### No Multi-Use Agents
A single RCS Agent cannot mix promotional and transactional traffic in India.

```
CORRECT:
  Agent A = Transactional (order updates, OTP, delivery alerts)
  Agent B = Promotional (sales, discounts, campaigns)

WRONG:
  Agent C = Both transactional + promotional (not allowed in India)
```

Impact on your POC: If your use case has both order notifications AND marketing offers, design with two separate agents from the start.

#### Promotional Traffic Limits (Reputation-Based)
New promotional agents start with a low reputation score, limiting how many messages they can send per day. Limits increase as the agent builds a delivery track record.

Impact on your POC: Do not promise stakeholders high-volume blasting on day one with a new agent.

#### Business-Initiated Message Timing
Your agent can only initiate conversations between 7 AM and 10 PM IST.
Replies to user-initiated messages have no time restriction.

#### Carrier Dependency
Not all Indian carriers have uniformly deployed RCS. Confirm with your Vonage account manager which carriers (Jio / Airtel / Vi / BSNL) are supported for your specific agent configuration.

---

### 6.11 Capability Checking — Never Assume

Not every phone/carrier supports all RCS features. Check before sending rich content.

Vonage provides a capability check API:

```
GET /v1/rcs/capabilities/{phone_number}
```

Returns which features the device supports:
- rich_card
- carousel
- calendar_action
- dial_action
- open_url
- share_location
- view_location

Use this to build graceful degradation:

```
User
  |
  v
Capability Check
  |
  +-- Carousel supported?    --> Send carousel
  |
  +-- Rich card only?        --> Send single card
  |
  +-- RCS text only?         --> Send text + URL
  |
  +-- No RCS at all?         --> Fallback to SMS
```

---

### 6.12 Message Failover — Required for Production

Vonage's Messages API supports failover configuration in the same API call:

```json
{
  "to": "919876543210",
  "from": "YOUR_RCS_AGENT",
  "channel": "rcs",
  "message_type": "text",
  "text": "Your order is ready for pickup.",
  "failover": {
    "to": "919876543210",
    "from": "VONAGE_SMS_NUMBER",
    "channel": "sms",
    "message_type": "text",
    "text": "Your order is ready. Track: https://yourapp.com/track/1234"
  }
}
```

Flow:
```
Send RCS
  |
  +-- delivered  -->  done
  |
  +-- rejected / undeliverable
            |
            v
         Send SMS automatically
```

This is essential for any production use case. You cannot assume 100% RCS delivery.

---

### 6.13 Conversation State Machine

RCS conversations are not stateless. You need to track where each user is in the flow.

Each user has a conversation state:

```typescript
interface ConversationState {
  userId: string;               // phone number
  currentStep: string;          // e.g. 'ORDER_SELECTED', 'AWAITING_REASON'
  context: Record<string, any>; // e.g. { orderId: '1234', returnReason: null }
  lastMessageAt: Date;
  expiresAt: Date;              // auto-expire stale conversations
}
```

State transitions happen on inbound webhook events:

```
IDLE
  |
  | [user sends any message]
  v
WELCOME_SHOWN
  |
  | [user taps "Track Order"]
  v
ORDER_LOOKUP
  |
  | [order found]
  v
ORDER_STATUS_SHOWN
  |
  | [user taps "Return Item"]
  v
RETURN_REASON_PROMPT
  |
  | [user selects reason]
  v
RETURN_CONFIRMED
  |
  | [system generates label]
  v
RETURN_LABEL_SENT
  |
  v
IDLE (conversation closed)
```

Store state in Redis (fast, TTL-based expiry handles cleanup automatically) or your database.

---

### 6.14 AI Integration Architecture

AI does not replace RCS. It enhances what happens inside the conversation.

#### Pattern A: AI for Free-Text Understanding

When the user types instead of tapping a button:

```
User types: "my package didn't come and i need it today"
                    |
                    v
              LLM (GPT / Gemini)
                    |
                    +-- intent: "delivery_issue"
                    +-- urgency: "high"
                    +-- entities: { issue: "not_arrived" }
                    |
                    v
         OrderService.getLatestOrder(userId)
                    |
                    v
         RCS Card showing order status + options
```

#### Pattern B: AI for Decision Routing

```
Business Event (order exception detected)
                    |
                    v
          AI Decision Engine
                    |
      +-------------+-------------+
      |             |             |
   Notify        Offer         Escalate
   delay         alt item      to human
                    |
                    v
          RCS Carousel
   (alternative products or appointment slots)
```

Keep AI calls async and non-blocking. Your webhook endpoint must return 200 quickly.

---

### 6.15 n8n Integration Architecture

n8n is an open-source workflow automation tool. It can sit between Vonage webhooks and your business systems.

```
Vonage Webhook (inbound RCS event)
          |
          v
        n8n Flow
          |
  +-------+--------+--------+
  |       |        |        |
 CRM    AI Svc   ERP    Database
  |       |        |        |
  +-------+--------+--------+
          |
          v
   Vonage API (outbound RCS reply)
```

When to use n8n vs custom code:

| Scenario | Recommendation |
|----------|---------------|
| Complex multi-system orchestration | n8n |
| Real-time low-latency responses under 1 second | Custom Express code |
| Business user wants to edit the flow | n8n |
| Developer owns the flow entirely | Custom code |

For the POC, custom Express gives more control and is easier to explain in a demo. n8n can be layered in later.

---

### 6.16 Agent Lifecycle — Full Onboarding Flow

```
STEP 1: Vonage Account
  - Create account at developer.vonage.com
  - Get API key + secret

STEP 2: Vonage Application
  - Create application in dashboard
  - Download private key (store it securely, never commit to Git)
  - Set inbound webhook URL
  - Set status webhook URL

STEP 3: Brand Creation
  - Legal entity name
  - Business description
  - Business logo
  - Website URL

STEP 4: RCS Agent Creation
  - Agent display name (what customer sees)
  - Agent logo
  - Use case: OTP / Transactional / Promotional
  - Billing category: Conversational / Non-Conversational
  - Agent description

STEP 5: Country and Carrier Selection
  - Select India
  - Select supported carriers (Jio, Airtel, Vi etc.)

STEP 6: Developer Mode
  - Allow-list up to 50 test phone numbers
  - Test all message types
  - Test webhook flows end-to-end

STEP 7: Brand Verification
  - Vonage / Google verifies you represent the brand
  - Authorized representative must confirm

STEP 8: Carrier Launch Submission
  - Submit for production launch
  - Google / carrier approves

STEP 9: Production
  - Agent goes live
  - Can now reach all RCS-capable users on supported carriers
```

For your POC: Steps 1 through 6 are sufficient. You do not need production launch to build and demo.

---

### 6.17 Security Checklist

| Item | Action |
|------|--------|
| Private key storage | Never commit to Git. Use env variable or secret manager |
| JWT expiry | Short-lived, 15 minutes max |
| Webhook signature validation | Validate Vonage HMAC signature on every inbound webhook |
| Phone number validation | Validate E.164 format before calling API |
| Rate limiting | Apply rate limiting on your webhook endpoint |
| Idempotency | Use message_uuid to deduplicate repeated webhook deliveries |
| Conversation TTL | Expire stale conversations after 24h of inactivity |
| Error handling | Never expose raw internal errors to the customer via RCS |

---

### 6.18 Production Architecture Blueprint

```
                     CUSTOMER
                         |
                        RCS
                         |
                      VONAGE
                         |
          +--------------+--------------+
          |                             |
   Inbound Webhook              Status Webhook
          |                             |
          v                             v
    API Gateway                  Event Logger
          |
          v
  Conversation Orchestrator
          |
   +------+------+------+
   |       |      |      |
   AI    State  Rules  Context
          DB
   |       |      |      |
   +------+------+------+
          |
   +------+------+------+
   |       |            |
  CRM     ERP      External APIs
          |
          v
    Business Logic
          |
          v
      VONAGE API
          |
          v
      RCS Response
```

---

## 7. Manager / Vonage Message

Copy this email exactly. Replace [YOUR COMPANY NAME] and [YOUR NAME].

---

Subject: RCS POC Technical Requirements and Questions — One-Time Clarification Needed

Hi [Manager / Vonage Contact Name],

I am building the RCS by Vonage POC for [YOUR COMPANY NAME] and want to consolidate all technical requirements and questions into one communication so we can move ahead without back-and-forth.

Context: We are building an enterprise-grade RCS POC demonstrating rich interactive conversations, AI-assisted routing, backend API integration, conversation state management, and RCS-to-SMS fallback. Target region: India.

--- A. Account and Access ---

1. Is our Vonage account a managed account? (Vonage documentation states RCS is currently available to managed accounts only.)
2. Is RCS messaging enabled on our account?
3. Can you enable Developer Mode so we can test with allow-listed phone numbers before production launch?
4. Who is our Account Manager for ongoing RCS technical queries?

--- B. Agent and Brand Setup ---

5. Do we create the Brand and RCS Agent ourselves via Agent Builder, or does Vonage's team do this during onboarding?
6. For India, which use cases are available?
   - OTP
   - Transactional (order updates, alerts, notifications)
   - Promotional (marketing, campaigns)
   - Multi-use (transactional + promotional in one agent — we understand this may be unavailable in India, please confirm)
7. If Multi-use is not available, can we create two separate agents — one Transactional, one Promotional — under the same Brand? What is that process?
8. What are the visual/branding requirements for the Agent? (logo dimensions, description character limits, etc.)

--- C. India Carrier Support ---

9. Which Indian carriers currently have full RCS support via Vonage?
   - Jio
   - Airtel
   - Vi (Vodafone Idea)
   - BSNL
10. Are there carrier-specific limitations on RCS message types in India?
11. Confirm the business-initiated message timing rule for India: can we only send outbound messages between 7 AM and 10 PM IST?

--- D. RCS Features Available in India ---

12. Which of the following are available for our agent in India? Please mark each Yes / Partial / No:
    - Text messages
    - Image messages
    - Video messages
    - File messages (PDF etc.)
    - Rich Cards (single card with buttons)
    - Carousels (horizontal scrolling cards, up to 10)
    - Suggested Replies (tappable buttons)
    - Suggested Action: Open URL
    - Suggested Action: Dial Number
    - Suggested Action: View Location (map)
    - Suggested Action: Share Location (user shares GPS)
    - Suggested Action: Create Calendar Event
    - Read receipts (delivered / read status events)
    - RCS Capability Check API (per phone number)
    - Message failover to SMS within the same API call

--- E. Developer and API Details ---

13. What is the API endpoint for sending RCS messages? (Standard: https://api.nexmo.com/v1/messages)
14. Which authentication method should we use? (We plan JWT with RS256 using Vonage Application private key — please confirm this is correct for RCS.)
15. Vonage Application configuration needed:
    - Inbound webhook URL format
    - Status webhook URL format
    - Any additional webhook event types we should handle
16. What is the correct value for the "from" field in the Messages API payload for RCS? (Agent ID / name / specific sender string?)
17. Is there a webhook signature or HMAC validation mechanism we should implement to verify webhooks are genuinely from Vonage?
18. What are the rate limits per second, per minute, and per day for our account?
19. What are the message size limits for each type? (image file size, video file size, carousel card count, etc.)
20. What is the exact endpoint for the RCS Capability Check API?

--- F. Testing ---

21. How do we add test phone numbers to the allow-list for Developer Mode?
22. How many test numbers can be allow-listed? (Documentation mentions up to 50 — please confirm.)
23. Do test phones need to be on specific carriers for Developer Mode, or does any RCS-capable Indian number work?
24. Is there a sandbox or test mode to simulate responses without real carrier delivery?
25. Do you have Postman collections or code samples in Node.js / TypeScript for RCS messages?

--- G. Pricing and Billing ---

26. Per-message pricing for RCS in India, broken down by:
    - Transactional messages
    - Promotional messages
    - OTP messages
27. What is the billing category difference between Conversational and Non-Conversational, and how does it affect pricing?
28. Can the billing category be changed after the Agent is launched?
29. Are there monthly minimums or setup fees for the RCS managed account?

--- H. Production Launch and Compliance ---

30. What is the full production launch timeline once testing is complete?
31. What are the brand verification requirements? What documents or proof does Vonage/Google need?
32. Is there a DLT (Distributed Ledger Technology) registration requirement for RCS in India, similar to what exists for SMS?
33. Are there content restrictions or compliance requirements specific to India (TRAI etc.) for RCS promotional messaging?
34. What are the consequences of a spam complaint on our agent's reputation score?

--- I. Architecture Questions ---

35. Can one Vonage Application be linked to multiple RCS Agents (one transactional + one promotional)?
36. Can we route inbound messages from multiple agents to the same webhook URL, differentiated by a field in the payload?
37. Does Vonage support multi-turn conversation session management, or is state management entirely our responsibility?
38. Is there a message TTL (time to live) configuration — after which Vonage stops retrying and marks as undeliverable?

Please share answers to all of the above at once. We want to avoid multiple rounds of follow-up. A technical call with your RCS solutions engineer would also be very helpful if possible.

Thank you.
[YOUR NAME]

---

## 8. Where You Are Stuck Right Now

| Blocker | Why it blocks you | Unblocked by |
|---------|-------------------|--------------|
| No managed account confirmed | RCS is not enabled on free/standard accounts | Manager message to Vonage |
| No Agent ID | You need the "from" value to send any RCS message | Account manager enabling RCS + Agent creation |
| No test phone on allow-list | Developer Mode needed for any real testing | Vonage enabling Developer Mode |
| No Vonage Application | No credentials to authenticate API calls | Can be done in dashboard once account confirmed |
| POC use case not finalized | Cannot design state machine without a scenario | Your decision — see Action 2 below |
| India feature list unknown | Cannot design conversation if carousel is not supported | Answer to question 12 in the manager message |

---

## 9. Next Action Items (In Order)

```
ACTION 1 — Do this today
  Send the manager message above
  Get it forwarded to Vonage account team
  Ask for a technical call with their solutions engineer

ACTION 2 — While waiting for Vonage response
  Decide your POC use case domain
  Options: e-commerce / banking / healthcare / logistics
  Tell me which one and we design the full conversation flow together

ACTION 3 — After use case decided (we do this together)
  Design the full conversation flow on paper
  Every screen, every button, every branch
  State machine diagram

ACTION 4 — After Vonage confirms access
  Create Vonage Application in dashboard
  Download private key
  Configure webhook URLs (use ngrok for local development)

ACTION 5 — First code
  Express project setup
  JWT generation
  Send first RCS text message
  Receive first webhook

ACTION 6 — Build up message types incrementally
  Text -> Image -> Card -> Carousel -> Replies -> Actions

ACTION 7 — Build conversation orchestrator
  State machine + Redis state storage
  Full conversation flow for chosen POC use case

ACTION 8 — Add intelligence
  Capability check + graceful degradation
  AI layer for free-text input handling
  SMS fallback

ACTION 9 — Polish and demo
  End-to-end on real test device
  Observability and logging
  Demo script for stakeholders
```

---

## 10. First Principles: The "Stripe Model" vs. The "RCS Telecom Model"

If you are used to modern SaaS APIs like Stripe, AWS, or Twilio SMS, the RCS ecosystem feels like it is full of unnecessary bureaucracy. Here is the first-principles breakdown of why.

### The "Stripe Model" (Typical SaaS)
1. You go to a website and click "Sign Up".
2. You get an API Key immediately.
3. You put that API key in your Express app.
4. You call an endpoint (`POST /v1/charges`).
5. The provider processes the request.
*You are in total control. You don't need anyone's permission to build and test.*

### The "RCS Telecom Model"
RCS is a **regulated telecom channel**. When you send an RCS message, it doesn't just go from your server to Vonage to the user. It goes:
`Your Server -> Vonage -> Google's RCS Servers -> The Indian Telecom Carrier (Jio/Airtel) -> The User's Phone`.

Because you are sending rich, branded messages directly into a user's native text messaging app (which is highly protected against spam), you cannot just sign up and start sending messages. 

The carriers (Jio, Airtel) and Google demand to know exactly *who* is sending the message, *what* they are sending, and whether they are a *verified business*. 

### The Three Layers of RCS Identity

To understand what you need to build, you must understand the three layers of identity:

#### Layer 1: The Vonage Application (The Code Layer)
You create a "Vonage Application" in the dashboard. You get an **Application ID** and a **Private Key** (used to generate a JWT token for authentication). 
*BUT... an Application ID alone cannot send an RCS message. It has no "Sender" identity yet.*

#### Layer 2: The Brand (The Legal Layer)
Google and the carriers need to verify your company is real. Vonage registers your company as a "Brand" (e.g., *Your Company Pvt Ltd*). 

#### Layer 3: The RCS Agent (The Phone Identity Layer)
This is the most important concept. Think of an **Agent** like a verified WhatsApp Business number. The Agent has a Name (e.g., *Your Company Support*), a Logo, and a specific "Use Case" (e.g., Transactional updates). 

**How they connect:** Your Express code uses the **Vonage Application credentials** to tell Vonage: "Hey, I want to send a message *on behalf of* the **RCS Agent**."

### The "Developer Mode" Workaround
Normally, you can't send messages until Jio/Airtel approves your Agent (which takes weeks). 
**Developer Mode** is the workaround. It allows you to say, "Hey Vonage, I am just testing. Please whitelist these 5 specific phone numbers." Vonage will then deliver messages *only* to those 5 phones, instantly, without waiting for carrier approval.

### What You Need to Write Your First Line of Code
To actually test an API request, you need these four exact things:
1. **Vonage enables RCS on your account.**
2. **You get your API Credentials:** (Application ID and Private Key from the dashboard).
3. **You get an Agent ID:** (The `from` string to use in your API call).
4. **You Whitelist your Phone Number:** (Add your personal Indian phone number to the Developer Mode whitelist).
