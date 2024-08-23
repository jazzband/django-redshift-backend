# setup
set -ex

curl -LsSf https://astral.sh/uv/install.sh | sh
. $HOME/.cargo/env
uv tool install -U ruff
uv tool install -U tox --with tox-uv
uv sync --extra psycopg2-binary
