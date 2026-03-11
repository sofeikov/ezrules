from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import UserList, UserListEntry

type DemoScalar = str | int | float
type DemoEventData = dict[str, DemoScalar]


SAFE_COUNTRIES = ["US", "GB", "CA", "DE", "FR", "NL", "AU", "SG", "SE", "ES"]
BROADER_CUSTOMER_COUNTRIES = SAFE_COUNTRIES + ["BR", "MX", "IT", "IE"]
LATAM_COUNTRIES = ["BR", "MX", "AR", "CO", "CL", "PE", "PA"]
MIDDLE_ASIA_COUNTRIES = ["KZ", "UZ", "KG", "TJ", "TM"]
SANCTIONED_COUNTRIES = ["IR", "KP", "SY", "CU"]
COMMON_EMAIL_DOMAINS = [
    "gmail.com",
    "outlook.com",
    "hotmail.com",
    "yahoo.com",
    "icloud.com",
    "fastmail.com",
    "proton.me",
]
DISPOSABLE_EMAIL_DOMAINS = [
    "mailinator.com",
    "guerrillamail.com",
    "tempmail.dev",
    "sharklasers.com",
    "yopmail.com",
]
STANDARD_MERCHANT_CATEGORIES = [
    "groceries",
    "fashion",
    "electronics",
    "travel",
    "home_goods",
    "health",
    "fuel",
    "luxury",
]
ELEVATED_RISK_MERCHANT_CATEGORIES = ["digital_goods", "gift_cards", "crypto", "money_transfer"]
WATCHLIST_MERCHANT_IDS = ["mrc_cardhub", "mrc_quickcash", "mrc_streambox"]
TRUSTED_BILLING_COUNTRIES = ["US", "GB", "CA", "DE", "FR", "NL", "AU"]

USER_LISTS = {
    "SanctionedCountries": SANCTIONED_COUNTRIES,
    "DisposableEmailDomains": DISPOSABLE_EMAIL_DOMAINS,
    "ElevatedRiskMerchantCategories": ELEVATED_RISK_MERCHANT_CATEGORIES,
    "WatchlistMerchants": WATCHLIST_MERCHANT_IDS,
    "TrustedBillingCountries": TRUSTED_BILLING_COUNTRIES,
}

COUNTRY_CURRENCY = {
    "US": "USD",
    "GB": "GBP",
    "CA": "CAD",
    "DE": "EUR",
    "FR": "EUR",
    "NL": "EUR",
    "AU": "AUD",
    "SG": "SGD",
    "SE": "SEK",
    "ES": "EUR",
    "BR": "BRL",
    "MX": "MXN",
    "IT": "EUR",
    "IE": "EUR",
    "AE": "AED",
    "IR": "IRR",
    "KP": "KPW",
    "SY": "SYP",
    "CU": "CUP",
    "KZ": "KZT",
    "UZ": "UZS",
    "KG": "KGS",
    "TJ": "TJS",
    "TM": "TMT",
    "AR": "ARS",
    "CO": "COP",
    "CL": "CLP",
    "PE": "PEN",
    "PA": "USD",
}

CARD_PURCHASE_TYPES = ["card_purchase"]
PAYOUT_TYPES = ["wallet_cashout", "instant_payout", "bank_transfer"]


@dataclass(frozen=True, slots=True)
class CustomerProfile:
    customer_id: str
    customer_country: str
    email_domain: str
    account_age_days: int
    email_age_days: int
    prior_chargebacks_180d: int
    manual_review_hits_30d: int
    typical_amount: int


@dataclass(frozen=True, slots=True)
class MerchantProfile:
    merchant_id: str
    merchant_category: str
    merchant_country: str
    base_ticket: int


@dataclass(frozen=True, slots=True)
class DemoRuleDefinition:
    rid: str
    logic: str
    description: str


@dataclass(frozen=True, slots=True)
class GeneratedDemoEvent:
    event_id: str
    event_timestamp: int
    event_data: DemoEventData


_MERCHANTS = [
    MerchantProfile("mrc_dailycart", "groceries", "US", 55),
    MerchantProfile("mrc_gadgethub", "electronics", "US", 240),
    MerchantProfile("mrc_stylelane", "fashion", "GB", 130),
    MerchantProfile("mrc_skyways", "travel", "NL", 460),
    MerchantProfile("mrc_homeware", "home_goods", "DE", 165),
    MerchantProfile("mrc_pharmaline", "health", "CA", 75),
    MerchantProfile("mrc_fuelline", "fuel", "US", 95),
    MerchantProfile("mrc_luxevault", "luxury", "FR", 900),
    MerchantProfile("mrc_streambox", "digital_goods", "GB", 85),
    MerchantProfile("mrc_cardhub", "gift_cards", "US", 185),
    MerchantProfile("mrc_quickcash", "money_transfer", "AE", 650),
    MerchantProfile("mrc_coinlane", "crypto", "SG", 1100),
]


