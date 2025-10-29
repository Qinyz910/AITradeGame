# AITradeGame - AI-Powered A-Share Trading Simulator

[English](README.md) | [中文](README_ZH.md)

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

AITradeGame is an open-source trading simulator dedicated to mainland China's A-share markets. It blends large language model (LLM) reasoning with Shanghai and Shenzhen equity data so you can prototype, test, and compare AI-driven strategies in a realistic, regulation-aware environment. The project ships with a local-first desktop mode and an optional hosted experience with leaderboards.

## Key Features

### Purpose-built for A-shares
- Real-time A-share pricing, fundamentals, and limit prices powered by AkShare
- Market calendar awareness including trading sessions, holidays, and T+1 settlement windows
- Fee and lot-size simulation that reflects mainland exchange rules
- Automatic enrichment of portfolio positions with board metadata, suspension status, and limits

### AI Strategy Workbench
- Multi-provider API management with automatic model discovery for OpenAI-compatible services
- Strategy orchestration with configurable trading cadence and fee structure
- Aggregated dashboard for performance comparison across multiple AI models
- ECharts-powered analytics, historical equity curves, and trade logs

### Deployment Options
- Local desktop build with SQLite persistence — no cloud storage required
- Web-based deployment with background execution and optional leaderboard
- Container image for easy integration into existing infrastructure

## Quick Start

### Online Playground
Launch the hosted playground at https://aitradegame.com to explore the interface and leaderboard without installing anything locally.

### Desktop (Local) Setup
1. Clone this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Start the app: `python app.py`
4. Open http://localhost:5000 in your browser to begin configuring providers and models

> AkShare relies on pandas and numpy. When preparing a clean Python environment, ensure compatible wheels are available (or that you can build them from source) before running the application.

### Docker Deployment
You can also run AITradeGame using Docker:

**Using docker-compose (recommended):**
```bash
# Build and start the container
docker-compose up -d

# Access the application at http://localhost:5000
```

**Using docker directly:**
```bash
# Build the image
docker build -t aitradegame .

# Run the container
docker run -d -p 5000:5000 -v $(pwd)/data:/app/data aitradegame

# Access the application at http://localhost:5000
```

The `data/` directory stores the SQLite database (`AITradeGame.db`). Stop the stack with `docker-compose down` when you are done.

## Configuration

### AI Provider Setup
1. Click **API Provider** in the header
2. Provide a name, API base URL, and API key
3. Fetch available models automatically or add them manually
4. Save to make the provider available to all models

### Adding Trading Models
1. Click **Add Model**
2. Pick an existing AI provider
3. Choose a model, set display name, and allocate initial capital (CNY)
4. Select **A-share** as the market type and confirm to start the simulation loop

### System Settings
Use the **Settings** dialog to control:
- **Trading Frequency:** minutes between AI decisions (1–1440)
- **Trading Fee Rate:** commission per trade leg (0.1% by default)
- **Lot Controls:** when running in A-share mode the engine enforces 100-share lots and disables short selling

### Advanced Configuration (optional)
An example configuration file is provided in `config.example.py`. It mirrors the default behaviour and demonstrates how to:
- Override database location
- Toggle automatic trading and tune the trading interval
- Define a default A-share watchlist (`A_SHARE_SYMBOLS`)
- Adjust AkShare caching windows for quotes and fundamentals

Copy the file to `config.py` and adapt it to your deployment when you need persistent overrides.

## Development

Development requires Python 3.9 or later plus an internet connection for AkShare and LLM API calls. Install dependencies with:

```bash
pip install -r requirements.txt
```

### Verification Checklist
Before shipping documentation or configuration updates, run the keyword scan below to ensure no non A-share terminology slips back into shared templates:

```bash
grep -R --include="config*.py" --include="docker-compose.yml" --include="Dockerfile" \
     --include="CHANGELOG.md" -n "crypto" .
grep -R --include="config*.py" --include="docker-compose.yml" --include="Dockerfile" \
     --include="CHANGELOG.md" -n "coin" .
```

Both commands should return no matches when the repository remains A-share only.

## Privacy & Security
All data stays on your machine in the `AITradeGame.db` SQLite file unless you opt into external AI providers. The application does not create user accounts or phone home.

## Contributing
Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Disclaimer
AITradeGame is a simulation environment for research and experimentation. It does not execute real trades or handle real capital. Always perform independent due diligence before investing in financial markets.

## Links
- Online leaderboard & social features: https://aitradegame.com
- Desktop binaries: https://github.com/chadyi/AITradeGame/releases/tag/main
- Source repository: https://github.com/chadyi/AITradeGame
