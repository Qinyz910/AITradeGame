# Changelog

## [2.1.0] - 2024-11

### Changed
- Repositioned documentation to highlight AITradeGame as an A-share-only trading simulator, removing legacy non-equity references.
- Updated `config.example.py`, Docker guidance, and ancillary docs with mainland market defaults.
- Added contributor verification steps to ensure forbidden non–A-share terminology does not return to documentation or sample configurations.

## [2.0.0] - 2024-10

### Added
- Real-time portfolio tracking with live market data
- AI-powered trading decisions via LLM integration
- Interactive web dashboard with ECharts
- Multi-model support (OpenAI, DeepSeek, Claude)
- Expanded equity trading simulation capabilities
- Automatic trading loop
- Historical performance charts
- Trade execution logging

### Changed
- Migrated frontend to modern ES6+ JavaScript
- Improved UI/UX with clean design system
- Enhanced chart visualization with auto-scaling
- Optimized database queries for better performance

### Fixed
- Timezone display for accurate timestamps
- Real-time P&L calculation for open positions
- Chart value consistency with account stats
- Position value calculation with fee-aware adjustments

## [1.0.0] - 2024-09

### Added
- Initial release
- Basic trading simulation
- Database setup
- Flask server