def seed_demo_user_lists(list_manager: PersistentUserListManager) -> None:
    list_manager._ensure_initialized()
    db_session = list_manager.db_session
    existing_lists = {
        user_list.list_name: {
            entry.entry_value
            for entry in db_session.query(UserListEntry).filter(UserListEntry.ul_id == user_list.ul_id).all()
        }
        for user_list in db_session.query(UserList).filter_by(o_id=list_manager.o_id).all()
    }
    changed = False
    for list_name, entries in USER_LISTS.items():
        current_entries = existing_lists.get(list_name, set())
        user_list = db_session.query(UserList).filter_by(list_name=list_name, o_id=list_manager.o_id).first()
        if user_list is None:
            user_list = UserList(list_name=list_name, o_id=list_manager.o_id)
            db_session.add(user_list)
            db_session.flush()
            existing_lists[list_name] = set()
            current_entries = existing_lists[list_name]
            changed = True
        for entry in entries:
            if entry not in current_entries:
                db_session.add(UserListEntry(entry_value=entry, ul_id=user_list.ul_id))
                current_entries.add(entry)
                changed = True
    if changed:
        db_session.commit()
        list_manager._cached_lists = None


def build_demo_rules(n_rules: int, start_index: int = 0) -> list[DemoRuleDefinition]:
    rules: list[DemoRuleDefinition] = []
    for offset in range(n_rules):
        absolute_index = start_index + offset + 1
        variant = offset // len(_RULE_BUILDERS)
        rule_logic, rule_description, rule_suffix = _RULE_BUILDERS[offset % len(_RULE_BUILDERS)](variant)
        rules.append(
            DemoRuleDefinition(
                rid=f"TestRule_{rule_suffix}_{absolute_index:03d}",
                logic=rule_logic,
                description=rule_description,
            )
        )
    return rules


