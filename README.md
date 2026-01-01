# LLM Tray Manager & Chat (Docker)


## About 

AI is becomming a thing and local AI models running on a local server are very usefull while coding and other things. While Ollama by itself doasnt consume much resources running on Docker container I wanted to have possibility to start / stop the container. 

Next feature that I wanted was to show if models are running and using my GPU. 

So next step was to put some quick interaction with local AI LLMs. This comes handy if you don't need much and just want to rethink a subject or something with help of local AI. Posibilities when having active AI on the system are endless but just a fact that your expensive graphic card/s that you don't use for gaming because you have to brain out a lot is great.

This application provides a system tray icon for easy management and interaction with your LLM server (e.g., Ollama Docker instance), acting as an LLM tray icon. It allows you to start and stop the LLM server container, list available models, and initiate chat sessions directly from your system tray.

For now this program is only for debian based systems runnning local LLMs on Ollama docker. This might change in the future if I find more time. 

Functions:
- List installed models 
- Start a chat with a selected model
- Send messages to the selected model
- Start and stop LLM server docker container 
- manage docker instance name that is running Ollama (for now)
- 

## Installation 


1. Make sure you have Python 3.8+ installed.
2. Installed Docker and Ollama. If you plan to use a `docker-compose.yml` file, ensure Docker Compose is also installed.

**Install from .deb package**

Latest deb package is in the `deb_dist` folder.

Install using apt to install dependencies if not installed: 

```bash
sudo apt install ./deb_dist/llm-tray-icon_1.0_amd64.deb
```
