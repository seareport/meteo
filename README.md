# meteo

## Installation

```bash
# Clone the repository
git clone https://github.com/seareport/meteo
cd meteo

# Create conda environment with metview
conda create -n metview_env metview

# Activate the conda environment (stacked)
conda activate --stack --name metview_env

# Create virtualenv using conda's Python
python -m venv .venv

# Install dependencies
poetry install
```
