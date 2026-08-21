# utils_prompt.py

import re

def build_prompt_for_module(module_key: str, prompts: dict, context: dict, **kwargs):
    module = prompts.get(module_key, {})
    system_template = module.get("system", "") or ""
    user_template = module.get("user", "") or ""

    values = {
        "context": (
            "PROJEKTBESCHREIBUNG:\n" + context.get("project_description", "") +
            "\n\nTEILNEHMERKONTEXT:\n" + context.get("participants", "") +
            "\n\nMETHODISCHER KONTEXT:\n" + context.get("methodology", "")
        ),
        "strict_rules_segments": prompts.get("strict_rules_segments", ""),
        "strict_rules_global": prompts.get("strict_rules_global", ""),
        "swot_strict_rules": prompts.get("swot_strict_rules", ""),
        "json_schema": prompts.get("json_schema", ""),
        "subcat": "",
        "facets": "",
        "segments": "",
        "clusters": "",
        "category": "",
        "subcats": "",
        "categories": "",
        "persons": "",
        "terms": "",
        "data": ""
    }
    values.update(kwargs)

    for k in values:
        if values[k] is None:
            values[k] = ""

    def safe_format(template):
        placeholders = {}
        pattern = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

        def replace(match):
            key = match.group(1)
            if key in values:
                token = f"__PH_{len(placeholders)}__"
                placeholders[token] = str(values[key])
                return token
            return match.group(0)

        protected = pattern.sub(replace, template)
        protected = protected.replace("{", "{{").replace("}", "}}")

        for token in placeholders:
            protected = protected.replace(token, "{__PLACEHOLDER__}")

        try:
            result = protected.format(__PLACEHOLDER__="__PLACEHOLDER__")
        except Exception:
            return template

        for token, value in placeholders.items():
            result = result.replace("__PLACEHOLDER__", value, 1)

        return result

    return safe_format(system_template), safe_format(user_template)
