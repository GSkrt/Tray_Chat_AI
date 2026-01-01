<p align="center">
  <img src="images/llm_tray_default.png" alt="LLM Tray Manager Icon" width="250">
</p>


# LLM Tray Manager

A lightweight system tray application for Linux to manage local LLM (Large Language Model) servers using **Ollama** and **Docker**.

It provides a quick way to check if your LLM server is running, see if it's using CPU or GPU, start/stop the server, and even chat with models directly from your desktop.

Right now program works with ollama docker image. Idea is to start and stop docker image using system tray and quickly get to chat with your locally installed AI model. 
This is a quick 1 day project durring hollidays so don't expect much for now. 

Check video below.  

## Demo

Sorry I know It's too fast overview, but you can get the point...



https://github.com/user-attachments/assets/4ee96f3e-75c8-4be9-a838-429e1794580b



## Features

*   **System Tray Indicator**: Visual status of your Ollama container (Stopped, Running on CPU, Running on GPU). Detection is done by checking the Docker process list giving square around lama icon if CPU and round for GPU. 
*   **Control**: Start and Stop the Ollama Docker container easily.
*   **Model Management**: Pull new models and select which model to run.
*   **Chat Interface**: A built-in chat window with syntax highlighting for code blocks.
*   **Docker Integration**: Works with existing Docker setups or Docker Compose.

## Prerequisites

*   **Linux** (Tested on Debian/Ubuntu based systems)
*   **Docker** installed and running.
*   **Docker nvidia container runtime** for GPU support (if you're using a machine with a GPU).
*   **Python 3**

## Installation

### Option 1: Install via Debian Package (.deb)
Check the [Releases](https://github.com/GSkrt/LLM-tray-manager-and-chat/releases) page for the latest `.deb` file.

```bash
sudo dpkg -i llm-tray-manager_1.0-1_all.deb
sudo apt-get install -f  # To fix any missing dependencies
```

### Option 2: Run from Source

1.  Clone the repository:
    ```bash
    git clone https://github.com/GSkrt/LLM-tray-manager-and-chat.git
    cd llm-tray-manager
    ```

2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
    *Note: On some Linux distributions, it is recommended to install PyQt5 via your package manager (e.g., `sudo apt install python3-pyqt5`).*

3.  Run the application:
    ```bash
    python3 llm_tray_manager.py
    ```

## Usage

1.  Launch the application.
2.  Right-click the tray icon (Llama head).
3.  Select **Start LLM Server** if it's not running.
4.  Select **Chat with selected LLM Model** to open the chat interface.

## License

This project is licensed under the GPLv3 License - see the LICENSE.txt file for details.
