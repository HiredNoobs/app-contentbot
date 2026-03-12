from typing import Dict, List


def calculate_hand_value(hand: List[Dict[str, str]]) -> int:
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
