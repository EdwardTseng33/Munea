from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "deploy" / "glows" / "restart-flashhead.sh").read_text(
    encoding="utf-8"
)

old_env = SOURCE.index('done < "/proc/$pid/environ"')
persistent_env = SOURCE.index('source "$ENV_FILE"')
launch = SOURCE.index('nohup "$PY" -u "$APP"')

assert old_env < persistent_env < launch
assert 'ENV_FILE="${MUNEA_FACE_ENV_FILE:-/root/munea-face.env}"' in SOURCE
assert "set -a" in SOURCE and "set +a" in SOURCE

print("Glows restart persistent environment precedence: PASS")
