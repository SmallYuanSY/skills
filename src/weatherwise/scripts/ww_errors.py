"""Errors the model reads. Every code comes with the next step to take."""

ACTIONS = {
    "no_default_location": "ask the user where they are, then run: config set-default <place>",
    "place_not_found": "try another spelling, add --global for places outside Taiwan, or pass lat,lon",
    "network_error": "tell the user the weather could not be fetched right now",
    "service_error": "tell the user the weather service returned an error; try again later",
    "config_invalid": "ask the user to check or delete the config file, then set it up again with the config commands",
    "weatherkit_config_incomplete": "run: config weatherkit with the missing values, or config weatherkit --remove to use the free source",
    "weatherkit_key_missing": "run: config weatherkit again with --key-file <path to the .p8>, or config weatherkit --remove",
    "weatherkit_auth_failed": "tell the user WeatherKit rejected the key (wrong IDs, revoked key, or expired Apple Developer membership); nothing was saved",
    "invalid_key_file": "ask the user for the path to the AuthKey_<KeyID>.p8 file they downloaded from Apple",
    "unsupported_lang": "use a BCP 47 language tag such as zh-TW, en, or ja",
    "bad_arguments": "fix the command using the usage in SKILL.md",
    "internal_error": "tell the user weatherwise hit an unexpected problem; try again later, and if it keeps happening, report it at https://github.com/SmallYuanSY/skills/issues",
}


class WwError(Exception):
    def __init__(self, code: str, detail: str = ""):
        if code not in ACTIONS:
            raise ValueError(f"unknown error code: {code}")
        super().__init__(code)
        self.code = code
        self.detail = detail
