<p align="center">
  <img src="images/llm_tray_default.png" alt="LLM Tray Manager Icon" width="250">
</p>


# LLM Tray Manager

A lightweight system tray application for Linux to manage local LLM (Large Language Model) servers using **Ollama** and **Docker**. 

It provides a quick way to check if your LLM server is running, see if it's using CPU or GPU, start/stop the server, and even chat with models directly from your desktop.

Right now program works with ollama docker image. More LLM servers will be added in future.

It was designed for status checking but I'm using it more and more for quick LLM chat interface available in the taskbar.
Chat interface was designed to talk with multiple installed models at once. As such it is very usefull when doing quick brain storming tasks.  


## Functions and GUI


### Status checking 
System tray icon and status checking is done in the taskbar. When GPU is available in Ollama it shows round circle around Lama. 

![status bar gpu working](readme_images/status_bar_gpu_working.png)

When Ollama is using CPU: 
![when cpu running](images/llm_tray_cpu_running.png)

When Ollama is using GPU: 
![ollama running gpu status](images/llm_tray_gpu_running.png)

When there is no docker container with Ollama running: 
![gpu not runing](images/llm_tray_not_running.png)

This statuses ware the main reason why I needed this app. 

### Taskbar and functions overview
On **right click** you will get menu to access basic functions. Currently there is: 

1. Open chat window with model. 
2. Start and stop (docker container running Ollama)
3. Select main chat model (Select LLM model)
4. Function to pull LLM model for Ollama
5. Remove LLM model 
6. Check interval (for working docker image and hardware type used)
7. Name select for docker image (in case it is different as Ollama)
8. Add a program to startup programs
9. Quit

![right click menu](readme_images/right_menu_action.png)

### Chat interface

Chat interface can be envoked by left clicking status icon or using menu option. 
Its a simple interface with a twist, it sends same prompt to multiple models that can be selected using dropdown menu. 
So you can gather info from multiple AI models running in the background. For code it's using black background so for all those looking for quick 
coding help its ok. 

![Chat window](readme_images/chat_window_v1.png)
  

## Demo Video 

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
