# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.1.x   | :white_check_mark: |
| 2.0.x   | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in GameBooster, please report it responsibly:

1. **DO NOT** create a public GitHub issue
2. Email: [YOUR_EMAIL_HERE] (or use GitHub's private vulnerability reporting if enabled)
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

## What We Consider Vulnerabilities

- **Registry operations** that could corrupt Windows
- **Privilege escalation** risks
- **Data exposure** through log files
- **DLL injection** or code execution vulnerabilities
- **Race conditions** in service manipulation

## What We Don't Consider Vulnerabilities

- Expected behavior of Windows API calls
- Issues requiring physical access to the machine
- Problems caused by third-party software conflicts

## Response Timeline

- **Initial response**: Within 7 days
- **Status update**: Within 14 days
- **Fix target**: Within 30 days for critical issues

## Security Best Practices We Follow

1. **Backup before changes** - All registry and service modifications are backed up
2. **Reversible operations** - Every change has a restore path
3. **No network calls** - The application doesn't phone home
4. **No data collection** - We don't collect or transmit user data
5. **Open source** - All code is visible for audit

## Acknowledgments

We appreciate responsible disclosure and will credit security researchers (with permission) in our security advisories.
