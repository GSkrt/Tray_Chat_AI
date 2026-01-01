# Copyright (c) [current year], Gregor Skrt. All rights reserved.
#
__author__ = "Gregor Skrt"
__email__ = "gregor.skrt@gmail.com"


import sys
import subprocess
import re
import html # Keep html import as it's used in chat display
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QFileDialog, QMessageBox, QInputDialog, QStyle, QAction, QDialog, QVBoxLayout, QTextEdit, QPushButton, QListWidget, QListWidgetItem, QLabel, QHBoxLayout, QWidget, QAbstractItemView, QLineEdit
from PyQt5 import QtGui, QtCore
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QTimer, QProcess # Import QProcess
import os
import logging
import logging.handlers 

from docker import DockerClient, errors as docker_errors
import json


class LlmTrayManager:
    def __init__(self):
        
        self.check_timer_interval = 5000  # in milliseconds
        
        # Determine paths for packaging compatibility
        # 1. Base dir for static assets (images) relative to the script location
        self.base_dir = os.path.dirname(os.path.abspath(__file__)) # This will be the installed script location
        
        # Logic to find images:
        # 1. Check relative to script (Development / Manual install) - this might not be ideal for installed packages
        local_image_path = os.path.join(self.base_dir, "images")
        # 2. Check standard system path (Debian/Ubuntu install)
        system_image_path = "/usr/share/llm-tray-manager/images"
        
        if os.path.exists(local_image_path):
            self.image_dir = local_image_path
        else:
            self.image_dir = system_image_path
        
        # 2. User data dir for writable files (settings, logs) in user's home, consistent with new name
        self.user_data_dir = os.path.join(os.path.expanduser("~"), ".config", "llm_tray_manager")
        if not os.path.exists(self.user_data_dir):
            os.makedirs(self.user_data_dir)
            
        # Path for the autostart .desktop file, consistent with new name
        self.autostart_file = os.path.join(os.path.expanduser("~"), ".config", "autostart", "llm-tray-manager.desktop")

        # set up logging for the app 
        logger = logging.getLogger("LlmTrayManager")
        logger.setLevel(logging.INFO)
        
        # set path for log directory
        log_dir = os.path.join(self.user_data_dir, "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # configure rotating file handler, consistent with new name
        log_file_path = os.path.join(log_dir, 'LlmTrayManager.log')
        logger_handler = logging.handlers.RotatingFileHandler(log_file_path, maxBytes = 1024*1024, backupCount=5)
        logger_handler.setFormatter(logging.Formatter('%(asctime)s: %(levelname)s - %(message)s'))
        logger.addHandler(logger_handler)
        
        # load settings from settings.json (if exists) otherwise create one with default values
        settings_json = self.read_settings()
        self.docker_image_name = settings_json.get('ollama_container_name', 'ollama') # default to 'ollama' if not set
        self.docker_compose_path = settings_json.get('docker_compose_path', None)
        self.selected_ollama_model = settings_json.get('selected_ollama_model', None)
        self.save_settings(settings_json)
        
        self.docker_client = None
        self.docker_available = False
        try:
            self.docker_client = DockerClient.from_env()
            self.docker_client.ping() # A simple operation to confirm connection
            self.docker_available = True
        except (docker_errors.DockerException, FileNotFoundError) as e:
            if isinstance(e, FileNotFoundError): # This is a generic Docker error, not specific to Ollama
                logging.error("Docker command not found. Is Docker installed and in PATH?")
                self.show_status_message("Docker Error", "Docker command not found. Please ensure Docker is installed and in your system PATH.", 10000)
            else:
                logging.error(f"Docker daemon not available or Docker not installed: {e}")
                self.show_status_message("Docker Error", "Docker daemon not running or Docker not installed. Please ensure Docker is running.", 10000)
        except Exception as e:
            logging.error(f"An unexpected error occurred while checking Docker availability: {e}")
            self.show_status_message("Docker Error", f"An unexpected error occurred while checking Docker: {e}", 10000)


        self.app = QApplication(sys.argv)
        # Prevents the app from closing when there is no main window
        self.app.setQuitOnLastWindowClosed(False)

        # 1. Create the Tray Icon
        self.tray = QSystemTrayIcon()
        icon_path = os.path.join(self.image_dir, "llm_tray_default.png")
        icon = QIcon(icon_path)  # Replace with your icon path
        self.tray.setIcon(icon)
        self.tray.setVisible(True)

        # 2. Create the Menu
        self.menu = QMenu() # Menu items remain Ollama-specific as the functionality is Ollama-specific
        
        
        # add option to send prompt to ollama and show result in dialog
        self.send_prompt_action = QAction("Chat with selected LLM Model")
        # add chat icon from image folder 
        chat_icon_path = os.path.join(self.image_dir, "llm_chat_window_icon.png")
        chat_icon = QIcon(chat_icon_path)  # Replace with your icon path
        
        self.send_prompt_action.setIcon(chat_icon)
        self.send_prompt_action.triggered.connect(self.open_window_send_prompt_and_show_result_in_dialog)
        self.menu.addAction(self.send_prompt_action)
        
        self.status_action = QAction("Checking status...")
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)

        self.menu.addSeparator()

        self.start_action = QAction("Start LLM Server")
        start_icon = QApplication.style().standardIcon(QStyle.SP_MediaPlay)
        self.start_action.setIcon(start_icon)
        self.start_action.triggered.connect(self.start_container)
        self.menu.addAction(self.start_action)

        self.stop_action = QAction("Stop LLM Server")
        stop_icon = QApplication.style().standardIcon(QStyle.SP_MediaStop)
        self.stop_action.setIcon(stop_icon)
        self.stop_action.triggered.connect(self.stop_container)
        self.menu.addAction(self.stop_action)
        
        self.menu.addSeparator()

        self.choose_docker_compose_file_action = QAction("Set Docker Compose File")
        self.choose_docker_compose_file_action.triggered.connect(self.choose_docker_compose_file)
        self.menu.addAction(self.choose_docker_compose_file_action)

        
        self.menu.addSeparator()
        
        # add option to select ollama model from available models
        self.choose_ollama_model_action = QAction("Select LLM Model")
        self.choose_ollama_model_action.triggered.connect(self.choose_ollama_model)
        self.menu.addAction(self.choose_ollama_model_action)
        
        # New action for pulling models
        self.pull_model_action = QAction("Pull LLM Model")
        self.pull_model_action.triggered.connect(self.open_pull_model_dialog)
        self.menu.addAction(self.pull_model_action)
        self.menu.addSeparator()
        
        
        
        
        self.menu.addSeparator()

        self.choose_running_docker_image_as_ollama = QAction("Choose Running Docker Image for LLM Server")
        self.choose_running_docker_image_as_ollama.triggered.connect(self.choose_from_running_docker_images)
        self.menu.addAction(self.choose_running_docker_image_as_ollama)
        
        self.menu.addSeparator()
        
        self.autostart_action = QAction("Run on Startup")
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(os.path.exists(self.autostart_file))
        self.autostart_action.triggered.connect(self.toggle_autostart)
        self.menu.addAction(self.autostart_action)

       
        self.menu.addSeparator()
        
        self.quit_action = QAction("Quit")
        self.quit_action.triggered.connect(self.app.quit)
        self.menu.addAction(self.quit_action)

        self.menu.addSeparator()

        self.tray.setContextMenu(self.menu)

        # 3. Setup a Timer to check status every 5 seconds
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status)
        self.timer.start(self.check_timer_interval)  # Check every 5 seconds
        self.update_status()

        # Disable Docker-related actions if Docker is not available
        if not self.docker_available:
            self.start_action.setEnabled(False)
            self.stop_action.setEnabled(False)
            self.choose_docker_compose_file_action.setEnabled(False)
            self.choose_ollama_model_action.setEnabled(False)
            self.send_prompt_action.setEnabled(False)
            self.choose_running_docker_image_as_ollama.setEnabled(False)
            self.pull_model_action.setEnabled(False) # Disable pull model action
            self.status_action.setText("Ollama: Docker Not Available")
            # Set a default icon indicating no docker, using the new generic error icon
            error_icon_path = os.path.join(self.image_dir, "llm_tray_error.png")
            if os.path.exists(error_icon_path):
                self.tray.setIcon(QIcon(error_icon_path))
            else:
                self.tray.setIcon(QIcon(os.path.join(self.image_dir, "llm_tray_default.png"))) # Fallback to default icon
            self.timer.stop() # No need to check status if Docker is not available
        
        
       
        
    def change_timer_interval_input(self): 
        interval, ok = QInputDialog.getInt(None, "Set Status Check Interval", "Enter interval in seconds:", self.check_timer_interval, 1000, 60000, 1000)
        if ok:
            self.check_timer_interval = interval*1000 # convert to milliseconds
            self.timer.setInterval(self.check_timer_interval)
            self.show_status_message("Interval Updated", f"Status check interval set to {(self.check_timer_interval/1000)} s.")
            
    
        
    def show_status_message(self, title, message, duration=3000):
        self.tray.showMessage(title, message, QSystemTrayIcon.Information, duration)
        
        
    def open_window_send_prompt_and_show_result_in_dialog(self):
        # Create a dialog window for sending prompts
        dialog = QDialog() # This dialog is for chatting with an LLM model
        dialog.setWindowTitle("Chat with LLM model: " + (self.selected_ollama_model if self.selected_ollama_model else "No model selected"))
        layout = QVBoxLayout()
        # add resize to maximum button to dialog 
        dialog.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowMinMaxButtonsHint | QtCore.Qt.WindowCloseButtonHint)
        
    
        
        # initial size of the chat dialog
        dialog.resize(600, 600)
        
        # first call function to sellect ollama model if not selected yet 
        if not self.selected_ollama_model:
            self.choose_ollama_model()
        
        font = QtGui.QFont()
        font.setPointSize(12)
        
        # Chat Display (History)
        chat_display = QListWidget()
        chat_display.setStyleSheet("QListWidget { background-color: #ECE5DD; border: none; }")
        chat_display.setSelectionMode(QAbstractItemView.NoSelection)
        
        # Handle resize to update bubble widths dynamically
        def chat_resize_event(event):
            QListWidget.resizeEvent(chat_display, event)
            new_max_width = int((event.size().width() - 50) * 0.85)
            for i in range(chat_display.count()):
                item = chat_display.item(i)
                widget = chat_display.itemWidget(item)
                if widget:
                    label = widget.findChild(QLabel)
                    if label:
                        label.setMaximumWidth(new_max_width)
                        widget.layout().activate()
                        widget.adjustSize()
                        item.setSizeHint(widget.sizeHint())
            chat_display.doItemsLayout()
        chat_display.resizeEvent = chat_resize_event
        
        layout.addWidget(chat_display)
        
        # Input Area
        prompt_input = QTextEdit()
        prompt_input.setFont(font)
        prompt_input.setMaximumHeight(100)
        prompt_input.setPlaceholderText("Type your message here... (Press Enter to send)")
        layout.addWidget(prompt_input)

        send_button = QPushButton("Send")
        
        # Initialize chat history for this session
        dialog.chat_history = []
        
        # Handle Enter key to send
        def keyPressEvent(event):
            if event.key() == QtCore.Qt.Key_Return and not (event.modifiers() & QtCore.Qt.ShiftModifier):
                send_button.click()
            else:
                QTextEdit.keyPressEvent(prompt_input, event)
        prompt_input.keyPressEvent = keyPressEvent
        
        send_button.clicked.connect(lambda: self.send_prompt_and_show_result(prompt_input, chat_display, dialog))
        layout.addWidget(send_button)

        dialog.setLayout(layout)
        dialog.exec_()

    def send_prompt_and_show_result(self, prompt_input, chat_display, dialog):
        prompt = prompt_input.toPlainText().strip()
        if not prompt:
            return

        def add_bubble(text, role):
            item = QListWidgetItem()
            widget = QWidget()
            layout = QHBoxLayout()
            
            # Normalize newlines
            text = text.replace("\r\n", "\n")
            
            parts = re.split(r'(```.*?```)', text, flags=re.DOTALL)
            final_html_parts = []
            
            for part in parts:
                if part.startswith("```") and part.endswith("```"):
                    content = part[3:-3]
                    # Remove language identifier if present
                    match = re.match(r'^\s*([a-zA-Z0-9+\-#]+)\n', content)
                    if match:
                        content = content[match.end():]
                    
                    escaped_content = html.escape(content, quote=False)
                    # Use table for background color support in QLabel rich text
                    code_html = f'<br><table border="0" cellpadding="10" bgcolor="#2b2b2b" width="100%"><tr><td><pre style="color: #f8f8f2;">{escaped_content}</pre></td></tr></table><br>'
                    final_html_parts.append(code_html)
                else:
                    # Heuristic: If Assistant response looks like hard-wrapped text (and not code), unwrap it.
                    if role == "Assistant" and "```" not in text:
                        part = part.replace("\n\n", "[[PARAGRAPH]]").replace("\n", " ").replace("[[PARAGRAPH]]", "\n\n")
                    
                    escaped_part = html.escape(part, quote=False).replace("\n", "<br>")
                    if role == "Assistant":
                        escaped_part = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', escaped_part)
                    final_html_parts.append(escaped_part)
            
            final_html = "".join(final_html_parts)
            
            
            # set qlabel width as percentage of chat display width make sure this works on resize too
            
            current_width = chat_display.width()
            if chat_display.viewport().width() > 0:
                current_width = chat_display.viewport().width()
            
            label_width = int((current_width - 50) * 0.85) 
            label = QLabel(final_html)
            label.setWordWrap(True)
            label.setMaximumWidth(label_width) 
            label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            label.setOpenExternalLinks(True)
            
            if role == "User":
                label.setStyleSheet("background-color: #DCF8C6; color: black; border-radius: 10px; padding: 10px; font-size: 12pt;")
                layout.addStretch()
                layout.addWidget(label)
            else:
                label.setStyleSheet("background-color: #FFFFFF; color: black; border-radius: 10px; padding: 10px; font-size: 12pt;")
                layout.addWidget(label)
                layout.addStretch()
            
            layout.setContentsMargins(10, 5, 10, 5)
            widget.setLayout(layout)
            item.setSizeHint(widget.sizeHint())
            chat_display.addItem(item)
            chat_display.setItemWidget(item, widget)
            chat_display.scrollToBottom()

        # Display User Message
        add_bubble(prompt, "User")
        
        prompt_input.clear()
        QApplication.processEvents()

        # Construct Contextual Prompt
        full_prompt = ""
        for msg in dialog.chat_history:
            full_prompt += f"{msg['role']}: {msg['content']}\n"
        full_prompt += f"User: {prompt}\nAssistant:"

        QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            result = self.send_promt_to_ollama(full_prompt)
        finally:
            QApplication.restoreOverrideCursor()

        if result:
            # Display LLM Response (this is generic)
            add_bubble(result, "Assistant")
            
            # Update History
            dialog.chat_history.append({"role": "User", "content": prompt})
            dialog.chat_history.append({"role": "Assistant", "content": result.strip()})
            
            return result 
        else:
            add_bubble("Error: Failed to get response.", "Assistant")
            return None

    def send_promt_to_ollama(self, prompt):
        """Sends a prompt to the LLM server (Ollama container) via docker python package. This method is Ollama-specific."""
        if not self.docker_available:
            self.show_status_message("Error", "Docker is not available. Cannot send prompt.", 5000)
            return "Error: Docker is not available."
        try:
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            client = self.docker_client
            container = client.containers.get(self.docker_image_name)
            if container.status == "running":
                # Execute the ollama command inside the container (this is Ollama-specific)
                # use selected ollama model if set (this is specific to Ollama's internal command)
                if not self.selected_ollama_model:
                    self.show_status_message("Error", "No LLM model selected. Please select one first.", 5000)
                    return "Error: No model selected. Please select a model."

                # Use subprocess to pipe input to stdin, avoiding shell quoting issues
                cmd = ["docker", "exec", "-i", self.docker_image_name, "ollama", "run", self.selected_ollama_model]
                result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, check=True) # -i is needed for piping input
                return ansi_escape.sub('', result.stdout) # Clean ANSI escape codes from output
            else:
                logging.error("LLM server container (Ollama) is not running.")
                self.show_status_message("Error", "LLM server container is not running. Please start it first.", 5000)
                return "Error: LLM server container is not running."
        except FileNotFoundError:
            logging.error("Docker command not found when sending prompt. Is Docker installed and in PATH?")
            self.show_status_message("Error", "Docker command not found. Please ensure Docker is installed.", 5000)
            return "Error: Docker command not found."
        except docker_errors.NotFound:
            logging.error(f"LLM server container (Ollama) '{self.docker_image_name}' not found. Cannot send prompt.") # This error is Ollama-specific
            self.show_status_message("Error", f"LLM server container '{self.docker_image_name}' not found. Please check the container name.", 5000)
            return "Error: LLM server container not found."
        except docker_errors.APIError as e:
            logging.error(f"Docker API error when sending prompt: {e}")
            self.show_status_message("Docker Error", f"Failed to send prompt due to Docker API error: {e}", 5000)
            return f"Error: Docker API error: {e}"
        except subprocess.CalledProcessError as e:
            cleaned_stderr = ansi_escape.sub('', e.stderr)
            logging.error(f"Error executing ollama command in container: {cleaned_stderr}") # This error is Ollama-specific
            self.show_status_message("LLM Server Command Error", f"Error in LLM server command: {cleaned_stderr}", 5000)
            return f"Error: LLM server command failed: {cleaned_stderr}"
        except Exception as e:
            logging.error(f"An unexpected error occurred when sending prompt: {e}")
            self.show_status_message("Error", f"An unexpected error occurred: {e}", 5000)
            return f"Error: An unexpected error occurred: {e}"
        
    def list_ollama_models(self):
        """Lists available LLM models (Ollama) by querying the container. This method is Ollama-specific."""
        if not self.docker_available:
            self.show_status_message("Error", "Docker is not available. Cannot list models.", 5000)
            return None
        try:
            client = self.docker_client
            container = client.containers.get(self.docker_image_name)
            if container.status == "running":
                exec_result = container.exec_run("ollama list", stdout=True, stderr=True) # This command is Ollama-specific
                if exec_result.exit_code == 0:
                    output = exec_result.output.decode('utf-8')
                    return output
                else:
                    error_output = exec_result.output.decode('utf-8')
                    logging.error(f"Ollama list command failed in container: {error_output}") # This error is Ollama-specific
                    self.show_status_message("LLM Server Error", f"Failed to list models: {error_output}", 5000)
                    return None
            else:
                logging.error("LLM server container (Ollama) is not running.")
                self.show_status_message("Error", "LLM server container is not running. Please start it first.", 5000)
                return None
        except docker_errors.NotFound:
            logging.error(f"LLM server container (Ollama) '{self.docker_image_name}' not found. Cannot list models.") # This error is Ollama-specific
            self.show_status_message("Error", f"LLM server container '{self.docker_image_name}' not found. Please check the container name.", 5000)
            return None
        except docker_errors.APIError as e:
            logging.error(f"Docker API error when listing models: {e}")
            self.show_status_message("Docker Error", f"Failed to list models due to Docker API error: {e}", 5000)
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred when listing LLM models (Ollama): {e}")
            return None
        
    def choose_ollama_model(self):
        # Placeholder for choosing LLM model (Ollama) from available models. This method is Ollama-specific.
        models_output = self.list_ollama_models()
        if models_output:
            models = [line.split()[0] for line in models_output.splitlines() if line]
            item, ok = QInputDialog.getItem(None, "Select Ollama Model", "Available Models:", models, 0, False) # 0 is default index
            if ok and item:
                QMessageBox.information(None, "Model Selected", f"You selected: {item}")
                self.selected_ollama_model = item
                
                # store selected model in settings to persist between sessions
                settings = self.read_settings()
                settings['selected_ollama_model'] = item
                self.save_settings(settings)
                
                # add menu text to show selected model, show it in bold 
                self.choose_ollama_model_action.setText(f"Select LLM Model (Selected: {item})")
                
        else:
            QMessageBox.warning(None, "No Models", "Could not retrieve LLM models.")
        
    def open_pull_model_dialog(self):
        # This dialog is for pulling Ollama models, so some "Ollama" references remain. This method is Ollama-specific.
        if not self.docker_available:
            self.show_status_message("Error", "Docker is not available. Cannot pull models.", 5000)
            return
        
        try:
            client = self.docker_client
            container = client.containers.get(self.docker_image_name)
            if container.status != "running":
                self.show_status_message("Error", "LLM server container is not running. Please start it first to pull models.", 5000)
                return
        except docker_errors.NotFound:
            self.show_status_message("Error", f"Ollama container '{self.docker_image_name}' not found. Please check the container name.", 5000)
            return
        except docker_errors.APIError as e:
            self.show_status_message("Docker Error", f"Failed to check Ollama container status: {e}", 5000)
            return
        except Exception as e:
            self.show_status_message("Error", f"An unexpected error occurred: {e}", 5000)
            return

        dialog_pull_model = QDialog()
        dialog_pull_model.setWindowTitle("Pull Ollama Model")
        dialog_pull_model.resize(500, 400)
        layout = QVBoxLayout()

        model_label = QLabel("Enter model name (e.g., 'llama2', 'mistral'):")
        layout.addWidget(model_label)

        model_input = QLineEdit()
        model_input.setPlaceholderText("e.g., llama2:7b-chat")
        layout.addWidget(model_input)

        pull_button = QPushButton("Pull Model")
        layout.addWidget(pull_button)

        output_text_edit = QTextEdit()
        output_text_edit.setReadOnly(True)
        layout.addWidget(output_text_edit)
        
        # Progress bar (optional, as ollama pull output is text-based)
        # For now, we'll just show the text output. A true progress bar
        # would require parsing the percentage from the output lines.
        # progress_bar = QProgressBar()
        # progress_bar.setRange(0, 100)
        # progress_bar.setValue(0)
        # layout.addWidget(progress_bar)

        dialog_pull_model.setLayout(layout)

        # Store references to widgets in the dialog for access by slots
        dialog_pull_model.model_input = model_input
        dialog_pull_model.pull_button = pull_button
        dialog_pull_model.output_text_edit = output_text_edit
        # dialog.progress_bar = progress_bar # if using progress bar

        # QProcess instance for the pull operation
        dialog_pull_model.pull_process = QProcess(dialog_pull_model)
        dialog_pull_model.pull_process.readyReadStandardOutput.connect(lambda: self._append_process_output(dialog_pull_model.output_text_edit, dialog_pull_model.pull_process.readAllStandardOutput().data().decode()))
        dialog_pull_model.pull_process.readyReadStandardError.connect(lambda: self._append_process_output(dialog_pull_model.output_text_edit, dialog_pull_model.pull_process.readAllStandardError().data().decode()))
        dialog_pull_model.pull_process.finished.connect(lambda exitCode, exitStatus: self._pull_process_finished(dialog_pull_model, exitCode, exitStatus))
        dialog_pull_model.pull_process.errorOccurred.connect(lambda error: self._pull_process_error(dialog_pull_model, error))

        pull_button.clicked.connect(lambda: self._start_pull_process(dialog_pull_model))

        dialog_pull_model.exec_()

    def _append_process_output(self, text_edit, output):
        text_edit.append(output.strip())
        # Optional: parse output for progress bar update
        # For example: if "pulling ... (XX%)" in output, update progress_bar.setValue(XX)

    def _start_pull_process(self, dialog):
        """Starts pull process for ollama LLMs. This method is Ollama-specific.

        Args:
            dialog (_type_): Dialog reference for outputing text messages
        """
        model_name = dialog.model_input.text().strip()
        if not model_name:
            dialog.output_text_edit.append("Error: Please enter a model name.")
            self.show_status_message("Error", "Please enter a model name to pull.", 3000)
            return

        dialog.output_text_edit.clear()
        dialog.output_text_edit.append(f"Attempting to pull model: {model_name}...")
        dialog.pull_button.setEnabled(False)
        dialog.model_input.setEnabled(False)
        # dialog.progress_bar.setValue(0) # if using progress bar

        command = ["docker", "exec", self.docker_image_name, "ollama", "pull", model_name]
        logging.info(f"Executing command: {' '.join(command)}")
        
        try: # This command is Ollama-specific
            dialog.pull_process.start(command[0], command[1:])
        except Exception as e:
            logging.error(f"Failed to start QProcess for pulling model: {e}")
            dialog.output_text_edit.append(f"Error: Failed to start the pull process. {e}")
            self.show_status_message("Error", f"Failed to start pull process: {e}", 5000)
            dialog.pull_button.setEnabled(True)
            dialog.model_input.setEnabled(True)


    def _pull_process_finished(self, dialog, exitCode, exitStatus):
        dialog.pull_button.setEnabled(True)
        dialog.model_input.setEnabled(True)
        # dialog.progress_bar.setValue(100) # if using progress bar

        if exitCode == 0:
            dialog.output_text_edit.append("\nModel pull completed successfully!")
            self.show_status_message("LLM Model", f"Model '{dialog.model_input.text()}' pulled successfully.", 5000)
            # After pulling, it might be good to refresh the model list
            self.update_status() # This will re-enable model selection if it was disabled
        else: # This error is for Ollama pull
            dialog.output_text_edit.append(f"\nModel pull failed with exit code {exitCode}.")
            self.show_status_message("LLM Model Error", f"Failed to pull model '{dialog.model_input.text()}'. Check output for details.", 5000)
        logging.info(f"Ollama pull process finished. Exit code: {exitCode}, Exit status: {exitStatus}")

    def _pull_process_error(self, dialog, error):
        """ Handles errors durring LLM installation and updates the dialog accordingly. This method is Ollama-specific.

        Args:
            dialog (_type_): Dialog reference for outputing text messages
            error (_type_): Error that happend durring download session
        """
        dialog.pull_button.setEnabled(True)
        dialog.model_input.setEnabled(True)
        # dialog.progress_bar.setValue(0) # if using progress bar
        error_message = ""
        if error == QProcess.FailedToStart:
            error_message = "Failed to start the Docker command. Is Docker installed and in your PATH?"
        elif error == QProcess.Crashed:
            error_message = "The Docker command crashed."
        elif error == QProcess.Timedout:
            error_message = "The Docker command timed out."
        else:
            error_message = f"An unknown QProcess error occurred: {error}"
        
        dialog.output_text_edit.append(f"\nError: {error_message}")
        logging.error(f"QProcess error during model pull: {error_message}")
        self.show_status_message("LLM Model Pull Error", f"Error during model pull: {error_message}", 5000)


    

    def update_status(self):
        """Runs a shell command to check if the LLM server (Ollama) container is running. This method is Ollama-specific."""
        if not self.docker_available:
            self.status_action.setText("LLM Server: Docker Not Available")
            self.start_action.setEnabled(False)
            self.stop_action.setEnabled(False)
            self.choose_ollama_model_action.setEnabled(False)
            self.send_prompt_action.setEnabled(False)
            self.pull_model_action.setEnabled(False) # Disable pull model action
            # Icon already set in __init__
            return

        try:
            # Check if the LLM server container (Ollama) is running (this is Ollama-specific)
            # Using subprocess.run for docker inspect as it's a direct command execution
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}|{{.HostConfig.Runtime}}|{{json .HostConfig.DeviceRequests}}", self.docker_image_name],
                capture_output=True, text=True
            )
            
            # parse output to get status of ollama container (Ollama specific)
            output = result.stdout.strip().split("|")
            is_running = output[0] == "true"
            runtime = output[1] if len(output) > 1 else ""
            device_requests = output[2] if len(output) > 2 else "null"
            
            if is_running:
                mode = "CPU"
                # Check if runtime is nvidia or if there are GPU device requests
                if runtime == "nvidia" or (device_requests != "null" and "gpu" in device_requests.lower()): # This check is Ollama-specific
                    mode = "GPU 🚀"
                    # update tray icon image to show gpu mode
                    gpu_icon_path = os.path.join(self.image_dir, "llm_tray_gpu_running.png")
                    self.tray.setIcon(QIcon(gpu_icon_path))
                    self.start_action.setEnabled(True) # Re-enable if it was disabled due to a previous error
                    self.stop_action.setEnabled(True)
                else: # This is for CPU mode
                    default_icon_path = os.path.join(self.image_dir, "llm_tray_cpu_running.png")
                    self.tray.setIcon(QIcon(default_icon_path))
                    
                self.status_action.setText(f"Ollama: Running ({mode})")
                # You could change the icon here too: self.tray.setIcon(QIcon("green.png"))
                self.start_action.setVisible(False)
                self.stop_action.setVisible(True)
                
                self.choose_ollama_model_action.setEnabled(True)
                self.send_prompt_action.setEnabled(True)
                self.pull_model_action.setEnabled(True) # Enable pull model action if container is running
            else:
                # set tray icon to not running 
                not_running_icon_path = os.path.join(self.image_dir, "llm_tray_not_running.png")
                self.tray.setIcon(QIcon(not_running_icon_path))
                
                # change icon to show stopped status
                self.status_action.setText("LLM Server: Stopped ❌")
                self.start_action.setVisible(True)
                self.stop_action.setVisible(False)
                
                # disable actions that require running container
                self.start_action.setEnabled(True)
                self.stop_action.setEnabled(False) # Cannot stop if not found or not running
                self.choose_ollama_model_action.setEnabled(False) # Cannot choose model if not running
                self.send_prompt_action.setEnabled(False) # Cannot send prompt if not running
                self.pull_model_action.setEnabled(False) # Disable pull model action if container is not running
                
        except FileNotFoundError:
            logging.error("Docker command not found during status update. Is Docker installed and in PATH?")
            self.status_action.setText("LLM Server: Docker Command Not Found") # This status is generic
            self.start_action.setEnabled(False)
            self.stop_action.setEnabled(False)
            self.choose_ollama_model_action.setEnabled(False)
            self.send_prompt_action.setEnabled(False)
            self.pull_model_action.setEnabled(False) # Disable pull model action
            self.tray.setIcon(QIcon(os.path.join(self.image_dir, "llm_tray_error.png")))
            self.docker_available = False # Mark as unavailable (this is generic)
        except subprocess.CalledProcessError as e:
            # This happens if 'docker inspect' fails, e.g., container not found
            logging.warning(f"LLM server container (Ollama) '{self.docker_image_name}' not found or docker inspect failed: {e.stderr.strip()}") # This warning is Ollama-specific
            self.status_action.setText("LLM Server: Not Found")
            self.start_action.setVisible(True)
            self.stop_action.setVisible(False)
            self.start_action.setEnabled(True)
            self.stop_action.setEnabled(False) # Cannot stop if not found
            self.choose_ollama_model_action.setEnabled(False)
            self.pull_model_action.setEnabled(False) # Disable pull model action
            self.send_prompt_action.setEnabled(False)
            not_running_icon_path = os.path.join(self.image_dir, "llm_tray_not_running.png")
            self.tray.setIcon(QIcon(not_running_icon_path))
        except docker_errors.DockerException as e: # This is a generic Docker error
            logging.error(f"Docker daemon not available during status update: {e}") # This error is generic
            self.status_action.setText("LLM Server: Docker Daemon Down")
            self.start_action.setEnabled(False)
            self.stop_action.setEnabled(False)
            self.choose_ollama_model_action.setEnabled(False)
            self.send_prompt_action.setEnabled(False)
            self.pull_model_action.setEnabled(False) # Disable pull model action
            self.tray.setIcon(QIcon(os.path.join(self.image_dir, "llm_tray_error.png")))
            self.docker_available = False # Mark as unavailable (this is generic)
        except Exception as e:
            logging.error(f"An unexpected error occurred during status update: {e}") # This error is generic
            self.status_action.setText("LLM Server: Error")
            self.start_action.setEnabled(False)
            self.stop_action.setEnabled(False)
            self.choose_ollama_model_action.setEnabled(False)
            self.pull_model_action.setEnabled(False) # Disable pull model action
            self.send_prompt_action.setEnabled(False)
            self.tray.setIcon(QIcon(os.path.join(self.image_dir, "llm_tray_error.png"))) # This icon is for error
            
    def choose_from_running_docker_images(self):
        # List running docker containers and let user choose one to set as LLM server (Ollama). This method is Ollama-specific.
        if not self.docker_available:
            self.show_status_message("Error", "Docker is not available. Cannot list containers.", 5000)
            return
        try:
            containers = self.docker_client.containers.list()
            container_names = [container.name for container in containers]

            if not container_names:
                QMessageBox.information(None, "No Running Containers", "There are no running Docker containers.")
                return
            # docker container name in case it's different as usual (ollama)
            item, ok = QInputDialog.getItem(None, "Select Docker Container", "Running Containers:", container_names, 0, False) # This dialog is generic
            if ok and item:
                # Here you would store the selected container name and use it in start/stop methods
                QMessageBox.information(None, "Container Selected", f"You selected: {item}")
                
                # store selected container name in settings to persist between sessions
                settings = self.read_settings()
                settings['ollama_container_name'] = item 
                self.docker_image_name = item
                self.save_settings(settings)
                self.update_status()
        except docker_errors.APIError as e:
            logging.error(f"Docker API error when choosing Docker image: {e}")
            QMessageBox.critical(None, "Docker Error", f"An error occurred while accessing Docker API: {e}")
        except docker_errors.DockerException as e:
            logging.error(f"Docker error: {e}")
            QMessageBox.critical(None, "Docker Error", f"An error occurred while accessing Docker: {e}")
            
    def choose_docker_compose_file(self):
        # Placeholder for file dialog to choose docker compose file (this might be usufull for specific Ollama setups). This method is Ollama-specific.

        # get users home directory, use it as start path it should be working on windows mac and linux too...
        home = os.path.expanduser("~") # This is a generic path for home folder
        file_manager_string = "Select docker-compose.yml file to start and stop Ollama container"
        file_path, selected_filter = QFileDialog.getOpenFileName(None, file_manager_string, home, "YAML Files (*.yml);;All Files (*)")
        
        settings_json = self.read_settings()
        settings_json['docker_compose_path'] = file_path
        self.docker_compose_path = file_path
        self.save_settings(settings_json)
        if file_path:
            QMessageBox.information(None, "File Selected", f"You selected: {file_path}\n) ")
            # Here you would store the selected file path and use it in start/stop methods
            
        else:
            print("No file selected.")
            

    def read_settings(self):
        try:
            settings_path = os.path.join(self.user_data_dir, "settings.json")
            if not os.path.exists(settings_path):
                # File doesn't exist, return empty settings. It will be created on first save.
                return {}
            with open(settings_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logging.error(f"Failed to decode settings.json: {e}. Returning empty settings.")
            return {}
        except Exception as e:
            logging.error(f"An unexpected error occurred while reading settings: {e}. Returning empty settings.")
            return {}
        
    def save_settings(self, settings):
        try:
            settings_path = os.path.join(self.user_data_dir, "settings.json")
            with open(settings_path, "w") as f:
                json.dump(settings, f)
        except Exception as e:
            logging.error(f"Failed to save settings: {e}")
    
    
    def start_container(self):
        """""Starts the LLM server (Ollama) Docker container. This method is Ollama-specific.
        """
        if not self.docker_available:
            self.show_status_message("Error", "Docker is not available. Cannot start LLM server.", 5000)
            return

        # Start the LLM server (Ollama) Docker container using docker compose file or docker command. This method is Ollama-specific.
        if self.docker_compose_path and os.path.exists(self.docker_compose_path):
            dir_path = os.path.dirname(self.docker_compose_path)
            try: # Use 'docker compose' instead of 'docker-compose'
                subprocess.run(["docker", "compose", "-f", self.docker_compose_path, "up", "-d"], cwd=dir_path, check=True)
                self.show_status_message("LLM Server Started", "LLM server container started via Docker Compose.") # This message is generic
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to start LLM server container (Ollama) with Docker Compose: {e}") # This error is Ollama-specific
                self.show_status_message("Error", f"Failed to start LLM server with Docker Compose: {e}", 5000)
            except FileNotFoundError:
                logging.error("Docker command not found. Is Docker installed and in PATH?")
                self.show_status_message("Error", "Docker command not found. Please ensure Docker is installed and in your system PATH.", 5000)
            except Exception as e:
                logging.error(f"An unexpected error occurred when starting Ollama container with Docker Compose: {e}")
                self.show_status_message("Error", f"An unexpected error occurred: {e}", 5000)
        else:
            # check for docker containers (that are not running) named ollama and start it
            try:
                client = self.docker_client
                container = client.containers.get(self.docker_image_name)
                if container.status != "running":
                    container.start()
                    self.show_status_message("LLM Server Started", f"LLM server container '{self.docker_image_name}' has been started.")
                else:
                    self.show_status_message("LLM Server Already Running", f"LLM server container '{self.docker_image_name}' is already running.")
            except docker_errors.NotFound:
                logging.error(f"LLM server container (Ollama) '{self.docker_image_name}' not found. Please ensure the container exists or the name is correct.") # This error is Ollama-specific
                self.show_status_message("Error", f"LLM server container '{self.docker_image_name}' not found. Please check the container name or create it.", 5000)
            except docker_errors.APIError as e:
                logging.error(f"Docker API error when starting container: {e}")
                self.show_status_message("Docker Error", f"Failed to start LLM server container due to Docker API error: {e}", 5000)
            except Exception as e:
                logging.error(f"An unexpected error occurred when starting LLM server container (Ollama): {e}") # This error is Ollama-specific
                self.show_status_message("Error", f"An unexpected error occurred: {e}", 5000)
            
        self.update_status()

    def stop_container(self):
        if not self.docker_available:
            self.show_status_message("Error", "Docker is not available. Cannot stop LLM server.", 5000)
            return # This message is generic
        # stop docker compose service or docker command. This method is Ollama-specific.
        if self.docker_compose_path and os.path.exists(self.docker_compose_path):
            dir_path = os.path.dirname(self.docker_compose_path)
            try: # Use 'docker compose' instead of 'docker-compose'
                subprocess.run(["docker", "compose", "-f", self.docker_compose_path, "down"], cwd=dir_path, check=True)
                self.show_status_message("LLM Server Stopped", "LLM server container stopped via Docker Compose.")
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to stop Ollama container with Docker Compose: {e}") # This error is Ollama-specific
                self.show_status_message("Error", f"Failed to stop Ollama with Docker Compose: {e}", 5000)
            except FileNotFoundError:
                logging.error("Docker command not found. Is Docker installed and in PATH?")
                self.show_status_message("Error", "Docker command not found. Please ensure Docker is installed and in your system PATH.", 5000)
            except Exception as e:
                logging.error(f"An unexpected error occurred when stopping Ollama container with Docker Compose: {e}")
                self.show_status_message("Error", f"An unexpected error occurred: {e}", 5000)
        else:
            try:
                client = self.docker_client
                container = client.containers.get(self.docker_image_name)
                if container.status == "running": # Only try to stop if it's running
                    container.stop()
                    self.show_status_message("LLM Server Stopped", f"LLM server container '{self.docker_image_name}' has been stopped.")
                else:
                    self.show_status_message("LLM Server Not Running", f"LLM server container '{self.docker_image_name}' is not running.")
            except docker_errors.NotFound:
                logging.error(f"LLM server container (Ollama) '{self.docker_image_name}' not found. Cannot stop a non-existent container.") # This error is Ollama-specific
                self.show_status_message("Error", f"LLM server container '{self.docker_image_name}' not found. Cannot stop it.", 5000)
            except docker_errors.APIError as e:
                logging.error(f"Docker API error when stopping container: {e}")
                self.show_status_message("Docker Error", f"Failed to stop LLM server container due to Docker API error: {e}", 5000)
            except Exception as e:
                logging.error(f"An unexpected error occurred when stopping LLM server container (Ollama): {e}") # This error is Ollama-specific
                self.show_status_message("Error", f"An unexpected error occurred: {e}", 5000)
        self.update_status()
        
    def toggle_autostart(self):
        if self.autostart_action.isChecked():
            autostart_dir = os.path.dirname(self.autostart_file)
            if not os.path.exists(autostart_dir):
                os.makedirs(autostart_dir)
            
            # Use the installed console script for Exec, and the installed image path for Icon
            exec_cmd = "llm-tray-manager" 
            icon_path = "/usr/share/llm-tray-manager/images/llm_tray_default.png"

            desktop_entry = f"""[Desktop Entry]
Type=Application
Name=LLM Tray Manager
Exec={exec_cmd}
Icon={icon_path}
Comment=Manage Ollama Docker Containers
Terminal=false
Categories=Utility;
StartupNotify=false
"""
            try:
                with open(self.autostart_file, "w") as f:
                    f.write(desktop_entry)
                self.show_status_message("Settings Saved", "Run on Startup enabled.")
                logging.info(f"Autostart file created in user's autostart directory. \n {desktop_entry}")
            except Exception as e:
                logging.error(f"Failed to write autostart file: {e}")
                self.autostart_action.setChecked(False)
        else:
            if os.path.exists(self.autostart_file):
                try:
                    os.remove(self.autostart_file)
                    self.show_status_message("Settings Saved", "Run on Startup disabled.")
                    logging.info(f"Autostart file removed from user's autostart directory {self.autostart_file}.")
                except Exception as e:
                    logging.error(f"Failed to remove autostart file: {e}")

    def run(self):
        sys.exit(self.app.exec())

def main():
    tray = LlmTrayManager()
    tray.run()

if __name__ == "__main__":
    main()