"""Golden demo scenarios, one per Domain Pack.

Used by the offline Demo Simulator so a full lifecycle can be shown without any LLM key,
and as the "golden use case" (BUILD_SPEC 8.3): small, synthetic, with known answers.
Each attribute carries its source and transformation; the mapping agent turns those into
MAP rows and the design agent drops them from the logical model.
"""
from __future__ import annotations


def A(name, type_, src, tr="direct", cls="internal", pk=False, fk=None, br=None, desc="", nullable=None, req=None):
    return {"name": name, "type": type_, "source": src, "transformation": tr, "classification": cls, "pk": pk,
            "fk": ({"entity": fk[0], "attribute": fk[1]} if fk else None), "business_rule": br, "description": desc,
            "nullable": (not pk) if nullable is None else nullable, "req_ids": req or []}


def C(name, type_, cls="internal", pk=False, desc=""):
    return {"name": name, "type": type_, "classification": cls, "pk": pk, "description": desc}


def DQ(id_, entity, attr, type_, params=None, threshold=1.0, severity="high", req="REQ-001", desc=""):
    return {"id": id_, "entity": entity, "attribute": attr, "type": type_, "params": params or {},
            "threshold": threshold, "severity": severity, "requirement": req, "description": desc}


UTILITIES = {
    "id": "utilities-meter-to-cash",
    "title": "Meter-to-cash billed consumption data product",
    "request": ("Finance and Customer Operations need a trusted monthly view of billed versus metered "
                "consumption per customer account, so they can find billing leakage and track estimated "
                "reads. Start with residential accounts in one region; reconcile to the monthly revenue report."),
    "consumers": [("Revenue Assurance analysts", "Where is billed consumption below metered consumption?"),
                  ("Customer Operations lead", "What share of bills rely on estimated reads?"),
                  ("Finance controller", "Does billed kWh reconcile to the monthly revenue report?")],
    "sources": [
        {"system": "customer-information-system", "table": "cis.account", "owner": "Billing Operations",
         "refresh": "daily batch", "description": "Customer accounts and status",
         "columns": [C("account_id", "string(20)", pk=True), C("customer_name", "string(200)", "restricted"),
                     C("service_address", "string(400)", "restricted"), C("account_status", "string(1)"),
                     C("rate_class", "string(10)"), C("open_date", "date"), C("close_date", "date"),
                     C("updated_at", "timestamp")]},
        {"system": "customer-information-system", "table": "cis.premise", "owner": "Billing Operations",
         "refresh": "daily batch", "description": "Service premises",
         "columns": [C("premise_id", "string(20)", pk=True), C("account_id", "string(20)"),
                     C("premise_type", "string(20)"), C("region_code", "string(10)"),
                     C("postal_code", "string(10)", "confidential")]},
        {"system": "meter-data-management", "table": "mdm.meter", "owner": "Metering Services",
         "refresh": "daily batch", "description": "Installed meters",
         "columns": [C("meter_id", "string(20)", pk=True), C("premise_id", "string(20)"),
                     C("meter_type", "string(10)"), C("install_date", "date"), C("status", "string(10)")]},
        {"system": "meter-data-management", "table": "mdm.daily_read", "owner": "Metering Services",
         "refresh": "daily batch", "description": "Validated daily register reads (high volume)",
         "columns": [C("meter_id", "string(20)", pk=True), C("read_date", "date", pk=True),
                     C("kwh", "decimal(18,3)", "restricted", desc="usage linked to a premise"),
                     C("read_quality", "string(1)"), C("loaded_at", "timestamp")]},
        {"system": "customer-information-system", "table": "cis.bill", "owner": "Billing Operations",
         "refresh": "daily batch", "description": "Issued bills",
         "columns": [C("bill_id", "string(20)", pk=True), C("account_id", "string(20)"), C("period_start", "date"),
                     C("period_end", "date"), C("billed_kwh", "decimal(18,3)"), C("amount_due", "decimal(18,2)"),
                     C("bill_status", "string(10)")]},
    ],
    "entities": [
        {"name": "customer_account", "kind": "dimension", "history": "type2", "subject_area": "customer",
         "grain": "one row per customer account version", "description": "Billing account of a customer",
         "attributes": [
             A("customer_account_id", "string(20)", "cis.account.account_id", pk=True, desc="Business key of the account", req=["REQ-001"]),
             A("account_status", "string(1)", "cis.account.account_status", desc="A=active, I=inactive, C=closed", req=["REQ-001"]),
             A("rate_class", "string(10)", "cis.account.rate_class", desc="Tariff rate class", req=["REQ-004"]),
             A("customer_name", "string(200)", "cis.account.customer_name", cls="restricted", desc="Account holder name (masked for consumers)", req=["REQ-005"]),
             A("open_date", "date", "cis.account.open_date", desc="Account open date"),
         ]},
        {"name": "premise", "kind": "dimension", "history": "type1", "subject_area": "customer",
         "grain": "one row per premise", "description": "Service location",
         "attributes": [
             A("premise_id", "string(20)", "cis.premise.premise_id", pk=True, desc="Business key of the premise"),
             A("customer_account_id", "string(20)", "cis.premise.account_id", fk=("customer_account", "customer_account_id"), desc="Owning account"),
             A("premise_type", "string(20)", "cis.premise.premise_type", desc="Residential, commercial, industrial", req=["REQ-004"]),
             A("region_code", "string(10)", "cis.premise.region_code", desc="Operating region", req=["REQ-004"]),
         ]},
        {"name": "meter", "kind": "dimension", "history": "type1", "subject_area": "metering",
         "grain": "one row per meter", "description": "Installed meter",
         "attributes": [
             A("meter_id", "string(20)", "mdm.meter.meter_id", pk=True, desc="Business key of the meter"),
             A("premise_id", "string(20)", "mdm.meter.premise_id", fk=("premise", "premise_id"), desc="Premise where installed"),
             A("meter_type", "string(10)", "mdm.meter.meter_type", desc="AMI or legacy"),
             A("install_date", "date", "mdm.meter.install_date", desc="Installation date"),
         ]},
        {"name": "billed_consumption", "kind": "fact", "history": "none", "subject_area": "billing",
         "grain": "one row per final bill", "description": "Billed versus metered consumption per bill",
         "attributes": [
             A("bill_id", "string(20)", "cis.bill.bill_id", pk=True, desc="Business key of the bill", req=["REQ-001"]),
             A("customer_account_id", "string(20)", "cis.bill.account_id", fk=("customer_account", "customer_account_id"), desc="Billed account", req=["REQ-001"]),
             A("bill_period_start", "date", "cis.bill.period_start", desc="First day of bill period", req=["REQ-001"]),
             A("bill_period_end", "date", "cis.bill.period_end", desc="Last day of bill period", req=["REQ-001"]),
             A("billed_kwh", "decimal(18,3)", "cis.bill.billed_kwh", desc="kWh on the bill", req=["REQ-001"], br="BR-003"),
             A("metered_kwh", "decimal(18,3)", "mdm.daily_read.kwh", tr="SUM(kwh) of reads for the account's meters within the bill period", desc="Metered kWh in the bill period", req=["REQ-002"], br="BR-001"),
             A("estimated_read_share", "decimal(5,4)", "mdm.daily_read.read_quality", tr="COUNT(read_quality='E') / COUNT(*) within the bill period", desc="Share of estimated reads", req=["REQ-003"], br="BR-002"),
             A("variance_kwh", "decimal(18,3)", "derived", tr="billed_kwh - metered_kwh", desc="Billed minus metered kWh", req=["REQ-002"], br="BR-004"),
             A("amount_due", "decimal(18,2)", "cis.bill.amount_due", desc="Amount billed", req=["REQ-006"]),
         ]},
    ],
    "requirements": [
        ("REQ-001", "Provide one row per final bill with account, bill period and billed kWh.", "a final bill exists in the source", "the data product is refreshed", "one row exists for that bill with matching billed kWh"),
        ("REQ-002", "Compare billed kWh with metered kWh for the same bill period and expose the variance.", "daily reads exist for the account's meters in the bill period", "the bill is loaded", "metered kWh equals the sum of those reads and variance equals billed minus metered"),
        ("REQ-003", "Show the share of estimated reads behind each bill.", "a bill period includes estimated reads", "the bill is loaded", "estimated read share equals estimated reads divided by all reads"),
        ("REQ-004", "Allow analysis by region, premise type and rate class.", "an analyst filters by region", "they query the data product", "only bills for premises in that region are returned"),
        ("REQ-005", "Customer personal data is masked for all consumers outside Billing Operations.", "a Revenue Assurance analyst queries accounts", "they view the account name", "the value is masked"),
        ("REQ-006", "Total billed kWh for a month reconciles to the monthly revenue report within 0.5 percent.", "the month is closed", "the reconciliation runs", "the difference is within 0.5 percent"),
    ],
    "business_rules": [
        ("BR-001", "Metered kWh is the sum of daily reads for all meters at the account's premises within the bill period (inclusive).", "Reads of 10, 12 and 8 kWh in a 3-day period give 30 kWh."),
        ("BR-002", "Estimated read share is estimated reads divided by all reads in the bill period.", "3 estimated of 30 reads gives 0.1000."),
        ("BR-003", "Only bills with status FINAL are in scope; cancelled and draft bills are excluded.", "A CANCELLED bill does not appear."),
        ("BR-004", "Variance kWh is billed kWh minus metered kWh; negative means under-billing.", "Billed 300, metered 320 gives -20."),
    ],
    "nfrs": [
        ("NFR-001", "Data is available by 06:00 local time each day for the previous day's bills.", "freshness <= 6 hours after source close"),
        ("NFR-002", "Daily load completes within 30 minutes at 2 million reads per day.", "runtime <= 30 min"),
        ("NFR-003", "Point-in-time results are reproducible for regulatory reporting.", "history retained, re-run gives identical totals"),
    ],
    "dq": [
        DQ("DQ-001", "billed_consumption", "bill_id", "not_null", req="REQ-001"),
        DQ("DQ-002", "billed_consumption", "bill_id", "unique", req="REQ-001"),
        DQ("DQ-003", "billed_consumption", "customer_account_id", "referential", {"to_entity": "customer_account", "to_attribute": "customer_account_id"}, req="REQ-001"),
        DQ("DQ-004", "customer_account", "account_status", "accepted_values", {"values": ["A", "I", "C"]}, severity="medium", req="REQ-001"),
        DQ("DQ-005", "billed_consumption", "billed_kwh", "range", {"min": 0, "max": 100000}, threshold=0.999, req="REQ-001"),
        DQ("DQ-006", "billed_consumption", "estimated_read_share", "range", {"min": 0, "max": 1}, req="REQ-003"),
        DQ("DQ-007", "customer_account", "customer_account_id", "unique", {"where": "is_current = 1"}, req="REQ-001"),
        DQ("DQ-008", "billed_consumption", None, "row_count_min", {"min": 1}, severity="critical", req="REQ-001"),
    ],
    "metrics": [
        {"name": "avg_billed_kwh_per_account", "label": "Average billed kWh per account", "entity": "billed_consumption",
         "measure": {"agg": "sum", "attribute": "billed_kwh"}, "denominator": {"agg": "count_distinct", "attribute": "customer_account_id"},
         "unit": "kWh", "business_rule": "BR-001", "grain": "month",
         "definition": "Total billed kWh divided by number of distinct billed accounts in the period."},
        {"name": "total_billed_kwh", "label": "Total billed kWh", "entity": "billed_consumption",
         "measure": {"agg": "sum", "attribute": "billed_kwh"}, "denominator": None, "unit": "kWh",
         "business_rule": "BR-003", "grain": "month", "definition": "Sum of billed kWh on final bills."},
    ],
}

