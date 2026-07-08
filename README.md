Pedigreeall AI Horse Racing Prediction Platform
> Open-source AI platform for collecting, analyzing and predicting
> Turkish horse racing results using machine learning.
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows-lightgrey)
![Status](https://img.shields.io/badge/Status-Active-success)
![ML](https://img.shields.io/badge/Machine-Learning-orange)
Table of Contents
Overview
Features
Architecture
Project Structure
Installation
Quick Start
API Discovery
Machine Learning Pipeline
Data Lifecycle
VPS Deployment
Backup Strategy
Roadmap
Contributing
License
---
Overview
Pedigreeall is an open-source platform for collecting, processing and
analyzing Turkish horse racing data.
The project automatically discovers public API endpoints, downloads
available race information, builds a historical SQLite warehouse,
prepares ML-ready datasets and serves predictions through a read-only
FastAPI dashboard.
Key Features
Automated API discovery
Historical race warehouse
Pedigree analysis
Feature engineering
ML prediction pipeline
Prediction evaluation
SHAP explainability
FastAPI dashboard
SQLite warehouse
CSV / Parquet export
VPS deployment
Automatic backup
Scheduled updates
Architecture
``` text
Pedigreeall API
      │
      ▼
Endpoint Discovery
      │
      ▼
Data Collection
      │
      ▼
SQLite Warehouse
      │
      ▼
Normalization
      │
      ▼
Feature Engineering
      │
      ▼
Machine Learning
      │
      ▼
Prediction Dashboard
```
Project Structure
``` text
discover_endpoints.py
probe_public_endpoints.py
discover_horses.py
scrape_pedigreeall.py
normalize_data.py
analyze_dataset.py
pedigreeall_core.py
web_app.py
tests/
deploy/
lake/
reports/
output/
```
Installation
``` bash
git clone https://github.com/KynTr4/at_yaris_tahmini.git
cd at_yaris_tahmini

python3.11 -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install -r requirements.txt
```
Quick Start
``` bash
python discover_endpoints.py
python discover_horses.py
python scrape_pedigreeall.py
python normalize_data.py
python analyze_dataset.py
```
API Discovery
The project validates available endpoints before downloading data.
Supported capabilities include:
Endpoint discovery
Anonymous endpoint probing
Access restriction reporting
Automatic retry
Resume support
Rate limiting
Request deduplication
Machine Learning Pipeline
Data Collection
Data Validation
Normalization
Feature Engineering
Dataset Generation
Model Training
Evaluation
Prediction
Dashboard
Data Lifecycle
Raw JSON
↓
SQLite Warehouse
↓
Normalized Tables
↓
Feature Engineering
↓
Training Dataset
↓
Prediction Models
↓
Dashboard
VPS Deployment
The repository includes:
Git deployment
Automatic migrations
Health checks
Systemd timers
Read-only dashboard
Backup automation
Rollback support
Backup Strategy
Daily backups
Weekly backups
Monthly backups
SQLite Hot Backup
Automatic cleanup
Log rotation
Roadmap
Better prediction accuracy
Docker support
PostgreSQL support
Distributed training
Live prediction API
Additional ML models
Better explainability
Performance dashboard
Contributing
Contributions are welcome.
Please create an issue before opening a pull request.
License
MIT License (recommended).
Disclaimer
This project is intended for research and educational purposes.
Horse racing predictions are probabilistic estimates and should not be
considered guaranteed outcomes.
---
Existing Technical Documentation
Paste your existing detailed sections below this heading without
modification:
Public API mode
Endpoint catalog
Automatic horse discovery
Data lifecycle
Reliability
Test plan
VPS deployment
Backup system
Cleanup
Production deployment
