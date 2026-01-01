# LLM Tray Manager and quick chat


## About 

This application provides a system tray icon for easy management and interaction with your LLM server (e.g., Ollama Docker instance), acting as an LLM tray icon. It allows you to start and stop the LLM server container, list available models, and initiate chat sessions directly from your system tray.



Functions:
- List installed models
- Start a chat with a selected model
- Send messages to the selected model
- Start and stop LLM server docker container 

## Installation 


1. Make sure you have Python 3.8+ installed.
2. Installed Docker and Ollama. If you plan to use a `docker-compose.yml` file, ensure Docker Compose is also installed.

**Install from .deb package**

Latest deb package is in the `deb_dist` folder.

Install using apt to install dependencies if not installed: 

```bash
sudo apt install ./deb_dist/llm-tray-icon_1.0_amd64.deb
```
