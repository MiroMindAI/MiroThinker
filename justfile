default:
    just --list

# lint monorepo
[group('precommit')]
lint:
    uv tool run ruff@0.8.0 check --fix .

# sort imports
[group('precommit')]
sort-imports:
    uv tool run ruff@0.8.0 check --select I --fix .

# format monorepo
[group('precommit')]
format:
    uv tool run ruff@0.8.0 format .

# check license
[group('precommit')]
check-license:
    uv run reuse lint

# insert license for contributor
insert-license:
    # https://reuse.readthedocs.io/en/stable/scripts.html#add-headers-to-staged-files-based-on-git-settings
    git diff --name-only --cached | xargs -I {} reuse annotate -c "$(git config --get user.name) <$(git config --get user.email)>" "{}"

# run precommit before PR
[group('precommit')]
precommit: lint sort-imports format

# format markdown files
[group('precommit')]
format-md:
    uv tool run mdformat@0.7.17 .