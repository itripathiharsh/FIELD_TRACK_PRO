# FieldTrack Pro — User Journey
### Phase 2.5 — UX & Wireframes (continued)

Where User Flows mapped screens and taps, this maps the lived experience — what each persona is trying to accomplish, what they're feeling, and where friction or trust breaks down if the product gets it wrong. This is what should guide tone, copy, and error-state design when wireframes/UI actually get built.

---

## 1. Employee Journey — "A Day in the Field"

| Stage | What They're Doing | What They Need | Risk if Product Gets It Wrong |
|---|---|---|---|
| **Start of Day** | Opens app, checks assigned visits | Fast load, clear list, no ambiguity about what's next | If the list is confusing or slow, the day starts with friction before the first visit even happens |
| **Traveling to Customer** | Navigating unfamiliar roads/areas, possibly with poor network | One-tap navigation handoff, doesn't need to fight the app while driving | A clunky nav flow means they'll just use Google Maps separately and lose the connection back to the visit record |
| **Arriving On-Site** | Physically at (or near) the customer location | Fast, frictionless check-in — this is the moment that proves they did their job | This is the highest-stakes moment in the whole app. If geo-verification fails for a legitimate visit (bad GPS signal, radius too tight), the employee feels **accused**, not assisted. This is where trust in the tool is won or lost. |
| **During the Visit** | Talking to the customer, capturing requirements, may be juggling paperwork simultaneously | A form that doesn't feel like a burden on top of an actual sales/service conversation | If the form is long or rigid, employees will rush it or fill it in later from memory — defeating the point of real-time capture |
| **Capturing Signatures** | Asking the customer to sign on a phone screen | A simple, familiar gesture (most people have signed on phones before — delivery apps, etc.) | A finicky signature pad reflects badly on the employee in front of the customer, not just the app |
| **Leaving / Poor Signal Area** | May lose connectivity right after finishing | Confidence that their work is saved, not lost | If sync status is unclear, the employee's biggest fear is redoing work or having it "not count" — the offline banner and pending-sync badge exist specifically to remove this fear |
| **End of Day** | Reflecting on visits completed | A sense of a day well-documented, not surveilled | If the app feels like a tracking device rather than a work tool, adoption resistance follows — this is a real risk with any GPS-based field app and worth being deliberate about in copy/tone |

**Design implication carried forward:** every geo-verification failure message needs to sound like troubleshooting ("Let's get you checked in — try moving closer or check your GPS signal") not accusation ("Location verification failed"). Small copy choice, real trust impact.

---

## 2. Admin/Manager Journey — "Managing a Distributed Team"

| Stage | What They're Doing | What They Need | Risk if Product Gets It Wrong |
|---|---|---|---|
| **Morning Planning** | Reviewing today's scheduled visits, checking who's assigned where | A clear overview without digging through multiple screens | If the overview buries the useful info, admins fall back to spreadsheets/WhatsApp — the exact behavior this product replaces |
| **Throughout the Day — Passive Monitoring** | Occasionally glancing at the live status board between other work | At-a-glance status, not a screen that demands constant attention | An overly busy dashboard becomes noise the admin tunes out, defeating the "real-time visibility" pitch |
| **Handling a Flagged Visit** | Notices a geo-verification failure, needs to decide: genuine problem or GPS glitch? | Enough context (distance off, reason code, employee's history) to make a fair judgment call quickly | If flagged visits look identical to genuine fraud, admins may punish employees for GPS flakiness — this is where the tool could actively damage manager-employee trust if not designed carefully |
| **End of Week/Month — Reporting** | Pulling productivity and visit reports, possibly for their own manager or for payroll/incentive decisions | Trustworthy, exportable numbers they can stand behind | If report numbers ever look inconsistent with what admins observed day-to-day, the entire system's credibility is at risk — this is the moment the whole product either earns long-term trust or gets quietly abandoned |
| **Onboarding a New Employee/Customer** | Adding records, assigning territory | A fast add flow that doesn't feel like data entry drudgery | Slow/clunky admin forms are a recurring reason internal tools get bypassed in favor of "I'll just message the team" |

**Design implication carried forward:** the Flagged Visit Review screen (already flagged as needing real design attention in the Web Dashboard Screen List) is the single highest-trust-risk surface in the entire product — it's where the tool could either fairly protect a hardworking employee's record or unfairly indict them over a GPS hiccup.

---

## 3. Cross-Cutting Journey Insight

Both personas ultimately want the same thing from different sides: **proof that the work happened, without friction and without feeling surveilled or unfairly judged.** The entire product's success hinges less on features and more on whether the geo-verification failure/flagging experience feels like a fair, explainable system rather than a black-box accusation — for both the employee living it in the field and the admin making calls from behind a screen.

This is the throughline that should override any small feature debate later: **when in doubt, design for trust and explainability over strict enforcement.**

---

**Next up:** Low-fidelity wireframes for the highest-priority screens (Check-in flow, Flagged Visit Review) — or straight into Phase 3 Backend Development if you'd rather let Antigravity generate UI directly from the Screen Lists + this journey doc as tone/context.
