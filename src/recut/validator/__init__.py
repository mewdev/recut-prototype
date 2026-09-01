from recut.compositor.nodes import Node, XFade
from recut.map.schema import MusicMap
from recut.validator.rules import RULES, SEQUENCE_RULES
from recut.validator.types import ValidationResult


def validate(music_map: MusicMap, *nodes: Node) -> list[ValidationResult]:
    results: list[ValidationResult] = []

    # per-node rules — XFade has no label/segment, skip it
    for node in nodes:
        if isinstance(node, XFade):
            continue
        for rule in RULES:
            result = rule.check(node, music_map)
            if result:
                results.append(result)

    # sequence-level rules (see full node list)
    for rule in SEQUENCE_RULES:
        results.extend(rule.check(list(nodes), music_map))

    return results
