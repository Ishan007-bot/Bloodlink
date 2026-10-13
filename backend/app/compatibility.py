"""Red-cell ABO/Rh compatibility.

For each recipient group, the donor groups it can safely receive, in the order the
allocator prefers them: the exact group first, then the same ABO group with the other
Rh type, then other ABO groups, and O- (the universal donor) always last so it is kept
for patients who can receive nothing else.
"""

BLOOD_GROUPS: tuple[str, ...] = ("O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+")

RECIPIENT_CAN_RECEIVE: dict[str, tuple[str, ...]] = {
    "O-": ("O-",),
    "O+": ("O+", "O-"),
    "A-": ("A-", "O-"),
    "A+": ("A+", "A-", "O+", "O-"),
    "B-": ("B-", "O-"),
    "B+": ("B+", "B-", "O+", "O-"),
    "AB-": ("AB-", "A-", "B-", "O-"),
    "AB+": ("AB+", "AB-", "A+", "A-", "B+", "B-", "O+", "O-"),
}


def donor_groups_for(recipient: str) -> tuple[str, ...]:
    """Donor groups a recipient can receive, most preferred first."""
    try:
        return RECIPIENT_CAN_RECEIVE[recipient]
    except KeyError:
        raise ValueError(f"unknown blood group: {recipient!r}") from None


def recipients_for(donor: str) -> tuple[str, ...]:
    """Recipient groups that can receive blood from this donor group."""
    if donor not in RECIPIENT_CAN_RECEIVE:
        raise ValueError(f"unknown blood group: {donor!r}")
    return tuple(r for r in BLOOD_GROUPS if donor in RECIPIENT_CAN_RECEIVE[r])


def is_compatible(donor: str, recipient: str) -> bool:
    return donor in donor_groups_for(recipient)
