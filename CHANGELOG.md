# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2]

### Added
- Online status check for all active connections. The application now verifies connectivity for remote APIs, not just the local Ollama Docker container.
- A new tray icon (`tray_chat_ai_online.png`) is used to indicate when a remote API connection is active and online using models not running in local docker image.
- The chat response now includes a detailed breakdown of token usage, showing input (prompt), output (completion), and total tokens.

### Changed
- Refactored the `AIWorker` to be completely independent of Docker, making it a universal handler for any OpenAI-compatible API.
- The user interface now dynamically adapts based on the selected connection. Ollama-specific menu items (like "Ollama Management" and "Start/Stop Server") are now hidden when a non-Ollama connection is active.
- Selecting a new active connection now triggers an immediate refresh of the connection status in the tray menu.

## [1.0.1] - (Previous Version)

### Fixed
- Placeholder for previous bug fixes. For example: Corrected an issue where the application would not start if the Docker daemon was unavailable.

## [1.0.0] - (Initial Release)

### Added
- Initial release of TrayChat AI.
- Support for local Ollama server management (start, stop, status check) via Docker.
- System tray icon and menu for interacting with LLMs.
- Feature to add, edit, and select different OpenAI-compatible API connections.
- Chat dialog for sending prompts and viewing conversation history.
