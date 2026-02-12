# VPS Setup — Ubuntu + Python 3.10 (venv310)

## Vereisten

- Ubuntu VPS (22.04+ aanbevolen)
- `pyenv` geïnstalleerd met `pyenv-virtualenv` plugin
- Python 3.10.13 via pyenv: `pyenv install 3.10.13`
- Git

---

## Eenmalige setup

```bash
cd /root/projects/opcw_xauusd
git clone <repo-url> .          # of git pull als repo al bestaat
```

Het script `scripts/vps_run.sh` regelt alles automatisch:
- Activeert pyenv + Python 3.10.13
- Maakt `.venv310` aan als die ontbreekt of kapot is
- Installeert alle dependencies
- Draait tests + rapport

### Script aanmaken (eenmalig)

```bash
cat > scripts/vps_run.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Always make pyenv available (even in non-interactive shells)
export PATH="$HOME/.pyenv/bin:$PATH"
if command -v pyenv >/dev/null 2>&1; then
  eval "$(pyenv init -)"
  eval "$(pyenv virtualenv-init -)" || true
  pyenv local 3.10.13
fi

# Rebuild venv if missing or broken (bin/activate must exist)
if [ ! -f ".venv310/bin/activate" ]; then
  echo "[vps_run] .venv310 missing/broken -> rebuilding"
  rm -rf .venv310
  python -m venv .venv310
fi

source .venv310/bin/activate
python --version

pip install -U pip setuptools wheel
pip install ".[dev,yfinance]"

pytest
python scripts/make_report.py
SH

chmod +x scripts/vps_run.sh
```

---

## Dagelijkse routine

```bash
cd /root/projects/opcw_xauusd
git pull
./scripts/vps_run.sh
```

Dat is alles. Het script:

1. Zet pyenv op Python 3.10.13
2. Checkt of `.venv310` bestaat — zo niet, maakt het opnieuw aan
3. Activeert de venv
4. Upgrade pip/setuptools/wheel
5. Installeert het project met dev + yfinance extras
6. Draait `pytest`
7. Draait `make_report.py`

---

## Troubleshooting kennisbank

Bekende issues en oplossingen, verzameld uit eerdere VPS-sessies.

### Git & bestanden uit sync

| Probleem | Oorzaak | Oplossing |
|----------|---------|-----------|
| `ImportError: cannot import name 'X'` na `git pull` | Bestand lokaal overschreven door script/agent, `git pull` raakt alleen tracked files aan die niet conflicteren | `git checkout -- <pad/naar/bestand.py>` om de git-versie te herstellen |
| Bestanden handmatig gewijzigd op VPS, `git pull` faalt met conflict | Lokale wijzigingen blokkeren pull | `git stash && git pull && git stash pop` of `git checkout -- .` om alles te resetten |
| Tests falen na pull, maar code is correct in repo | Stale `.pyc`-cache | `find . -name '*.pyc' -delete && find . -name '__pycache__' -type d -exec rm -rf {} +` |
| `git pull` zegt "Already up to date" maar code is oud | Lokale branch wijst naar ander remote of is detached | `git fetch origin && git reset --hard origin/main` |

**Gouden regel:** wijzig nooit bestanden direct op de VPS. Alle code-changes via lokale machine → push → pull op VPS.

---

### pyenv & Python

| Probleem | Oorzaak | Oplossing |
|----------|---------|-----------|
| `pyenv: command not found` | pyenv niet in PATH (non-interactive shell) | Voeg toe aan `~/.bashrc`: `export PATH="$HOME/.pyenv/bin:$PATH"` + `eval "$(pyenv init -)"` + `eval "$(pyenv virtualenv-init -)"` |
| `python 3.10.13 not installed` | Versie niet geïnstalleerd via pyenv | `pyenv install 3.10.13` (kan 5-10 min duren op VPS) |
| `pyenv install` faalt met build errors | Missende build-dependencies | `apt update && apt install -y build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev libffi-dev liblzma-dev` |

---

### venv310

| Probleem | Oorzaak | Oplossing |
|----------|---------|-----------|
| venv kapot na OS-update | Systeem-Python geüpgrade, venv links broken | Verwijder en herbouw: `rm -rf .venv310 && python -m venv .venv310` (of draai `vps_run.sh` — doet dit automatisch) |
| `ModuleNotFoundError` voor pakket dat wél geïnstalleerd zou moeten zijn | Verkeerde Python/venv actief | Check: `which python` moet `/root/projects/opcw_xauusd/.venv310/bin/python` zijn. Zo niet: `source .venv310/bin/activate` |
| `pip install ".[dev,yfinance]"` faalt | `pyproject.toml` ontbreekt of extras staan er niet in | Check `pyproject.toml` in project root, sectie `[project.optional-dependencies]` |
| `pip install` timeout / SSL error | VPS netwerk issue | `pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org ".[dev,yfinance]"` |

---

### Tests & rapport

| Probleem | Oorzaak | Oplossing |
|----------|---------|-----------|
| `pytest` niet gevonden | Niet geïnstalleerd in venv | `pip install pytest` of `pip install ".[dev]"` |
| Tests falen met `ImportError` | Module niet gevonden — venv niet actief of package niet geïnstalleerd | `source .venv310/bin/activate && pip install -e ".[dev,yfinance]"` |
| `make_report.py` crasht op backtest | Geen marktdata aanwezig | Eerst fetch draaien: `python -m src.trader.app --config configs/xauusd.yaml fetch --days 30` |
| `Dict[str, float] \| None` SyntaxError | Python < 3.10 actief (union type syntax) | Check `python --version` — moet 3.10+ zijn. Fix: `pyenv local 3.10.13` |

---

### Snelle diagnose-commando's

```bash
# Welke Python draai ik?
which python && python --version

# Is de venv actief?
echo $VIRTUAL_ENV

# Zit mijn repo op de juiste commit?
git log --oneline -1

# Zijn er lokale wijzigingen die conflicteren?
git status --short

# Heeft een bestand de verwachte functie?
grep -n "functienaam" pad/naar/bestand.py

# Nuclear reset (verliest ALLE lokale wijzigingen):
git fetch origin && git reset --hard origin/main
rm -rf .venv310
./scripts/vps_run.sh
```

---

## Git push vanaf VPS instellen

Standaard kan de VPS alleen pullen. Om ook te pushen (bv. config-wijzigingen na optimalisatie):

### Optie A: SSH key (aanbevolen)

```bash
# 1. Genereer SSH key op VPS (eenmalig)
ssh-keygen -t ed25519 -C "vps-opcw" -f ~/.ssh/id_ed25519 -N ""

# 2. Toon de public key
cat ~/.ssh/id_ed25519.pub

# 3. Kopieer de output en voeg toe op GitHub:
#    GitHub → Settings → SSH and GPG keys → New SSH key

# 4. Wijzig remote URL naar SSH
cd /root/projects/opcw_xauusd
git remote set-url origin git@github.com:roelofgootjesgit/opcw_xauusd.git

# 5. Test
ssh -T git@github.com
git push
```

### Optie B: Personal Access Token (snel maar minder veilig)

```bash
# 1. Maak token aan op GitHub:
#    GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
#    Rechten: Contents (read/write)

# 2. Stel remote URL in met token
git remote set-url origin https://<USERNAME>:<TOKEN>@github.com/roelofgootjesgit/opcw_xauusd.git

# 3. Test
git push
```

**Let op:** bij Optie B staat je token in plain text in `.git/config`. Gebruik Optie A voor productie.
