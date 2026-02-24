# Contributing to VideoCue

Thank you for considering contributing to VideoCue!

## Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/jpwalters/VideoCue.git
   cd VideoCue
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   source .venv/bin/activate  # macOS/Linux
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install ruff  # For linting
   ```

4. **Install NDI Runtime (optional)**
   Download from https://ndi.tv/tools/

## Code Style

- Follow PEP 8 conventions
- Use Ruff for linting: `ruff check .`
- Use type hints where appropriate
- Add docstrings for public methods
- Keep functions focused and under 50 lines when possible

## Testing

Before submitting a PR:
- [ ] Test with real PTZ camera hardware if available
- [ ] Test NDI discovery and streaming
- [ ] Test USB controller functionality
- [ ] Test connection state management
- [ ] Verify error handling (try to break it!)
- [ ] Check console for warnings/errors

See QUICKSTART.md for comprehensive testing checklist.

## Pull Request Process

1. Create a feature branch: `git checkout -b feature/your-feature-name`
2. Make your changes with clear commit messages
3. Test thoroughly
4. Update documentation if needed (README.md, QUICKSTART.md)
5. Submit a pull request with:
   - Clear description of changes
   - Testing performed
   - Screenshots/videos if UI changes

## Bug Reports

Please include:
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Console output/error messages
- Camera model (if relevant)

## Feature Requests

We welcome feature requests! Please:
- Check existing issues first
- Describe the use case
- Explain why it would be useful
- Consider submitting a PR!

## Areas for Contribution

- **Cue tab enhancements**: Additional bulk edit tools, filtering, and run workflow improvements
- **Additional camera support**: Test with more VISCA-compatible cameras
- **Keyboard shortcuts**: Add hotkeys for common operations
- **Camera nicknames**: User-friendly naming separate from NDI source names
- **Preset thumbnails**: Visual previews for presets
- **Unit tests**: Improve test coverage (config validation, VISCA commands)
- **Documentation**: Examples, tutorials, troubleshooting guides
- **Performance**: Profile and optimize NDI frame reception pipeline

## Questions?

Open an issue with the "question" label.

Thank you for contributing! 🎥
