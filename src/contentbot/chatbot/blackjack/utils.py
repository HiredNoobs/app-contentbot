from typing import Dict, List


def calculate_hand_value(hand: List[Dict[str, str]]) -> int:
    """
    Calculate the value of a given hand.

    Args:
        hand (List[Dict[str, str]]): Hand to calculate. A List of Dicts,
            each Dict should contain a "rank" key with the value of the card.
            Face cards should be the upper case first letter (e.g. Jack -> J).

    Returns:
        int: The numerical value of the hand.
    """
    value = 0
    num_aces = 0
    for card in hand:
        rank = card["rank"]
        if rank in ["J", "Q", "K"]:
            value += 10
        elif rank == "A":
            num_aces += 1
        else:
            value += int(rank)
    for _ in range(num_aces):
        value += 11 if value + 11 <= 21 else 1
    return value
