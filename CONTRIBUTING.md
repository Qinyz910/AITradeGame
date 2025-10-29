# Contributing

Thank you for considering contributing to AITradeGame! This project is dedicated to mainland China's A-share market, so please keep wording and examples aligned with that scope when making changes.

## Development Setup
1. Fork the repository
2. Clone your fork locally
3. Install dependencies: `pip install -r requirements.txt`
4. Make your changes on a feature branch
5. Test thoroughly
6. Submit a pull request

## Code Style
- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add comments when logic is non-obvious
- Keep functions focused and concise

## Pull Request Process
1. Update documentation (README, README_ZH) if your change alters behaviour or user flows
2. Update `CHANGELOG.md` with a summary of your change
3. Run the verification commands to ensure restricted terminology has not returned to shared configuration assets:
   ```bash
   grep -R --include="config*.py" --include="docker-compose.yml" --include="Dockerfile" \
        --include="CHANGELOG.md" -n "crypto" .
   grep -R --include="config*.py" --include="docker-compose.yml" --include="Dockerfile" \
        --include="CHANGELOG.md" -n "coin" .
   ```
4. Ensure all automated tests and checks pass
5. Request a maintainer review

## Reporting Issues
- Use GitHub Issues
- Provide a clear description and reproduction steps
- Include relevant logs or screenshots when possible

## Questions?
Open an issue for discussion. We're excited to see how you extend the A-share trading simulator!