TELCO = {
    "id": "telco-churn",
    "title": "Subscriber churn and ARPU data product",
    "request": ("The Customer Retention team needs a monthly subscriber view with revenue, usage and churn "
                "flags so they can track churn rate and ARPU by segment and product family, and feed the "
                "retention campaign list. Start with postpaid mobile."),
    "consumers": [("Retention manager", "What is the monthly churn rate by segment?"),
                  ("Finance analyst", "What is ARPU by product family?"),
                  ("Data science team", "Which usage patterns precede churn?")],
    "sources": [
        {"system": "crm", "table": "crm.subscriber", "owner": "Customer Care", "refresh": "daily batch",
         "description": "Subscribers", "columns": [C("subscriber_id", "string(20)", pk=True), C("msisdn", "string(15)", "restricted"),
                                                   C("full_name", "string(200)", "restricted"), C("segment", "string(20)"),
                                                   C("activation_date", "date"), C("status", "string(12)")]},
        {"system": "billing-support-system", "table": "bss.subscription", "owner": "Billing", "refresh": "daily batch",
         "description": "Product subscriptions", "columns": [C("subscription_id", "string(20)", pk=True), C("subscriber_id", "string(20)"),
                                                            C("product_code", "string(12)"), C("start_date", "date"),
                                                            C("end_date", "date"), C("monthly_fee", "decimal(12,2)")]},
        {"system": "billing-support-system", "table": "bss.product_catalog", "owner": "Product", "refresh": "weekly",
         "description": "Product catalogue", "columns": [C("product_code", "string(12)", pk=True), C("product_name", "string(100)"),
                                                         C("product_family", "string(30)"), C("list_price", "decimal(12,2)", "confidential")]},
        {"system": "usage-mediation", "table": "usage.daily_usage_summary", "owner": "Network Operations", "refresh": "daily batch",
         "description": "Aggregated daily usage per subscriber", "columns": [C("subscriber_id", "string(20)", pk=True), C("usage_date", "date", pk=True),
                                                                              C("data_mb", "decimal(14,2)", "restricted"), C("voice_min", "decimal(10,2)", "restricted")]},
        {"system": "crm", "table": "crm.churn_event", "owner": "Customer Care", "refresh": "daily batch",
         "description": "Port-out and disconnection events", "columns": [C("subscriber_id", "string(20)", pk=True), C("churn_date", "date"),
                                                                           C("churn_reason", "string(40)")]},
    ],
    "entities": [
        {"name": "subscriber", "kind": "dimension", "history": "type2", "subject_area": "customer",
         "grain": "one row per subscriber version", "description": "Mobile subscriber",
         "attributes": [
             A("subscriber_id", "string(20)", "crm.subscriber.subscriber_id", pk=True, desc="Business key", req=["REQ-001"]),
             A("segment", "string(20)", "crm.subscriber.segment", desc="Consumer, SME or Enterprise", req=["REQ-002"]),
             A("status", "string(12)", "crm.subscriber.status", desc="ACTIVE, SUSPENDED or CHURNED", req=["REQ-001"]),
             A("activation_date", "date", "crm.subscriber.activation_date", desc="Activation date"),
             A("msisdn", "string(15)", "crm.subscriber.msisdn", cls="restricted", desc="Phone number (masked)", req=["REQ-005"]),
         ]},
        {"name": "product", "kind": "dimension", "history": "type1", "subject_area": "product",
         "grain": "one row per product", "description": "Product offering",
         "attributes": [
             A("product_code", "string(12)", "bss.product_catalog.product_code", pk=True, desc="Business key"),
             A("product_name", "string(100)", "bss.product_catalog.product_name", desc="Product name"),
             A("product_family", "string(30)", "bss.product_catalog.product_family", desc="Product family", req=["REQ-003"]),
         ]},
        {"name": "subscription_month", "kind": "fact", "history": "none", "subject_area": "usage",
         "grain": "one row per subscriber per month", "description": "Monthly revenue, usage and churn per subscriber",
         "attributes": [
             A("subscription_month_id", "string(30)", "derived", tr="subscriber_id || '-' || month", pk=True, desc="Surrogate business key"),
             A("subscriber_id", "string(20)", "bss.subscription.subscriber_id", fk=("subscriber", "subscriber_id"), desc="Subscriber", req=["REQ-001"]),
             A("product_code", "string(12)", "bss.subscription.product_code", fk=("product", "product_code"), desc="Main product", req=["REQ-003"]),
             A("month_start", "date", "derived", tr="first day of month", desc="Month", req=["REQ-001"]),
             A("monthly_revenue", "decimal(12,2)", "bss.subscription.monthly_fee", tr="prorated monthly fee", desc="Revenue in month", req=["REQ-003"], br="BR-001"),
             A("data_mb", "decimal(14,2)", "usage.daily_usage_summary.data_mb", tr="SUM over month", desc="Data used", req=["REQ-004"]),
             A("voice_min", "decimal(10,2)", "usage.daily_usage_summary.voice_min", tr="SUM over month", desc="Voice minutes", req=["REQ-004"]),
             A("is_churned", "boolean", "crm.churn_event.churn_date", tr="churn_date within month", desc="Churned in month", req=["REQ-002"], br="BR-002"),
         ]},
    ],
    "requirements": [
        ("REQ-001", "Provide one row per active or churned subscriber per month.", "a subscriber was active during a month", "the month closes", "one row exists for that subscriber and month"),
        ("REQ-002", "Flag churn in the month a port-out or disconnection occurs.", "a churn event dated in March", "March is loaded", "the March row is flagged churned"),
        ("REQ-003", "Report ARPU by product family.", "subscribers on two product families", "ARPU is calculated", "revenue is split by family"),
        ("REQ-004", "Include monthly data and voice usage per subscriber.", "daily usage exists", "the month is loaded", "usage equals the monthly sum"),
        ("REQ-005", "Subscriber identifiers and phone numbers are masked for analytical consumers.", "an analyst queries subscribers", "they view the phone number", "the value is masked"),
    ],
    "business_rules": [
        ("BR-001", "Monthly revenue is the monthly fee prorated by active days in the month.", "Fee 30.00, active 15 of 30 days gives 15.00."),
        ("BR-002", "A subscriber is churned in the month of their first churn event; later events are ignored.", "Port-out on 12 March flags March only."),
        ("BR-003", "Churn rate is churned subscribers divided by subscribers with a row in the month.", "5 churned of 100 gives 5.0 percent."),
    ],
    "nfrs": [("NFR-001", "Month-end data is available by the 2nd business day.", "freshness <= 2 business days"),
             ("NFR-002", "Usage aggregation handles 50 million subscriber-days per month.", "runtime <= 1 hour")],
    "dq": [
        DQ("DQ-001", "subscription_month", "subscription_month_id", "unique", req="REQ-001"),
        DQ("DQ-002", "subscription_month", "subscriber_id", "not_null", req="REQ-001"),
        DQ("DQ-003", "subscription_month", "subscriber_id", "referential", {"to_entity": "subscriber", "to_attribute": "subscriber_id"}, req="REQ-001"),
        DQ("DQ-004", "subscriber", "status", "accepted_values", {"values": ["ACTIVE", "SUSPENDED", "CHURNED"]}, severity="medium", req="REQ-002"),
        DQ("DQ-005", "subscription_month", "monthly_revenue", "range", {"min": 0, "max": 5000}, threshold=0.999, req="REQ-003"),
        DQ("DQ-006", "subscription_month", "product_code", "referential", {"to_entity": "product", "to_attribute": "product_code"}, req="REQ-003"),
        DQ("DQ-007", "subscription_month", None, "row_count_min", {"min": 1}, severity="critical", req="REQ-001"),
    ],
    "metrics": [
        {"name": "churn_rate", "label": "Monthly churn rate", "entity": "subscription_month",
         "measure": {"agg": "sum_bool", "attribute": "is_churned"}, "denominator": {"agg": "count_distinct", "attribute": "subscriber_id"},
         "unit": "ratio", "business_rule": "BR-003", "grain": "month", "definition": "Churned subscribers divided by subscribers in the month."},
        {"name": "arpu", "label": "ARPU", "entity": "subscription_month", "measure": {"agg": "sum", "attribute": "monthly_revenue"},
         "denominator": {"agg": "count_distinct", "attribute": "subscriber_id"}, "unit": "currency", "business_rule": "BR-001",
         "grain": "month", "definition": "Average revenue per subscriber in the month."},
    ],
}

