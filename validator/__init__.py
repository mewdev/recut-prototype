from compositor import Node
from map_parser import MapParser
from validator.rules import RULES
from validator.types import ValidationResult

def validate(parser: MapParser, *nodes: Node) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    for node in nodes:
        for rule in RULES:
            result = rule.check(node, parser)
            if result: results.append(result)

    return results