"""Request sizes for newly scheduled writing; persisted steps keep their payloads."""


def shots_per_request(config: dict) -> int:
    return 2 if config.get("story_engine") == "cpu_4b" else 4