FINANCIAL = {
    "id": "fs-deposit-balances",
    "title": "Deposit balances and average daily balance data product",
    "request": ("Treasury and Retail Banking need a governed daily view of deposit balances per account with "
                "customer segment and product, to report total deposits and average daily balance by segment "
                "and branch. Reconcile to the general ledger deposit total."),
    "consumers": [("Treasury analyst", "What are total deposits by product type today?"),
                  ("Retail banking head", "What is average daily balance by segment and branch?"),
                  ("Finance controller", "Do deposits reconcile to the general ledger?")],
    "sources": [
        {"system": "core-banking", "table": "cbs.customer", "owner": "Customer Data Office", "refresh": "daily batch",
         "description": "Customers", "columns": [C("customer_id", "string(20)", pk=True), C("full_name", "string(200)", "restricted"),
                                                 C("national_id", "string(20)", "restricted"), C("date_of_birth", "date", "restricted"),
                                                 C("segment", "string(20)"), C("kyc_status", "string(10)"), C("onboard_date", "date")]},
        {"system": "core-banking", "table": "cbs.account", "owner": "Deposits Operations", "refresh": "daily batch",
         "description": "Deposit accounts", "columns": [C("account_id", "string(20)", pk=True), C("customer_id", "string(20)"),
                                                        C("product_code", "string(10)"), C("branch_code", "string(8)"),
                                                        C("open_date", "date"), C("status", "string(10)"), C("currency", "string(3)")]},
        {"system": "core-banking", "table": "cbs.product", "owner": "Product Control", "refresh": "weekly",
         "description": "Deposit products", "columns": [C("product_code", "string(10)", pk=True), C("product_name", "string(100)"),
                                                        C("product_type", "string(20)"), C("interest_rate", "decimal(7,4)", "confidential")]},
        {"system": "core-banking", "table": "cbs.daily_balance", "owner": "Deposits Operations", "refresh": "daily batch",
         "description": "End-of-day balances", "columns": [C("account_id", "string(20)", pk=True), C("balance_date", "date", pk=True),
                                                           C("ledger_balance", "decimal(18,2)", "confidential"),
                                                           C("available_balance", "decimal(18,2)", "confidential")]},
    ],
    "entities": [
        {"name": "customer", "kind": "dimension", "history": "type2", "subject_area": "party",
         "grain": "one row per customer version", "description": "Bank customer",
         "attributes": [
             A("customer_id", "string(20)", "cbs.customer.customer_id", pk=True, desc="Business key", req=["REQ-002"]),
             A("segment", "string(20)", "cbs.customer.segment", desc="Mass, affluent or private", req=["REQ-002"]),
             A("kyc_status", "string(10)", "cbs.customer.kyc_status", desc="VERIFIED, PENDING or EXPIRED"),
             A("full_name", "string(200)", "cbs.customer.full_name", cls="restricted", desc="Customer name (masked)", req=["REQ-005"]),
         ]},
        {"name": "product", "kind": "dimension", "history": "type1", "subject_area": "product",
         "grain": "one row per product", "description": "Deposit product",
         "attributes": [
             A("product_code", "string(10)", "cbs.product.product_code", pk=True, desc="Business key"),
             A("product_name", "string(100)", "cbs.product.product_name", desc="Product name"),
             A("product_type", "string(20)", "cbs.product.product_type", desc="Current, savings or term", req=["REQ-001"]),
         ]},
        {"name": "account", "kind": "dimension", "history": "type2", "subject_area": "account",
         "grain": "one row per account version", "description": "Deposit account",
         "attributes": [
             A("account_id", "string(20)", "cbs.account.account_id", pk=True, desc="Business key", req=["REQ-001"]),
             A("customer_id", "string(20)", "cbs.account.customer_id", fk=("customer", "customer_id"), desc="Account holder"),
             A("product_code", "string(10)", "cbs.account.product_code", fk=("product", "product_code"), desc="Product", req=["REQ-001"]),
             A("branch_code", "string(8)", "cbs.account.branch_code", desc="Servicing branch", req=["REQ-002"]),
             A("status", "string(10)", "cbs.account.status", desc="OPEN, DORMANT or CLOSED"),
             A("currency", "string(3)", "cbs.account.currency", desc="ISO currency"),
         ]},
        {"name": "daily_balance", "kind": "fact", "history": "none", "subject_area": "deposits",
         "grain": "one row per account per business day", "description": "End-of-day deposit balance",
         "attributes": [
             A("daily_balance_id", "string(32)", "derived", tr="account_id || '-' || balance_date", pk=True, desc="Business key"),
             A("account_id", "string(20)", "cbs.daily_balance.account_id", fk=("account", "account_id"), desc="Account", req=["REQ-001"]),
             A("balance_date", "date", "cbs.daily_balance.balance_date", desc="Business date", req=["REQ-001"]),
             A("ledger_balance", "decimal(18,2)", "cbs.daily_balance.ledger_balance", cls="confidential", desc="Ledger balance", req=["REQ-001"], br="BR-001"),
             A("available_balance", "decimal(18,2)", "cbs.daily_balance.available_balance", cls="confidential", desc="Available balance"),
         ]},
    ],
    "requirements": [
        ("REQ-001", "Provide one row per deposit account per business day with ledger balance and product type.", "an open account on a business day", "the day is loaded", "one row exists with the ledger balance"),
        ("REQ-002", "Report average daily balance by customer segment and branch.", "balances for a month", "ADB is calculated", "it equals the mean of daily ledger balances"),
        ("REQ-003", "Total deposits reconcile to the general ledger within 0.01 percent.", "the business day closes", "reconciliation runs", "the difference is within tolerance"),
        ("REQ-004", "Closed accounts stop contributing balances after their close date.", "an account closed on the 10th", "the 11th is loaded", "no row exists for that account"),
        ("REQ-005", "Customer personal data is masked for all analytical consumers.", "an analyst queries customers", "they view the name", "the value is masked"),
    ],
    "business_rules": [
        ("BR-001", "Ledger balance is the end-of-day posted balance in account currency.", "Posted credits 100 and debits 40 on an opening 0 give 60."),
        ("BR-002", "Average daily balance is the mean of daily ledger balances over calendar days in the period.", "Balances 100, 200, 300 give ADB 200."),
        ("BR-003", "Dormant accounts are included; closed accounts are excluded after close date.", "Dormant account with 50 counts."),
    ],
    "nfrs": [("NFR-001", "Daily balances available by 07:00 for the prior business day.", "freshness <= 7h"),
             ("NFR-002", "Results reproducible point-in-time for regulatory reporting.", "re-run gives identical totals")],
    "dq": [
        DQ("DQ-001", "daily_balance", "daily_balance_id", "unique", req="REQ-001"),
        DQ("DQ-002", "daily_balance", "ledger_balance", "not_null", req="REQ-001"),
        DQ("DQ-003", "daily_balance", "account_id", "referential", {"to_entity": "account", "to_attribute": "account_id"}, req="REQ-001"),
        DQ("DQ-004", "account", "currency", "accepted_values", {"values": ["USD", "EUR", "GBP"]}, severity="medium", req="REQ-001"),
        DQ("DQ-005", "account", "status", "accepted_values", {"values": ["OPEN", "DORMANT", "CLOSED"]}, severity="medium", req="REQ-004"),
        DQ("DQ-006", "daily_balance", "ledger_balance", "range", {"min": -1000000, "max": 100000000}, threshold=0.999, req="REQ-001"),
        DQ("DQ-007", "daily_balance", None, "row_count_min", {"min": 1}, severity="critical", req="REQ-001"),
    ],
    "metrics": [
        {"name": "total_deposits", "label": "Total deposits", "entity": "daily_balance", "measure": {"agg": "sum", "attribute": "ledger_balance"},
         "denominator": None, "unit": "currency", "business_rule": "BR-001", "grain": "day", "definition": "Sum of ledger balances."},
        {"name": "average_daily_balance", "label": "Average daily balance", "entity": "daily_balance",
         "measure": {"agg": "avg", "attribute": "ledger_balance"}, "denominator": None, "unit": "currency",
         "business_rule": "BR-002", "grain": "month", "definition": "Mean of daily ledger balances."},
    ],
}