def build_demo_events(n_events: int, start_index: int = 0) -> list[GeneratedDemoEvent]:
    rng = random.Random()
    customers = _build_customer_profiles(max(40, n_events // 5 or 1), rng)
    events: list[GeneratedDemoEvent] = []

    for offset in range(n_events):
        event_id = f"TestEvent_TXN_{start_index + offset + 1:06d}"
        event_timestamp = _random_recent_timestamp(rng)
        event_data = _generate_event_payload(rng, customers)
        events.append(
            GeneratedDemoEvent(
                event_id=event_id,
                event_timestamp=event_timestamp,
                event_data=event_data,
            )
        )

    return events


def determine_demo_label(event_data: DemoEventData, available_labels: list[str]) -> str | None:
    if not available_labels:
        return None

    fraud_score = _fraud_score(event_data)
    chargeback_score = _chargeback_score(event_data)

    if "FRAUD" in available_labels and fraud_score >= 6.2:
        return "FRAUD"
    if "CHARGEBACK" in available_labels and chargeback_score >= 3.6 and fraud_score < 6.5:
        return "CHARGEBACK"

    labels: list[str] = []
    weights: list[float] = []

    if "FRAUD" in available_labels:
        labels.append("FRAUD")
        weights.append(max(0.5, fraud_score * 1.7))

    if "CHARGEBACK" in available_labels:
        labels.append("CHARGEBACK")
        weights.append(max(0.5, chargeback_score * 1.8))

    if "NORMAL" in available_labels:
        labels.append("NORMAL")
        weights.append(max(1.0, 10.5 - fraud_score - (chargeback_score * 1.2)))

    if labels:
        return random.choices(labels, weights=weights, k=1)[0]

    return available_labels[0]


def _build_customer_profiles(count: int, rng: random.Random) -> list[CustomerProfile]:
    countries = BROADER_CUSTOMER_COUNTRIES
    country_weights = [24, 14, 9, 8, 7, 6, 5, 4, 4, 4, 3, 3, 2, 2]
    customers: list[CustomerProfile] = []

    for index in range(count):
        segment = _weighted_pick(rng, ["established", "growing", "new"], [60, 28, 12])
        customer_country = _weighted_pick(rng, countries, country_weights)

        if segment == "established":
            account_age_days = rng.randint(240, 2200)
            email_age_days = rng.randint(180, account_age_days + 120)
            prior_chargebacks_180d = 0 if rng.random() < 0.92 else 1
            manual_review_hits_30d = 0 if rng.random() < 0.86 else rng.randint(1, 2)
            typical_amount = rng.randint(45, 480)
        elif segment == "growing":
            account_age_days = rng.randint(45, 540)
            email_age_days = rng.randint(30, account_age_days + 45)
            prior_chargebacks_180d = 0 if rng.random() < 0.8 else rng.randint(1, 2)
            manual_review_hits_30d = rng.randint(0, 2)
            typical_amount = rng.randint(35, 360)
        else:
            account_age_days = rng.randint(2, 45)
            email_age_days = rng.randint(1, account_age_days + 7)
            prior_chargebacks_180d = 0 if rng.random() < 0.7 else 1
            manual_review_hits_30d = rng.randint(0, 3)
            typical_amount = rng.randint(20, 220)

        customers.append(
            CustomerProfile(
                customer_id=f"cust_{index + 1:05d}",
                customer_country=customer_country,
                email_domain=_pick(rng, COMMON_EMAIL_DOMAINS),
                account_age_days=account_age_days,
                email_age_days=email_age_days,
                prior_chargebacks_180d=prior_chargebacks_180d,
                manual_review_hits_30d=manual_review_hits_30d,
                typical_amount=typical_amount,
            )
        )

    return customers


def _generate_event_payload(rng: random.Random, customers: list[CustomerProfile]) -> DemoEventData:
    scenario = _weighted_pick(
        rng,
        [
            "domestic_card_purchase",
            "trusted_big_ticket",
            "cross_border_reship",
            "card_testing_burst",
            "account_takeover",
            "wallet_cashout",
            "friendly_fraud_chargeback",
        ],
        [38, 13, 14, 11, 10, 8, 6],
    )
    customer = _pick(rng, customers)

    if scenario == "domestic_card_purchase":
        merchant = _pick_matching_merchants(rng, STANDARD_MERCHANT_CATEGORIES)
        event_data = _base_event_data(rng, customer, merchant, txn_type="card_purchase")
        event_data["channel"] = _weighted_pick(rng, ["web", "mobile_app", "pos"], [40, 35, 25])
        event_data["local_hour"] = rng.randint(8, 21)
        event_data["card_present"] = 1 if merchant.merchant_category in {"groceries", "fuel", "health"} else 0
        event_data["has_3ds"] = 0 if int(event_data["card_present"]) == 1 else 1
        return event_data

    if scenario == "trusted_big_ticket":
        merchant = _pick_matching_merchants(rng, ["electronics", "travel", "luxury"])
        event_data = _base_event_data(rng, customer, merchant, txn_type="card_purchase")
        event_data["amount"] = round(max(float(event_data["amount"]), rng.uniform(650, 2400)), 2)
        event_data["device_age_days"] = rng.randint(180, 1200)
        event_data["device_trust_score"] = rng.randint(82, 98)
        event_data["has_3ds"] = 1
        event_data["card_present"] = 0
        event_data["local_hour"] = rng.randint(9, 20)
        event_data["distance_from_home_km"] = rng.randint(0, 80)
        return event_data

    if scenario == "cross_border_reship":
        merchant = _pick_matching_merchants(rng, ["electronics", "fashion", "luxury"])
        event_data = _base_event_data(rng, customer, merchant, txn_type="card_purchase")
        if customer.customer_country not in TRUSTED_BILLING_COUNTRIES:
            event_data["billing_country"] = _pick(rng, TRUSTED_BILLING_COUNTRIES)
            event_data["customer_country"] = str(event_data["billing_country"])
        shipping_country = _weighted_pick(rng, LATAM_COUNTRIES + MIDDLE_ASIA_COUNTRIES, [7] * 7 + [4] * 5)
        event_data["shipping_country"] = shipping_country
        event_data["ip_country"] = _pick(rng, [shipping_country, "AE", "SG", "TR"])
        event_data["amount"] = round(rng.uniform(520, 1850), 2)
        event_data["account_age_days"] = rng.randint(1, 35)
        event_data["email_age_days"] = rng.randint(1, 20)
        event_data["device_age_days"] = rng.randint(0, 2)
        event_data["device_trust_score"] = rng.randint(12, 42)
        event_data["is_guest_checkout"] = 1
        event_data["has_3ds"] = 0
        event_data["card_present"] = 0
        event_data["txn_velocity_10m"] = rng.randint(2, 5)
        event_data["txn_velocity_1h"] = rng.randint(2, 6)
        event_data["unique_cards_24h"] = rng.randint(1, 3)
        event_data["distance_from_home_km"] = rng.randint(1400, 9200)
        event_data["local_hour"] = _pick(rng, [0, 1, 2, 3, 4, 22, 23])
        return event_data

    if scenario == "card_testing_burst":
        merchant = _pick_matching_merchants(rng, ["digital_goods", "gift_cards"])
        event_data = _base_event_data(rng, customer, merchant, txn_type="card_purchase")
        event_data["email_domain"] = _pick(rng, DISPOSABLE_EMAIL_DOMAINS)
        event_data["amount"] = round(rng.uniform(1.0, 24.0), 2)
        event_data["account_age_days"] = rng.randint(0, 12)
        event_data["email_age_days"] = rng.randint(0, 5)
        event_data["device_age_days"] = 0
        event_data["device_trust_score"] = rng.randint(1, 22)
        event_data["is_guest_checkout"] = 1
        event_data["has_3ds"] = 0
        event_data["card_present"] = 0
        event_data["decline_count_24h"] = rng.randint(6, 18)
        event_data["txn_velocity_10m"] = rng.randint(9, 28)
        event_data["txn_velocity_1h"] = rng.randint(16, 60)
        event_data["unique_cards_24h"] = rng.randint(4, 12)
        event_data["ip_proxy_score"] = rng.randint(72, 99)
        event_data["distance_from_home_km"] = rng.randint(900, 9800)
        event_data["local_hour"] = rng.randint(0, 4)
        return event_data

    if scenario == "account_takeover":
        merchant = _pick_matching_merchants(rng, ["electronics", "travel", "luxury"])
        event_data = _base_event_data(rng, customer, merchant, txn_type="card_purchase")
        event_data["amount"] = round(max(rng.uniform(650, 2600), float(event_data["amount"]) * 2.2), 2)
        event_data["account_age_days"] = max(customer.account_age_days, rng.randint(220, 1800))
        event_data["email_age_days"] = max(customer.email_age_days, rng.randint(180, 1800))
        event_data["password_reset_age_hours"] = rng.randint(0, 6)
        event_data["device_age_days"] = rng.randint(0, 1)
        event_data["device_trust_score"] = rng.randint(9, 35)
        event_data["has_3ds"] = 0
        event_data["card_present"] = 0
        event_data["decline_count_24h"] = rng.randint(2, 5)
        event_data["txn_velocity_1h"] = rng.randint(2, 6)
        event_data["ip_country"] = _pick(
            rng, [country for country in BROADER_CUSTOMER_COUNTRIES if country != customer.customer_country]
        )
        event_data["distance_from_home_km"] = rng.randint(1800, 9800)
        event_data["local_hour"] = _pick(rng, [0, 1, 2, 3, 4, 5, 22, 23])
        return event_data

    if scenario == "wallet_cashout":
        merchant = _pick_matching_merchants(rng, ["money_transfer", "crypto"])
        event_data = _base_event_data(rng, customer, merchant, txn_type=_pick(rng, PAYOUT_TYPES))
        event_data["amount"] = round(rng.uniform(680, 4200), 2)
        event_data["account_age_days"] = rng.randint(5, 160)
        event_data["email_age_days"] = rng.randint(3, 200)
        event_data["device_age_days"] = rng.randint(0, 10)
        event_data["device_trust_score"] = rng.randint(14, 58)
        event_data["has_3ds"] = 0
        event_data["card_present"] = 0
        event_data["txn_velocity_10m"] = rng.randint(2, 6)
        event_data["txn_velocity_1h"] = rng.randint(4, 14)
        event_data["manual_review_hits_30d"] = max(customer.manual_review_hits_30d, rng.randint(1, 4))
        event_data["beneficiary_country"] = _weighted_pick(
            rng,
            SANCTIONED_COUNTRIES + ["AE", "SG", "TR", "BR", "MX"],
            [7, 6, 6, 5, 4, 3, 3, 2, 2],
        )
        event_data["beneficiary_age_days"] = rng.randint(0, 3)
        event_data["ip_proxy_score"] = rng.randint(35, 95)
        event_data["distance_from_home_km"] = rng.randint(500, 9500)
        event_data["local_hour"] = _pick(rng, [0, 1, 2, 3, 4, 5, 20, 21, 22, 23])
        return event_data

    merchant = _pick_matching_merchants(rng, ["travel", "digital_goods", "fashion", "electronics"])
    event_data = _base_event_data(rng, customer, merchant, txn_type="card_purchase")
    event_data["amount"] = round(rng.uniform(120, 1600), 2)
    event_data["account_age_days"] = rng.randint(35, 420)
    event_data["email_age_days"] = rng.randint(25, 520)
    event_data["prior_chargebacks_180d"] = rng.randint(1, 3)
    event_data["device_age_days"] = rng.randint(10, 220)
    event_data["device_trust_score"] = rng.randint(38, 82)
    event_data["has_3ds"] = 1 if rng.random() < 0.45 else 0
    event_data["card_present"] = 0
    event_data["is_guest_checkout"] = 1 if rng.random() < 0.3 else 0
    event_data["shipping_country"] = (
        _pick(rng, [str(event_data["billing_country"]), "US", "GB", "DE"])
        if rng.random() < 0.7
        else _pick(rng, LATAM_COUNTRIES)
    )
    event_data["ip_country"] = str(event_data["billing_country"])
    event_data["local_hour"] = rng.randint(9, 22)
    return event_data


def _base_event_data(
    rng: random.Random,
    customer: CustomerProfile,
    merchant: MerchantProfile,
    txn_type: str,
) -> DemoEventData:
    baseline_ticket = (merchant.base_ticket * 0.65) + (customer.typical_amount * 0.35)
    amount = round(max(8.0, rng.gauss(baseline_ticket, max(baseline_ticket * 0.35, 18.0))), 2)
    local_hour = rng.randint(8, 21)
    return {
        "amount": amount,
        "currency": COUNTRY_CURRENCY.get(merchant.merchant_country, "USD"),
        "txn_type": txn_type,
        "channel": _weighted_pick(rng, ["web", "mobile_app", "merchant_api"], [48, 38, 14]),
        "customer_id": customer.customer_id,
        "customer_country": customer.customer_country,
        "billing_country": customer.customer_country,
        "shipping_country": customer.customer_country,
        "ip_country": customer.customer_country,
        "merchant_id": merchant.merchant_id,
        "merchant_category": merchant.merchant_category,
        "merchant_country": merchant.merchant_country,
        "email_domain": customer.email_domain,
        "account_age_days": customer.account_age_days,
        "email_age_days": customer.email_age_days,
        "customer_avg_amount_30d": round(customer.typical_amount * rng.uniform(0.85, 1.15), 2),
        "customer_std_amount_30d": round(max(customer.typical_amount * rng.uniform(0.18, 0.45), 12.0), 2),
        "prior_chargebacks_180d": customer.prior_chargebacks_180d,
        "manual_review_hits_30d": customer.manual_review_hits_30d,
        "decline_count_24h": rng.randint(0, 1),
        "txn_velocity_10m": 1,
        "txn_velocity_1h": rng.randint(1, 2),
        "unique_cards_24h": 1,
        "device_age_days": rng.randint(45, 960),
        "device_trust_score": rng.randint(72, 98),
        "has_3ds": 1,
        "card_present": 0,
        "is_guest_checkout": 0,
        "password_reset_age_hours": rng.randint(72, 720),
        "distance_from_home_km": rng.randint(0, 90),
        "ip_proxy_score": rng.randint(0, 22),
        "beneficiary_country": customer.customer_country,
        "beneficiary_age_days": rng.randint(45, 720),
        "local_hour": local_hour,
    }


def _pick_matching_merchants(rng: random.Random, categories: list[str]) -> MerchantProfile:
    matching = [merchant for merchant in _MERCHANTS if merchant.merchant_category in categories]
    return _pick(rng, matching)


def _fraud_score(event_data: DemoEventData) -> float:
    fraud_score = 0.0
    amount = _float_value(event_data, "amount")
    txn_type = _str_value(event_data, "txn_type")
    billing_country = _str_value(event_data, "billing_country")
    shipping_country = _str_value(event_data, "shipping_country")
    ip_country = _str_value(event_data, "ip_country")
    merchant_category = _str_value(event_data, "merchant_category")
    email_domain = _str_value(event_data, "email_domain")
    beneficiary_country = _str_value(event_data, "beneficiary_country")
    customer_avg_amount = _float_value(event_data, "customer_avg_amount_30d")
    customer_std_amount = _float_value(event_data, "customer_std_amount_30d")

    if txn_type in PAYOUT_TYPES:
        fraud_score += 1.0
    if amount >= 1500:
        fraud_score += 1.1
    elif amount >= 700:
        fraud_score += 0.6
    if _int_value(event_data, "card_present") == 0:
        fraud_score += 0.4
    if _int_value(event_data, "has_3ds") == 0 and txn_type in CARD_PURCHASE_TYPES:
        fraud_score += 0.9
    if _int_value(event_data, "device_age_days") <= 1:
        fraud_score += 1.0
    elif _int_value(event_data, "device_age_days") <= 7:
        fraud_score += 0.4
    if _int_value(event_data, "device_trust_score") < 25:
        fraud_score += 1.5
    elif _int_value(event_data, "device_trust_score") < 45:
        fraud_score += 0.8
    if _int_value(event_data, "decline_count_24h") >= 5:
        fraud_score += 1.2
    elif _int_value(event_data, "decline_count_24h") >= 3:
        fraud_score += 0.6
    if _int_value(event_data, "txn_velocity_10m") >= 8:
        fraud_score += 1.4
    elif _int_value(event_data, "txn_velocity_10m") >= 4:
        fraud_score += 0.7
    if _int_value(event_data, "unique_cards_24h") >= 4:
        fraud_score += 1.3
    elif _int_value(event_data, "unique_cards_24h") >= 2:
        fraud_score += 0.5
    if _int_value(event_data, "password_reset_age_hours") <= 6:
        fraud_score += 1.0
    if _int_value(event_data, "ip_proxy_score") >= 80:
        fraud_score += 1.2
    elif _int_value(event_data, "ip_proxy_score") >= 50:
        fraud_score += 0.5
    if billing_country != shipping_country:
        fraud_score += 0.7
    if billing_country != ip_country:
        fraud_score += 0.8
    if beneficiary_country in SANCTIONED_COUNTRIES:
        fraud_score += 2.8
    if txn_type in PAYOUT_TYPES and _int_value(event_data, "beneficiary_age_days") <= 3:
        fraud_score += 1.1
    if merchant_category in ELEVATED_RISK_MERCHANT_CATEGORIES:
        fraud_score += 0.8
    if email_domain in DISPOSABLE_EMAIL_DOMAINS:
        fraud_score += 1.0
    if _int_value(event_data, "manual_review_hits_30d") >= 2:
        fraud_score += 0.6
    if _int_value(event_data, "local_hour") <= 4:
        fraud_score += 0.4
    if _int_value(event_data, "prior_chargebacks_180d") >= 2:
        fraud_score += 0.8
    if customer_std_amount > 0:
        amount_zscore = (amount - customer_avg_amount) / customer_std_amount
        if amount_zscore >= 4:
            fraud_score += 1.2
        elif amount_zscore >= 3:
            fraud_score += 0.6

    return fraud_score


def _chargeback_score(event_data: DemoEventData) -> float:
    chargeback_score = 0.0
    amount = _float_value(event_data, "amount")
    merchant_category = _str_value(event_data, "merchant_category")

    if merchant_category in {"travel", "digital_goods", "electronics", "fashion", "luxury"}:
        chargeback_score += 1.1
    if amount >= 800:
        chargeback_score += 0.7
    elif amount >= 250:
        chargeback_score += 0.4
    if _int_value(event_data, "card_present") == 0:
        chargeback_score += 0.5
    if _int_value(event_data, "has_3ds") == 0:
        chargeback_score += 0.4
    if _int_value(event_data, "prior_chargebacks_180d") >= 2:
        chargeback_score += 1.4
    elif _int_value(event_data, "prior_chargebacks_180d") >= 1:
        chargeback_score += 0.8
    if _str_value(event_data, "billing_country") != _str_value(event_data, "shipping_country"):
        chargeback_score += 0.3
    if _int_value(event_data, "device_trust_score") < 50:
        chargeback_score += 0.2

    return chargeback_score


def _random_recent_timestamp(rng: random.Random) -> int:
    now = datetime.now(UTC)
    start = now - timedelta(days=45)
    window_seconds = int((now - start).total_seconds())
    return int((start + timedelta(seconds=rng.randint(0, window_seconds))).timestamp())


def _int_value(event_data: DemoEventData, field_name: str) -> int:
    value = event_data.get(field_name, 0)
    return int(value) if isinstance(value, int | float) else 0


def _float_value(event_data: DemoEventData, field_name: str) -> float:
    value = event_data.get(field_name, 0.0)
    return float(value) if isinstance(value, int | float) else 0.0


def _str_value(event_data: DemoEventData, field_name: str) -> str:
    value = event_data.get(field_name, "")
    return value if isinstance(value, str) else str(value)


def _pick[T](rng: random.Random, values: list[T]) -> T:
    return values[rng.randrange(len(values))]


def _weighted_pick[T](rng: random.Random, values: list[T], weights: list[int]) -> T:
    total = sum(weights)
    draw = rng.uniform(0, total)
    running_total = 0.0
    for value, weight in zip(values, weights, strict=True):
        running_total += weight
        if draw <= running_total:
            return value
    return values[-1]


def _rule_cross_border_cnp_mismatch(variant: int) -> tuple[str, str, str]:
    amount = 550 + (variant * 125)
    logic = (
        f"if $card_present == 0 and $amount >= {amount} and $device_age_days <= 2 and $has_3ds == 0 "
        "and ($billing_country != $shipping_country or $billing_country != $ip_country):\n"
        "    return 'HOLD'"
    )
    description = (
        f"Escalate card-not-present spend above {amount} from fresh devices when billing, shipping, "
        "or IP geography do not line up and no 3DS step-up completed."
    )
    return logic, description, "CrossBorderCnpMismatch"


def _rule_disposable_email_velocity(variant: int) -> tuple[str, str, str]:
    velocity = 4 + (variant % 2)
    unique_cards = 3 + (variant % 2)
    logic = (
        "if $merchant_category in @ElevatedRiskMerchantCategories and $email_domain in @DisposableEmailDomains "
        f"and $txn_velocity_10m >= {velocity} and $unique_cards_24h >= {unique_cards}:\n"
        "    return 'CANCEL'"
    )
    description = (
        f"Block elevated-risk merchants when a disposable email is used alongside a {velocity}+ burst "
        f"and {unique_cards}+ distinct cards in one device-day."
    )
    return logic, description, "DisposableEmailVelocity"


def _rule_na_to_latam_reship(variant: int) -> tuple[str, str, str]:
    amount = 420 + (variant * 90)
    max_age = 18 + (variant * 4)
    logic = (
        "if $billing_country in @NACountries and $shipping_country in @LatamCountries "
        f"and $account_age_days <= {max_age} and $is_guest_checkout == 1 and $amount >= {amount}:\n"
        "    return 'HOLD'"
    )
    description = (
        f"Review new-account guest checkouts over {amount} when billing is North America but goods "
        "are reshipped into Latin America."
    )
    return logic, description, "NaToLatamReship"


def _rule_showcase_amount_zscore(variant: int) -> tuple[str, str, str]:
    zscore = 3 + (variant * 0.5)
    logic = (
        "if $customer_std_amount_30d > 0:\n"
        "    amount_zscore = ($amount - $customer_avg_amount_30d) / $customer_std_amount_30d\n"
        f"    if amount_zscore >= {zscore}:\n"
        "        if $card_present == 0 or $billing_country != $shipping_country:\n"
        "            return 'HOLD'"
    )
    description = (
        f"Showcase rule: compute an amount z-score and escalate when spend is {zscore}+ sigma above the "
        "customer baseline plus card-not-present or geo-mismatch context."
    )
    return logic, description, "ShowcaseAmountZscore"


def _rule_ato_password_reset(variant: int) -> tuple[str, str, str]:
    amount = 700 + (variant * 140)
    logic = (
        f"if $password_reset_age_hours <= 6 and $account_age_days >= 180 and $amount >= {amount} "
        "and $device_age_days <= 1 and $ip_country != $customer_country:\n"
        "    return 'HOLD'"
    )
    description = (
        f"Escalate mature accounts spending {amount}+ right after a password reset when the session "
        "lands on a brand-new device from a new country."
    )
    return logic, description, "AtoPasswordReset"


def _rule_showcase_loop_score(variant: int) -> tuple[str, str, str]:
    threshold = 4 + (variant % 2)
    logic = (
        "signals = [\n"
        "    $device_age_days <= 2,\n"
        "    $has_3ds == 0,\n"
        "    $ip_proxy_score >= 70,\n"
        "    $billing_country != $ip_country,\n"
        "    $txn_velocity_10m >= 5,\n"
        "]\n"
        "hits = 0\n"
        "for signal in signals:\n"
        "    if signal:\n"
        "        hits += 1\n"
        f"if hits >= {threshold}:\n"
        "    return 'HOLD'"
    )
    description = (
        f"Showcase rule: count triggered risk signals in a loop and hold when at least {threshold} conditions line up."
    )
    return logic, description, "ShowcaseLoopSignals"


def _rule_showcase_branch_by_txn_type(variant: int) -> tuple[str, str, str]:
    payout_ratio = 2.4 + (variant * 0.3)
    purchase_ratio = 3.8 + (variant * 0.4)
    logic = (
        "baseline_amount = $customer_avg_amount_30d if $customer_avg_amount_30d > 1 else 1\n"
        "amount_ratio = $amount / baseline_amount\n"
        "if $txn_type in ['wallet_cashout', 'instant_payout', 'bank_transfer']:\n"
        f"    if amount_ratio >= {payout_ratio} and $beneficiary_age_days <= 2:\n"
        "        return 'HOLD'\n"
        "elif $merchant_category in ['electronics', 'travel', 'luxury']:\n"
        f"    if amount_ratio >= {purchase_ratio} and $card_present == 0:\n"
        "        return 'HOLD'"
    )
    description = (
        "Showcase rule: branch by transaction type and apply different baseline-multiple thresholds "
        f"for payouts ({payout_ratio}x) versus high-ticket purchases ({purchase_ratio}x)."
    )
    return logic, description, "ShowcaseBranching"


def _rule_sanctioned_cashout(variant: int) -> tuple[str, str, str]:
    max_beneficiary_age = 3 + variant
    logic = (
        "if $txn_type in ['wallet_cashout', 'instant_payout', 'bank_transfer'] and "
        f"$beneficiary_country in @SanctionedCountries and $beneficiary_age_days <= {max_beneficiary_age}:\n"
        "    return 'CANCEL'"
    )
    description = (
        "Block payout or transfer attempts to sanctioned destinations when the beneficiary was added "
        f"in the last {max_beneficiary_age} days."
    )
    return logic, description, "SanctionedCashout"


def _rule_proxy_high_risk_category(variant: int) -> tuple[str, str, str]:
    proxy_score = 70 + (variant * 5)
    amount = 280 + (variant * 60)
    logic = (
        "if $merchant_category in @ElevatedRiskMerchantCategories "
        f"and $ip_proxy_score >= {proxy_score} and $has_3ds == 0 and $amount >= {amount}:\n"
        "    return 'HOLD'"
    )
    description = (
        f"Review elevated-risk merchant traffic above {amount} when the session is masked behind a "
        f"proxy score of {proxy_score}+ and there is no 3DS challenge."
    )
    return logic, description, "ProxyHighRiskCategory"


def _rule_card_testing_on_device(variant: int) -> tuple[str, str, str]:
    declines = 5 + variant
    velocity = 8 + (variant * 2)
    logic = (
        f"if $amount <= 25 and $decline_count_24h >= {declines} and $txn_velocity_10m >= {velocity} "
        "and $unique_cards_24h >= 4:\n"
        "    return 'CANCEL'"
    )
    description = (
        f"Block classic card-testing bursts: micro-payments with {declines}+ declines, {velocity}+ "
        "attempts in ten minutes, and several cards cycling on one device."
    )
    return logic, description, "CardTestingBurst"


def _rule_watchlist_merchant_low_trust(variant: int) -> tuple[str, str, str]:
    trust_score = 35 + (variant * 5)
    logic = (
        "if $merchant_id in @WatchlistMerchants and $card_present == 0 "
        f"and $device_trust_score <= {trust_score} and $amount >= 150:\n"
        "    return 'CANCEL'"
    )
    description = (
        f"Decline card-not-present traffic hitting watchlist merchants when the device trust score falls "
        f"to {trust_score} or below."
    )
    return logic, description, "WatchlistMerchantLowTrust"


def _rule_repeat_chargeback_cnp(variant: int) -> tuple[str, str, str]:
    amount = 240 + (variant * 80)
    logic = (
        f"if $prior_chargebacks_180d >= 2 and $card_present == 0 and $amount >= {amount} "
        "and $merchant_category in ['fashion', 'electronics', 'travel', 'luxury']:\n"
        "    return 'HOLD'"
    )
    description = (
        f"Review repeat-chargeback customers re-entering card-not-present commerce above {amount}, "
        "especially in higher-dispute retail categories."
    )
    return logic, description, "RepeatChargebackCnp"


def _rule_night_velocity_payout(variant: int) -> tuple[str, str, str]:
    velocity = 4 + variant
    review_hits = 1 + (variant % 2)
    logic = (
        "if $txn_type in ['wallet_cashout', 'instant_payout', 'bank_transfer'] and "
        f"$beneficiary_age_days <= 3 and $txn_velocity_1h >= {velocity} and $manual_review_hits_30d >= {review_hits} "
        "and $local_hour <= 4:\n"
        "    return 'HOLD'"
    )
    description = (
        f"Escalate overnight cash-out behavior when a new beneficiary is hit {velocity}+ times per hour "
        f"from an account already seen by review at least {review_hits} time(s)."
    )
    return logic, description, "NightVelocityPayout"


_RULE_BUILDERS = [
    _rule_cross_border_cnp_mismatch,
    _rule_disposable_email_velocity,
    _rule_na_to_latam_reship,
    _rule_showcase_amount_zscore,
    _rule_ato_password_reset,
    _rule_showcase_loop_score,
    _rule_showcase_branch_by_txn_type,
    _rule_sanctioned_cashout,
    _rule_proxy_high_risk_category,
    _rule_card_testing_on_device,
    _rule_watchlist_merchant_low_trust,
    _rule_repeat_chargeback_cnp,
    _rule_night_velocity_payout,
]
