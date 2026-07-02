import os


def load_env_file(path, override=False):
    loaded = []
    if not path or not os.path.exists(path):
        return loaded

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key:
                continue
            if override or key not in os.environ:
                os.environ[key] = value
                loaded.append(key)
    return loaded


def load_engine_env(filename=".env.local", override=False):
    if os.environ.get("MUNEA_SKIP_ENV_LOCAL") in {"1", "true", "TRUE", "yes", "YES"}:
        return []
    here = os.path.dirname(os.path.abspath(__file__))
    return load_env_file(os.path.join(here, filename), override=override)