RETAIL = {
    "id": "retail-sales",
    "title": "Sales performance data product",
    "request": ("Merchandising and Store Operations need a trusted sales view by store, product and loyalty tier "
                "to track net sales and average order value daily, replacing three conflicting spreadsheets. "
                "Start with store sales (no e-commerce)."),
    "consumers": [("Merchandising manager", "What are net sales by category and brand?"),
                  ("Store operations director", "What is average order value by store and region?"),
                  ("Loyalty team", "How do sales differ by loyalty tier?")],
    "sources": [
        {"system": "point-of-sale", "table": "pos.store", "owner": "Store Operations", "refresh": "daily batch",
         "description": "Stores", "columns": [C("store_id", "string(10)", pk=True), C("store_name", "string(100)"),
                                              C("region", "string(20)"), C("format", "string(12)")]},
        {"system": "product-information", "table": "pim.product", "owner": "Merchandising", "refresh": "daily batch",
         "description": "Products", "columns": [C("product_id", "string(14)", pk=True), C("product_name", "string(200)"),
                                                C("category", "string(40)"), C("brand", "string(40)"),
                                                C("list_price", "decimal(10,2)"), C("unit_cost", "decimal(10,2)", "confidential")]},
        {"system": "crm", "table": "crm.customer", "owner": "Loyalty", "refresh": "daily batch",
         "description": "Loyalty customers", "columns": [C("customer_id", "string(20)", pk=True), C("email", "string(200)", "restricted"),
                                                          C("loyalty_tier", "string(10)"), C("consent_marketing", "boolean")]},
        {"system": "point-of-sale", "table": "pos.order_line", "owner": "Store Operations", "refresh": "daily batch",
         "description": "Sales lines", "columns": [C("order_line_id", "string(24)", pk=True), C("order_id", "string(20)"),
                                                   C("store_id", "string(10)"), C("product_id", "string(14)"),
                                                   C("customer_id", "string(20)"), C("order_ts", "timestamp"),
                                                   C("quantity", "integer"), C("gross_amount", "decimal(12,2)"),
                                                   C("discount_amount", "decimal(12,2)"), C("return_flag", "string(1)")]},
    ],
    "entities": [
        {"name": "store", "kind": "dimension", "history": "type1", "subject_area": "store", "grain": "one row per store",
         "description": "Physical store", "attributes": [
             A("store_id", "string(10)", "pos.store.store_id", pk=True, desc="Business key"),
             A("store_name", "string(100)", "pos.store.store_name", desc="Store name"),
             A("region", "string(20)", "pos.store.region", desc="Sales region", req=["REQ-002"]),
             A("format", "string(12)", "pos.store.format", desc="FLAGSHIP, STANDARD or EXPRESS")]},
        {"name": "product", "kind": "dimension", "history": "type2", "subject_area": "product", "grain": "one row per product version",
         "description": "Sellable product", "attributes": [
             A("product_id", "string(14)", "pim.product.product_id", pk=True, desc="Business key"),
             A("product_name", "string(200)", "pim.product.product_name", desc="Product name"),
             A("category", "string(40)", "pim.product.category", desc="Category", req=["REQ-001"]),
             A("brand", "string(40)", "pim.product.brand", desc="Brand", req=["REQ-001"])]},
        {"name": "customer", "kind": "dimension", "history": "type1", "subject_area": "customer", "grain": "one row per loyalty customer",
         "description": "Loyalty customer", "attributes": [
             A("customer_id", "string(20)", "crm.customer.customer_id", pk=True, desc="Business key"),
             A("loyalty_tier", "string(10)", "crm.customer.loyalty_tier", desc="NONE, BRONZE, SILVER or GOLD", req=["REQ-003"]),
             A("email", "string(200)", "crm.customer.email", cls="restricted", desc="Email (masked)", req=["REQ-005"])]},
        {"name": "sales_line", "kind": "fact", "history": "none", "subject_area": "order", "grain": "one row per order line",
         "description": "Store sales line", "attributes": [
             A("order_line_id", "string(24)", "pos.order_line.order_line_id", pk=True, desc="Business key", req=["REQ-001"]),
             A("order_id", "string(20)", "pos.order_line.order_id", desc="Order (basket)", req=["REQ-002"]),
             A("store_id", "string(10)", "pos.order_line.store_id", fk=("store", "store_id"), desc="Store", req=["REQ-002"]),
             A("product_id", "string(14)", "pos.order_line.product_id", fk=("product", "product_id"), desc="Product", req=["REQ-001"]),
             A("customer_id", "string(20)", "pos.order_line.customer_id", fk=("customer", "customer_id"), desc="Loyalty customer (NONE if anonymous)", req=["REQ-003"]),
             A("order_date", "date", "pos.order_line.order_ts", tr="CAST to date in store local time", desc="Sales date", req=["REQ-001"]),
             A("quantity", "integer", "pos.order_line.quantity", desc="Units", req=["REQ-001"]),
             A("net_amount", "decimal(12,2)", "pos.order_line.gross_amount", tr="gross_amount - discount_amount; negated for returns", desc="Net sales amount", req=["REQ-001"], br="BR-001"),
             A("discount_amount", "decimal(12,2)", "pos.order_line.discount_amount", desc="Discount")]},
    ],
    "requirements": [
        ("REQ-001", "Provide one row per sales line with product, date, units and net sales.", "a sales line exists", "the day is loaded", "one row exists with matching net sales"),
        ("REQ-002", "Report average order value by store and region.", "orders across stores", "AOV is calculated", "it equals net sales divided by distinct orders"),
        ("REQ-003", "Analyse sales by loyalty tier; anonymous sales use tier NONE.", "an anonymous sale", "it is loaded", "it appears under NONE"),
        ("REQ-004", "Net sales reconcile to the finance daily sales journal within 0.1 percent.", "the day closes", "reconciliation runs", "the difference is within tolerance"),
        ("REQ-005", "Customer contact data is masked for all analytical consumers.", "an analyst queries customers", "they view email", "the value is masked"),
    ],
    "business_rules": [
        ("BR-001", "Net amount is gross amount minus discount; returns are negative.", "Gross 50, discount 5 gives 45; a return of that line gives -45."),
        ("BR-002", "Average order value is net sales divided by distinct orders.", "Net 300 over 4 orders gives 75."),
        ("BR-003", "Anonymous sales are attributed to customer NONE with tier NONE.", "Cash sale without card goes to NONE."),
    ],
    "nfrs": [("NFR-001", "Daily sales available by 05:00.", "freshness <= 5h"),
             ("NFR-002", "Load handles 5 million lines per day.", "runtime <= 30 min")],
    "dq": [
        DQ("DQ-001", "sales_line", "order_line_id", "unique", req="REQ-001"),
        DQ("DQ-002", "sales_line", "net_amount", "not_null", req="REQ-001"),
        DQ("DQ-003", "sales_line", "store_id", "referential", {"to_entity": "store", "to_attribute": "store_id"}, req="REQ-002"),
        DQ("DQ-004", "sales_line", "product_id", "referential", {"to_entity": "product", "to_attribute": "product_id"}, req="REQ-001"),
        DQ("DQ-005", "customer", "loyalty_tier", "accepted_values", {"values": ["NONE", "BRONZE", "SILVER", "GOLD"]}, severity="medium", req="REQ-003"),
        DQ("DQ-006", "sales_line", "quantity", "range", {"min": -100, "max": 1000}, threshold=0.999, req="REQ-001"),
        DQ("DQ-007", "sales_line", None, "row_count_min", {"min": 1}, severity="critical", req="REQ-001"),
    ],
    "metrics": [
        {"name": "net_sales", "label": "Net sales", "entity": "sales_line", "measure": {"agg": "sum", "attribute": "net_amount"},
         "denominator": None, "unit": "currency", "business_rule": "BR-001", "grain": "day", "definition": "Gross sales less discounts and returns."},
        {"name": "average_order_value", "label": "Average order value", "entity": "sales_line", "measure": {"agg": "sum", "attribute": "net_amount"},
         "denominator": {"agg": "count_distinct", "attribute": "order_id"}, "unit": "currency", "business_rule": "BR-002",
         "grain": "day", "definition": "Net sales divided by distinct orders."},
    ],
}

