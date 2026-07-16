import json

import os
_VOCAB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vocab_mandarin.json')

with open(_VOCAB, 'r', encoding='utf-8') as f:
    Mandarin = json.load(f)


def confirmed_vocab_array(language):
    """
    Filters and returns only the confirmed vocab entries from the given language list.
    Each entry should be a dict with keys: 'word', 'correct_use', 'confirmed'.
    """
    return [entry for entry in language if entry.get('confirmed') is True]

def testing_vocab_array(language):
    """
    Filters and returns only the testing vocab entries from the given language list.
    Each entry should be a dict with keys: 'word', 'correct_use', 'confirmed'.
    """
    return [entry for entry in language if entry.get('Testing') is False]


def increment_correct_use(entry):
    """
    Increments the 'correct_use' property of the given vocab entry by one.
    Modifies the entry in place. Returns nothing.
    """
    if 'correct_use' in entry and isinstance(entry['correct_use'], int):
        entry['correct_use'] += 1



__all__ = [
    'confirmed_vocab_array',
    'testing_vocab_array',
    'increment_correct_use',
    'Mandarin',
]