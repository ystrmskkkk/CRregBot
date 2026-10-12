import random
import math


def shuffle_and_build_round1(participant_ids: list[int]):
    if len(participant_ids) < 2:
        raise ValueError("Нужно минимум 2 участника")

    participants = participant_ids[:]
    random.shuffle(participants)

    n = len(participants)
    next_pow2 = 1
    while next_pow2 < n:
        next_pow2 *= 2

    # лишним до степени двойки — бай
    byes_count = next_pow2 - n
    bye_players = participants[:byes_count]
    playing = participants[byes_count:]

    pairs = []
    for i in range(0, len(playing), 2):
        pairs.append((playing[i], playing[i + 1]))

    return pairs, bye_players


def pair_next_round(winners_in_position_order: list[int]):
    pairs = []
    for i in range(0, len(winners_in_position_order), 2):
        pairs.append((winners_in_position_order[i], winners_in_position_order[i + 1]))
    return pairs
