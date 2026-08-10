from map_parser import MapParser
from nodes import Node
from validator.rules import RULES, SEQUENCE_RULES
from validator.types import ValidationResult


def validate(parser: MapParser, *nodes: Node) -> list[ValidationResult]:
    results: list[ValidationResult] = []

    # per-node rules
    for node in nodes:
        for rule in RULES:
            result = rule.check(node, parser)
            if result:
                results.append(result)

    # sequence-level rules (see full node list)
    for rule in SEQUENCE_RULES:
        results.extend(rule.check(list(nodes), parser))

    return results