# Contributing to GameBooster

Thank you for your interest in contributing to GameBooster! This document provides guidelines and instructions for contributing.

## 🎯 What We're Looking For

- **Bug fixes** - Especially for hardware detection edge cases
- **Performance improvements** - Faster detection, more efficient optimizations
- **New hardware support** - Additional GPU/CPU detection patterns
- **Registry tweaks** - Proven, documented Windows optimizations
- **UI/UX improvements** - Better user experience
- **Documentation** - Translations, usage guides, troubleshooting

## 📋 Before You Start

1. **Check existing issues** - Someone might already be working on it
2. **Fork the repository** - Create your own copy
3. **Create a branch** - `git checkout -b feature/your-feature-name`
4. **Test on Windows 10/11** - Ensure compatibility

## � Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/GameBooster.git
cd GameBooster

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
pip install -e ".[dev]"  # For development

# Run the application
python main.py
```

## 🧪 Testing

Before submitting changes:

1. **Test the GUI** - All tabs should load without errors
2. **Test hardware detection** - Verify your GPU/CPU is detected correctly
3. **Test Boost/Restore** - Ensure changes can be applied and reverted
4. **Build the executable** - Run `build.bat` to verify PyInstaller works

## 📝 Code Style

- **Python 3.11+** syntax only
- **Type hints** for function signatures
- **Docstrings** for public functions
- **Hungarian comments** are OK (project is Hungarian-English bilingual)
- **Maximum line length**: 100 characters

## 🔄 Pull Request Process

1. **Update README.md** if you add features
2. **Add your changes** to the changelog section
3. **Squash commits** if you have multiple small fixes
4. **Write a clear PR description** explaining what and why

## ⚠️ Important Notes

### Security
- Never commit `.json` state files (they contain system-specific data)
- Never commit log files with system information
- Don't add registry tweaks without proper backup/restore

### Compatibility
- Must work on **Windows 10 (build 19041+)** and **Windows 11**
- Must work with **Intel iGPU**, **AMD iGPU**, and **Nvidia GPU**
- Admin rights required for Boost functionality

### What NOT to Submit
- Generic "cleaner" features without hardware awareness
- Registry tweaks without sources/documentation
- Process killing (Working Set flush is preferred)
- Anything that modifies game files

## 🐛 Reporting Issues

When reporting a bug, include:

- **Windows version** (Win + R → `winver`)
- **GPU type** (Intel/AMD/Nvidia + model)
- **Python version** (`python --version`)
- **Steps to reproduce**
- **Log file** (`gamebooster.log` from the app directory)
- **Screenshots** if UI-related

## 💡 Feature Requests

Before requesting a feature:

1. Check if it fits the project's scope (hardware-aware gaming optimization)
2. Search existing issues for similar requests
3. Explain the use case, not just the solution

## 📬 Questions?

- **General discussion**: [GitHub Discussions](https://github.com/YOUR_USERNAME/GameBooster/discussions)
- **Bug reports**: [Issues](https://github.com/YOUR_USERNAME/GameBooster/issues)

---

## 🏆 Contributors

Thanks to everyone who contributes! Your efforts make gaming on Windows better for everyone.

<div align="center">

**Happy Gaming! 🎮**

</div>
