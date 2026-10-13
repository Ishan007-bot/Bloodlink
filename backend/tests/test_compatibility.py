import pytest

from app.compatibility import BLOOD_GROUPS, donor_groups_for, is_compatible, recipients_for


def test_o_negative_can_only_receive_o_negative():
    assert donor_groups_for("O-") == ("O-",)


def test_ab_positive_is_universal_recipient():
    assert set(donor_groups_for("AB+")) == set(BLOOD_GROUPS)


def test_o_negative_is_universal_donor():
    assert set(recipients_for("O-")) == set(BLOOD_GROUPS)


def test_ab_positive_can_only_donate_to_ab_positive():
    assert recipients_for("AB+") == ("AB+",)


@pytest.mark.parametrize("group", BLOOD_GROUPS)
def test_exact_group_is_always_preferred_first(group):
    assert donor_groups_for(group)[0] == group


@pytest.mark.parametrize("group", BLOOD_GROUPS)
def test_universal_donor_is_always_last_resort(group):
    assert donor_groups_for(group)[-1] == "O-"


@pytest.mark.parametrize(
    ("donor", "recipient", "expected"),
    [
        ("O+", "A+", True),
        ("O+", "A-", False),  # Rh+ blood must not go to an Rh- patient
        ("A+", "B+", False),  # anti-A antibodies in a B patient
        ("A-", "AB-", True),
        ("B-", "AB+", True),
        ("AB-", "A-", False),
    ],
)
def test_compatibility_pairs(donor, recipient, expected):
    assert is_compatible(donor, recipient) is expected


@pytest.mark.parametrize("group", BLOOD_GROUPS)
def test_donor_and_recipient_views_agree(group):
    for recipient in recipients_for(group):
        assert group in donor_groups_for(recipient)


def test_unknown_group_is_rejected():
    with pytest.raises(ValueError):
        donor_groups_for("C+")
    with pytest.raises(ValueError):
        recipients_for("Z-")