SCENARIOS = {"utilities": UTILITIES, "telco": TELCO, "financial-services": FINANCIAL, "retail": RETAIL}


def for_domain(pack_id: str) -> dict:
    return SCENARIOS.get(pack_id, UTILITIES)


# SQL expressions for non-direct mappings. `src` is the entity's primary staging relation;
# {{stg:system_table}} is rendered per transformation tool. "derived" sources reference
# other target attributes and are computed in an outer select.
EXPRESSIONS = {
    ("utilities", "billed_consumption", "metered_kwh"):
        "(SELECT SUM(r.kwh) FROM {{stg:mdm.daily_read}} r JOIN {{stg:mdm.meter}} m ON r.meter_id = m.meter_id "
        "JOIN {{stg:cis.premise}} p ON m.premise_id = p.premise_id WHERE p.account_id = src.account_id "
        "AND r.read_date BETWEEN src.period_start AND src.period_end)",
    ("utilities", "billed_consumption", "estimated_read_share"):
        "(SELECT CAST(SUM(CASE WHEN r.read_quality = 'E' THEN 1 ELSE 0 END) AS DECIMAL(18,4)) / NULLIF(COUNT(*), 0) "
        "FROM {{stg:mdm.daily_read}} r JOIN {{stg:mdm.meter}} m ON r.meter_id = m.meter_id JOIN {{stg:cis.premise}} p "
        "ON m.premise_id = p.premise_id WHERE p.account_id = src.account_id AND r.read_date BETWEEN src.period_start AND src.period_end)",
    ("utilities", "billed_consumption", "variance_kwh"): "billed_kwh - metered_kwh",
    ("telco", "subscription_month", "subscription_month_id"): "subscriber_id || '-' || CAST(month_start AS CHAR(10))",
    ("telco", "subscription_month", "month_start"): "DATE_TRUNC('month', src.start_date)",
    ("telco", "subscription_month", "data_mb"):
        "(SELECT SUM(u.data_mb) FROM {{stg:usage.daily_usage_summary}} u WHERE u.subscriber_id = src.subscriber_id "
        "AND DATE_TRUNC('month', u.usage_date) = DATE_TRUNC('month', src.start_date))",
    ("telco", "subscription_month", "voice_min"):
        "(SELECT SUM(u.voice_min) FROM {{stg:usage.daily_usage_summary}} u WHERE u.subscriber_id = src.subscriber_id "
        "AND DATE_TRUNC('month', u.usage_date) = DATE_TRUNC('month', src.start_date))",
    ("telco", "subscription_month", "is_churned"):
        "EXISTS (SELECT 1 FROM {{stg:crm.churn_event}} c WHERE c.subscriber_id = src.subscriber_id "
        "AND DATE_TRUNC('month', c.churn_date) = DATE_TRUNC('month', src.start_date))",
    ("financial-services", "daily_balance", "daily_balance_id"): "account_id || '-' || CAST(balance_date AS CHAR(10))",
    ("retail", "sales_line", "order_date"): "CAST(src.order_ts AS DATE)",
    ("retail", "sales_line", "net_amount"):
        "CASE WHEN src.return_flag = 'Y' THEN -(src.gross_amount - src.discount_amount) ELSE src.gross_amount - src.discount_amount END",
    ("retail", "sales_line", "customer_id"): "COALESCE(src.customer_id, 'NONE')",
}
ENTITY_FILTERS = {("utilities", "billed_consumption"): "src.bill_status = 'FINAL'",
                  ("financial-services", "daily_balance"): "src.ledger_balance IS NOT NULL"}
