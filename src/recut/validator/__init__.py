from recut.compositor.nodes import Node
from recut.map.schema import MusicMap
from recut.validator.rules import RULES, SEQUENCE_RULES
from recut.validator.types import ValidationResult


def validate(music_map: MusicMap, *nodes: Node) -> list[ValidationResult]:
    results: list[ValidationResult] = []

    # per-node rules
    for node in nodes:
        for rule in RULES:
            result = rule.check(node, music_map)
            if result:
                results.append(result)

    # sequence-level rules (see full node list)
    for rule in SEQUENCE_RULES:
        results.extend(rule.check(list(nodes), music_map))

    return results
