# Copyright (c) 2026, Gregor Skrt. All rights reserved.
#
__author__ = "Gregor Skrt"
__email__ = "gregor.skrt@gmail.com"


import sys
import subprocess
import re
import html # Keep html import as it's used in chat display
from PyQt5.QtWidgets import QApplication,QComboBox, QSystemTrayIcon, QMenu, QFileDialog, QMessageBox, QInputDialog, \
    QStyle, QAction, QDialog, QVBoxLayout, QTextEdit, QPushButton, QListWidget, \
        QListWidgetItem, QLabel, QHBoxLayout, QWidget, QAbstractItemView, QLineEdit, QShortcut
from PyQt5 import QtGui, QtCore
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QTimer, QProcess # Import QProcess
import os
import logging
import logging.handlers 
import docker
from docker import DockerClient, errors as docker_errors
import json


class TrayChatAIManager:
    def __init__(self):
        
        # Determine paths for packaging compatibility
        # 1. Check if running as PyInstaller bundle (frozen)
        if getattr(sys, 'frozen', False):
            self.base_dir = sys._MEIPASS
        else:
            # Base dir for static assets (images) relative to the script location
            self.base_dir = os.path.dirname(os.path.abspath(__file__)) # This will be the installed script location
        
        # Logic to find images:
        # 1. Check relative to script (Development / Manual install) - this might not be ideal for installed packages
        local_image_path = os.path.join(self.base_dir, "images")
        # 2. Check standard system path (Debian/Ubuntu install)
        system_image_path = "/usr/share/tray-chat-ai/images"
        
        if os.path.exists(local_image_path):
            self.image_dir = local_image_path
        else:
            self.image_dir = system_image_path
        
        # 2. User data dir for writable files (settings, logs) in user's home, consistent with new name
        self.user_data_dir = os.path.join(os.path.expanduser("~"), ".config", "tray_chat_ai")
        if not os.path.exists(self.user_data_dir):
            os.makedirs(self.user_data_dir)
            
        # Path for the autostart .desktop file, consistent with new name
        self.autostart_file = os.path.join(os.path.expanduser("~"), ".config", "autostart", "tray-chat-ai.desktop")

        # set up logging for the app 
        logger = logging.getLogger("TrayChatAI")
        logger.setLevel(logging.INFO)
        
        # set path for log directory
        log_dir = os.path.join(self.user_data_dir, "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # configure rotating file handler, consistent with new name
        log_file_path = os.path.join(log_dir, 'TrayChatAI.log')
        logger_handler = logging.handlers.RotatingFileHandler(log_file_path, maxBytes = 1024*1024, backupCount=5)
        logger_handler.setFormatter(logging.Formatter('%(asctime)s: %(levelname)s - %(message)s'))
        logger.addHandler(logger_handler)
        
        # load settings from settings.json (if exists) otherwise create one with default values
        settings_json = self.read_settings()
        self.docker_image_name = settings_json.get('ollama_container_name', 'ollama') # default to 'ollama' if not set
        self.docker_compose_path = settings_json.get('docker_compose_path', None)
        
        # Ensure selected_ollama_model is always a list
        raw_model = settings_json.get('selected_ollama_model', [])
        if isinstance(raw_model, str):
            self.selected_ollama_model = [raw_model]
        elif raw_model is None:
            self.selected_ollama_model = []
        else:
            self.selected_ollama_model = raw_model
            
        self.check_timer_interval = settings_json.get('status_check_interval', 5000) # default to 5000 ms
        settings_json['selected_ollama_model'] = self.selected_ollama_model
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
        icon_path = os.path.join(self.image_dir, "tray_chat_ai_default.png")
        icon = QIcon(icon_path)  # Replace with your icon path
        self.tray.setIcon(icon)
        self.tray.setToolTip("TrayChat AI")
        self.tray.setVisible(True)

        # 2. Create the Menu
        self.menu = QMenu() # Menu items remain Ollama-specific as the functionality is Ollama-specific
        
        
        # add option to send prompt to ollama and show result in dialog
        self.send_prompt_action = QAction("Chat with selected LLM Model")
        # add chat icon from image folder 
        chat_icon_path = os.path.join(self.image_dir, "tray_chat_ai_window_icon.png")
        chat_icon = QIcon(chat_icon_path)  # Replace with your icon path
        
        self.send_prompt_action.setIcon(chat_icon)
        self.send_prompt_action.triggered.connect(self.chat_dialog)
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
        
        # New action for pulling models
        self.pull_model_action = QAction("Pull LLM Model")
        self.pull_model_action.triggered.connect(self.open_pull_model_dialog)
        self.menu.addAction(self.pull_model_action)
        self.menu.addSeparator()
        
        # New action for removing models
        self.remove_model_action = QAction("Remove LLM Model")
        self.remove_model_action.triggered.connect(self.remove_language_model_dialog)
        self.menu.addAction(self.remove_model_action)
        self.menu.addSeparator()
        
        # change timer interval for status check
        self.change_timer_interval_action =QAction("Set Status Check Interval")
        self.change_timer_interval_action.triggered.connect(self.change_interval_timer_variable)
        self.menu.addAction(self.change_timer_interval_action)
        self.menu.addSeparator()

        # if running docker image is not called ollama select ollama from running docker images
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
        self.tray.activated.connect(self.start_chat_from_tray_icon)

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
            self.send_prompt_action.setEnabled(False)
            self.choose_running_docker_image_as_ollama.setEnabled(False)
            self.pull_model_action.setEnabled(False) # Disable pull model action
            self.status_action.setText("Ollama: Docker Not Available")
            # Set a default icon indicating no docker, using the new generic error icon
            error_icon_path = os.path.join(self.image_dir, "llm_tray_error.png")
            if os.path.exists(error_icon_path):
                self.tray.setIcon(QIcon(error_icon_path))
            else:
                self.tray.setIcon(QIcon(os.path.join(self.image_dir, "tray_chat_ai_default.png"))) # Fallback to default icon
            self.timer.stop() # No need to check status if Docker is not available
        
    def change_interval_timer_variable(self): 
        # show input dialog to change timer interval variable
        current_int_seconds = self.check_timer_interval // 1000
        interval, ok = QInputDialog.getInt(None, "Set Status Check Interval", "Enter interval in milliseconds:", current_int_seconds, 1, 60, 1)
        if ok:
            self.check_timer_interval = interval*1000 # convert to milliseconds
            self.timer.setInterval(self.check_timer_interval)
            self.show_status_message("Interval Updated", f"Status check interval set to {(self.check_timer_interval/1000)} s.")
            # save to settings
            settings = self.read_settings()
            settings['status_check_interval'] = self.check_timer_interval
            self.save_settings(settings)
        else:
            return
    
    
    def remove_language_model_dialog(self):
        # show dropdown dialog with available ollama models to remove one
        models_output = self.list_ollama_models()
        if models_output:
            models = [line.split()[0] for line in models_output.splitlines() if line.strip() and line.split()[0] != "NAME"]
            if not models:
                QMessageBox.information(None, "No Models", "No LLM models found to remove.")
                return

            item, ok = QInputDialog.getItem(None, "Remove LLM Model", "Select Model to Remove:", models, 0, False)
            if ok and item:
                reply = QMessageBox.question(None, "Confirm Removal",
                                             f"Are you sure you want to remove model '{item}'?",
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self.remove_language_model_from_ollama(item)
                    # Optionally, update the selected model if the removed one was selected
                    if self.selected_ollama_model and item in self.selected_ollama_model:
                        self.selected_ollama_model.remove(item)
                        settings = self.read_settings()
                        settings['selected_ollama_model'] = self.selected_ollama_model
                        self.save_settings(settings)
                    self.update_status() # Refresh status to reflect changes
        else:
            QMessageBox.warning(None, "No Models", "Could not retrieve LLM models to remove.")

    
    
    def remove_language_model_from_ollama(self, model_name):
        try:
            # Check if the model exists in Ollama
            client = self.docker_client
            container = client.containers.get(self.docker_image_name)
            if container.status == "running":
                exec_result = container.exec_run(f"ollama rm {model_name}", stdout=True, stderr=True)
                if exec_result.exit_code == 0:
                    output = exec_result.output.decode('utf-8')
                    self.show_status_message("Model Removed", f"Successfully removed model '{model_name}': {output}", 5000)
                else:
                    error_output = exec_result.output.decode('utf-8')
                    logging.error(f"Failed to remove model '{model_name}' in Ollama container: {error_output}")
                    self.show_status_message("Error", f"Failed to remove model '{model_name}': {error_output}", 5000)
        except docker.errors.NotFound as e:
            logging.error(f"Ollama container '{self.docker_image_name}' not found. Cannot remove model '{model_name}'.")
            self.show_status_message("Error", f"Ollama container '{self.docker_image_name}' not found. Cannot remove model.", 5000)
        except Exception as e:
            logging.error(f"An unexpected error occurred while removing model '{model_name}': {e}")
            self.show_status_message("Error", f"An unexpected error occurred: {e}", 5000)
    
    
    def start_chat_from_tray_icon(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            # Check if a modal dialog (like the chat window) is already open
            if QApplication.activeModalWidget():
                QApplication.activeModalWidget().activateWindow()
                # notify user that window is already open
                self.show_status_message("TrayChat AI", "Chat window is already open.", 5000)
                return

            if self.send_prompt_action.isEnabled():
                self.chat_dialog()
            else:
                self.show_status_message("TrayChat AI", "Please start the LLM Server first to chat.", 2000)   
       
        
    def change_timer_interval_input(self): 
        interval, ok = QInputDialog.getInt(None, "Set Status Check Interval", "Enter interval in seconds:", self.check_timer_interval, 1000, 60000, 1000)
        if ok:
            self.check_timer_interval = interval*1000 # convert to milliseconds
            self.timer.setInterval(self.check_timer_interval)
            self.show_status_message("Interval Updated", f"Status check interval set to {(self.check_timer_interval/1000)} s.")
            
    
        
    def show_status_message(self, title, message, duration=3000):
        self.tray.showMessage(title, message, QSystemTrayIcon.Information, duration)
        
        
    def _update_selected_model_from_chat_dialog(self, item=None):
        """Update model from dropdown in chat dialog."""
        model = self.model_combo_box.model()
        selected_models = []
        for i in range(model.rowCount()):
            if model.item(i).checkState() == QtCore.Qt.Checked:
                selected_models.append(model.item(i).text())
        
        # Ensure it is never empty if we have a selection (except on first run logic handled elsewhere)
        if selected_models:
            self.selected_ollama_model = selected_models

        if self.selected_ollama_model:
            model_name = ", ".join(self.selected_ollama_model)
        else:
            model_name = "No model selected"

        # store selected model in settings to persist between sessions
        settings = self.read_settings()
        settings['selected_ollama_model'] = self.selected_ollama_model
        self.save_settings(settings)
        
        # update menu text to show selected model
        display_name = model_name
        if len(display_name) > 30:
            display_name = display_name[:27] + "..."

        # update chat dialog title and displayed label
        active_dialog = QApplication.activeModalWidget()
        
        # find label inside the dialog and update it if dialog is open (use isinstance to check if it's QDialog instance and not subclass of QDialog)
        if active_dialog and isinstance(active_dialog, QDialog):
            active_dialog.setWindowTitle("Chat with LLM model: " + display_name)
            # also update the label inside the dialog : find item with text "Selected LLM Model:" and refresh it
            for i in range(active_dialog.layout().count()):
                item = active_dialog.layout().itemAt(i)
                widget = item.widget()
                if isinstance(widget, QLabel) and widget.text().startswith("Selected LLM Model(s):"):
                    widget.setText(f"Selected LLM Model(s): {model_name}")
                    break
        
        
    def chat_dialog(self):
        # Create a dialog window for sending prompts
        
        dialog = QDialog() # This dialog is for chatting with an LLM model
        
        display_model_name = "No model selected"
        if self.selected_ollama_model:
            display_model_name = ", ".join(self.selected_ollama_model)
        
        dialog.setWindowTitle("Chat with LLM model: " + display_model_name)
        layout = QVBoxLayout()
        # add resize to maximum button to dialog 
        dialog.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowMinMaxButtonsHint | QtCore.Qt.WindowCloseButtonHint)
        
        # add dialog window icon to show in taskbar instead of default qt icon
        dialog.setWindowIcon(QtGui.QIcon('images/tray_chat_ai_window_icon.png'))
        
        # Restore geometry if saved
        settings = self.read_settings()
        if 'chat_window_geometry' in settings:
            geometry_hex = settings['chat_window_geometry']
            dialog.restoreGeometry(QtCore.QByteArray.fromHex(geometry_hex.encode()))
        else:
            # initial size of the chat dialog
            dialog.resize(600, 600)
        
        # first call function to sellect ollama model if not selected yet 
        if not self.selected_ollama_model:
            self.choose_ollama_model()
            
        
        font = QtGui.QFont()
        font.setPointSize(12)
        
        # add dropdown for model selection at the top of the dialog
        model_selection_layout = QHBoxLayout()
        model_selection_label = QLabel("Select Model(s):")
        model_selection_label.setFont(font)
        model_selection_layout.addWidget(model_selection_label)

        self.model_combo_box = QComboBox()
        self.model_combo_box.setFont(font)
        self.model_combo_box.setMinimumHeight(30)
        self.model_combo_box.setStyleSheet("QComboBox { border: 1px solid #0d5c7a; border-radius: 5px; padding: 1px 18px 1px 3px; }")
        
        # Populate model combo box use multi 
        models_output = self.list_ollama_models()
        if models_output:
            models = [line.split()[0] for line in models_output.splitlines() if line.strip() and line.split()[0] != "NAME"]
            
            model = QtGui.QStandardItemModel()
            for model_name in models:
                item = QtGui.QStandardItem(model_name)
                item.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
                
                is_checked = False
                if self.selected_ollama_model and model_name in self.selected_ollama_model:
                    is_checked = True
                
                if is_checked:
                    item.setData(QtCore.Qt.Checked, QtCore.Qt.CheckStateRole)
                else:
                    item.setData(QtCore.Qt.Unchecked, QtCore.Qt.CheckStateRole)
                model.appendRow(item)
            
            self.model_combo_box.setModel(model)
            self.model_combo_box.model().itemChanged.connect(self._update_selected_model_from_chat_dialog)
        
        model_selection_layout.addWidget(self.model_combo_box)
        layout.addLayout(model_selection_layout)
        
        
        # label on top to show selected model name 
        model_label = QLabel(f"Selected LLM Model(s): {display_model_name}")
        font_label = QtGui.QFont()
        font_label.setPointSize(12)
        font_label.setBold(True)
        model_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        model_label.setFont(font_label)
        
        layout.addWidget(model_label)
        
        
        # Chat Display (History)
        chat_display = QListWidget()
        chat_display.setStyleSheet("QListWidget { background-color: #ECE5DD; border: 0.5px solid #0d5c7a; border-radius: 10px; padding: 10px; }")
        chat_display.setSelectionMode(QAbstractItemView.NoSelection)
        chat_display.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        
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
        prompt_input.setStyleSheet("QTextEdit { background-color: #FFFFFF; border: 0.5px solid #0d5c7a; border-radius: 10px; padding: 10px; }")
        prompt_input.setFont(font)
        prompt_input.setMaximumHeight(100)
        prompt_input.setPlaceholderText("Type your message here... (Press Enter to send), use F11 for fullscreen")
        layout.addWidget(prompt_input)

        # Buttons Layout
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        clear_button = QPushButton("Clear Chat History")
        clear_button.setStyleSheet("QPushButton { font-size:14px; font-weight:bold; background-color: #546e7a; color: white; padding: 10px; border: 1px solid #0d5c7a; border-radius: 10px; } QPushButton:hover { background-color: #455a64; }")
        clear_button.setMinimumHeight(50)
        send_button = QPushButton("Ask question (or press Enter to send)")
        send_button.setStyleSheet("QPushButton { font-size:14px; font-weight:bold; background-color: #63a0c5; color: white; padding: 10px; border: 1px solid #0d5c7a; border-radius: 10px; } QPushButton:hover { background-color: #175a83; }")
        send_button.setMinimumHeight(50)
        
        buttons_layout.addWidget(clear_button)
        buttons_layout.addWidget(send_button)
        
        layout.addLayout(buttons_layout)
        
        # Initialize chat history for this session
        dialog.chat_history = []
        
        # Clear history function
        def clear_chat():
            chat_display.clear()
            dialog.chat_history = []

        clear_button.clicked.connect(clear_chat)
        
        
        
        
        # Handle Enter key to send
        def keyPressEvent(event):
            if event.key() == QtCore.Qt.Key_Return and not (event.modifiers() & QtCore.Qt.ShiftModifier):
                send_button.click()
            else:
                QTextEdit.keyPressEvent(prompt_input, event)
        prompt_input.keyPressEvent = keyPressEvent
        
        # Handle F11 for fullscreen (Global for dialog)
        dialog.shortcut_f11 = QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_F11), dialog)
        dialog.shortcut_f11.activated.connect(lambda: dialog.showNormal() if dialog.isFullScreen() else dialog.showFullScreen())
        
        send_button.clicked.connect(lambda: self.send_prompt_and_show_result(prompt_input, chat_display, dialog))

        dialog.setLayout(layout)
        dialog.exec_()
        
        # Save geometry
        settings = self.read_settings()
        settings['chat_window_geometry'] = dialog.saveGeometry().toHex().data().decode()
        self.save_settings(settings)

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
            
            label_width = int((current_width - 50) * 0.9) 
            label = QLabel(final_html)
            label.setWordWrap(True)
            label.setMinimumWidth(label_width) 
            label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            label.setOpenExternalLinks(True)
            
            if role == "User":
                label.setStyleSheet("background-color: #DCF8C6; color: black; border-radius: 15px; padding: 10px; font-size: 12pt;")
                # Add stretch before the widget to push it to the right
                layout.addStretch()
                layout.addWidget(label)
            else:
                label.setStyleSheet("background-color: #FFFFFF; color: black; border-radius: 15px; padding: 10px; font-size: 12pt;")
                layout.addWidget(label)
                # Add stretch after the widget to keep it on the left
                layout.addStretch()
            
            layout.setContentsMargins(10, 5, 10, 5)
            widget.setLayout(layout)
            widget.adjustSize()
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
                if not self.selected_ollama_model:
                    self.show_status_message("Error", "No LLM model selected. Please select one first.", 5000)
                    return "Error: No model selected. Please select a model."

                models_to_run = self.selected_ollama_model
                
                final_output = ""
                for model in models_to_run:
                    # Use subprocess to pipe input to stdin, avoiding shell quoting issues
                    cmd = ["docker", "exec", "-i", self.docker_image_name, "ollama", "run", model]
                    result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, check=True) # -i is needed for piping input
                    output = ansi_escape.sub('', result.stdout)
                    if len(models_to_run) > 1:
                        final_output += f"**Model: {model}**\n{output}\n\n"
                    else:
                        final_output += output
                
                return final_output
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
            models = [line.split()[0] for line in models_output.splitlines() if line.strip() and line.split()[0] != "NAME"]
            
            current_index = 0
            if self.selected_ollama_model and self.selected_ollama_model[0] in models:
                current_index = models.index(self.selected_ollama_model[0])
            
            item, ok = QInputDialog.getItem(None, "Select Ollama Model", "Available Models:", models, current_index, False) # 0 is default index
            if ok and item:
                QMessageBox.information(None, "Model Selected", f"You selected: {item}")
                self.selected_ollama_model = [item]
                
                # store selected model in settings to persist between sessions
                settings = self.read_settings()
                settings['selected_ollama_model'] = item
                self.save_settings(settings)
                
                
                # if chat window is open, update its title and label
                active_dialog = QApplication.activeModalWidget()
                if active_dialog and isinstance(active_dialog, QDialog) and active_dialog.windowTitle().startswith("Chat with LLM model"):
                    active_dialog.setWindowTitle("Chat with LLM model: " + item)
                    # update label inside dialog
                    for i in range(active_dialog.layout().count()):
                        widget = active_dialog.layout().itemAt(i).widget()
                        if isinstance(widget, QLabel):
                            widget.setText(f"Selected LLM Model(s): {item}")
                            break
                
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
                    gpu_icon_path = os.path.join(self.image_dir, "tray_chat_ai_gpu_running.png")
                    self.tray.setIcon(QIcon(gpu_icon_path))
                    self.start_action.setEnabled(True) # Re-enable if it was disabled due to a previous error
                    self.stop_action.setEnabled(True)
                else: # This is for CPU mode
                    default_icon_path = os.path.join(self.image_dir, "tray_chat_ai_cpu_running.png")
                    self.tray.setIcon(QIcon(default_icon_path))
                    
                self.status_action.setText(f"Ollama: Running ({mode})")
                # You could change the icon here too: self.tray.setIcon(QIcon("green.png"))
                self.start_action.setVisible(False)
                self.stop_action.setVisible(True)
                self.send_prompt_action.setEnabled(True)
                self.pull_model_action.setEnabled(True) # Enable pull model action if container is running
            else:
                # set tray icon to not running 
                not_running_icon_path = os.path.join(self.image_dir, "tray_chat_ai_not_running.png")
                self.tray.setIcon(QIcon(not_running_icon_path))
                
                # change icon to show stopped status
                self.status_action.setText("LLM Server: Stopped ❌")
                self.start_action.setVisible(True)
                self.stop_action.setVisible(False)
                
                # disable actions that require running container
                self.start_action.setEnabled(True)
                self.stop_action.setEnabled(False) # Cannot stop if not found or not running
                self.send_prompt_action.setEnabled(False) # Cannot send prompt if not running
                self.pull_model_action.setEnabled(False) # Disable pull model action if container is not running
                
        except FileNotFoundError:
            logging.error("Docker command not found during status update. Is Docker installed and in PATH?")
            self.status_action.setText("LLM Server: Docker Command Not Found") # This status is generic
            self.start_action.setEnabled(False)
            self.stop_action.setEnabled(False)
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
            self.pull_model_action.setEnabled(False) # Disable pull model action
            self.send_prompt_action.setEnabled(False)
            not_running_icon_path = os.path.join(self.image_dir, "tray_chat_ai_not_running.png")
            self.tray.setIcon(QIcon(not_running_icon_path))
        except docker_errors.DockerException as e: # This is a generic Docker error
            logging.error(f"Docker daemon not available during status update: {e}") # This error is generic
            self.status_action.setText("LLM Server: Docker Daemon Down")
            self.start_action.setEnabled(False)
            self.stop_action.setEnabled(False)
            self.send_prompt_action.setEnabled(False)
            self.pull_model_action.setEnabled(False) # Disable pull model action
            self.tray.setIcon(QIcon(os.path.join(self.image_dir, "llm_tray_error.png")))
            self.docker_available = False # Mark as unavailable (this is generic)
        except Exception as e:
            logging.error(f"An unexpected error occurred during status update: {e}") # This error is generic
            self.status_action.setText("LLM Server: Error")
            self.start_action.setEnabled(False)
            self.stop_action.setEnabled(False)
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
            exec_cmd = "tray-chat-ai" 
            icon_path = "/usr/share/tray-chat-ai/images/tray_chat_ai_default.png"

            desktop_entry = f"""[Desktop Entry]
Type=Application
Name=TrayChat AI
Exec={exec_cmd}
Icon={icon_path}
Comment=Chat with AI models from the system tray
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
    tray = TrayChatAIManager()
    tray.run()

if __name__ == "__main__":
    main()