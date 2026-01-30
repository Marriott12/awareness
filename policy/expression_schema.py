EXPRESSION_SCHEMA = {
    'type': 'object',
    'properties': {
        'op': {'type': 'string', 'enum': ['and', 'or', 'not']},
        'items': {
            'type': 'array',
            'items': {
                'anyOf': [
                    {'type': 'object', 'properties': {'rule': {'type': 'string'}}, 'required': ['rule']},
                    {'type': 'object', 'properties': {'rule_id': {'type': ['integer', 'string']}}, 'required': ['rule_id']},
                    {'$ref': '#'}
                ]
            }
        }
    },
    'required': ['op', 'items']
}
