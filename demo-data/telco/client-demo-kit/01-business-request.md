# Business request - Subscriber churn and ARPU data product

**From:** Head of Customer Retention, Nimbus Mobile (fictional demo client)  
**To:** Data & Analytics delivery team

## What we need

The Customer Retention team needs a monthly subscriber view with revenue, usage and churn flags so they can track churn rate and ARPU by segment and product family, and feed the retention campaign list. Start with postpaid mobile.

## Who will use it

- **Retention manager** - "What is the monthly churn rate by segment?"
- **Finance analyst** - "What is ARPU by product family?"
- **Data science team** - "Which usage patterns precede churn?"

## How we will know it worked

- Monthly churn rate and ARPU match Finance's month-end pack within 0.5%.
- Retention analysts stop maintaining their own spreadsheet extracts.
- Subscriber phone numbers and names are never visible to analysts.

## Constraints

- Start with postpaid mobile only; prepaid and fixed-line are later phases.
- Data must be ready by the 2nd business day after month end.
- Source systems: CRM, the billing support system (BSS) and usage mediation.
