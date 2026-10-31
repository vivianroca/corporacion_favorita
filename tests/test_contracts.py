from decimal import Decimal

import pytest

from reposicion.contracts import ContractError, event_applies, validate_relation


def sale(**changes):
    return {
        "id": "1",
        "date": "2017-01-01",
        "store_nbr": "1",
        "family": "DAIRY",
        "sales": "1.25",
        "onpromotion": "2",
        **changes,
    }


def test_fractional_zero_and_new_family(contracts):
    assert contracts.validate_row("train", sale())["sales"] == Decimal("1.25")
    assert contracts.validate_row("train", sale(sales="0"))["sales"] == 0
    assert contracts.validate_row("train", sale(family="NEW FAMILY"))["family"] == "NEW FAMILY"


@pytest.mark.parametrize(
    "changes",
    [
        {"sales": ""},
        {"sales": "NaN"},
        {"sales": "Infinity"},
        {"sales": "-1"},
        {"onpromotion": "1.5"},
        {"date": "2017-02-30"},
        {"date": "20170101"},
        {"store_nbr": "0"},
        {"family": " "},
        {"id": "1.5"},
        {"onpromotion": "-1"},
    ],
)
def test_bad_sales_rows_fail_without_imputation(contracts, changes):
    with pytest.raises(ContractError):
        contracts.validate_row("train", sale(**changes))


def test_nullable_oil_is_not_zero(contracts):
    result = contracts.validate_row("oil", {"date": "2017-01-01", "dcoilwtico": ""})
    assert result["dcoilwtico"] is None
    with pytest.raises(ContractError):
        contracts.validate_row("oil", {"date": "2017-01-01", "dcoilwtico": "NaN"})


def test_transactions_keep_store_day_grain(contracts):
    row = {"date": "2017-01-01", "store_nbr": "1", "transactions": "5"}
    assert contracts.validate_row("transactions", row)["transactions"] == 5
    with pytest.raises(ContractError):
        contracts.validate_row("transactions", {**row, "family": "DAIRY"})
    with pytest.raises(ContractError):
        contracts.validate_row("transactions", {**row, "transactions": "5.5"})


@pytest.mark.parametrize(
    "locale,name,expected",
    [
        ("National", "Ecuador", True),
        ("Regional", "Pichincha", True),
        ("Regional", "Guayas", False),
        ("Local", "Quito", True),
        ("Local", "Guayaquil", False),
    ],
)
def test_geographical_event_scope(locale, name, expected):
    store = {"city": "Quito", "state": "Pichincha"}
    assert event_applies({"locale": locale, "locale_name": name}, store) is expected


def test_unknown_store_and_unknown_event_location_rejected(contracts):
    with pytest.raises(ContractError, match="tienda desconocida"):
        validate_relation("train", contracts.validate_row("train", sale()), {})
    with pytest.raises(ContractError, match="geográfico"):
        validate_relation("holidays_events", {"locale": "National", "locale_name": "Other"}, {})


def test_holiday_transferred_requires_real_boolean(contracts):
    row = {
        "date": "2017-01-01",
        "type": "Holiday",
        "locale": "National",
        "locale_name": "Ecuador",
        "description": "Ejemplo",
        "transferred": "True",
    }
    assert contracts.validate_row("holidays_events", row)["transferred"] is True
    with pytest.raises(ContractError):
        contracts.validate_row("holidays_events", {**row, "transferred": "true"})
