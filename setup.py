from setuptools import setup

if __name__ == "__main__":
    setup(
        name="tray-chat-ai",
        version="1.0.2",
        description="TrayChat AI - Chat with AI models from the system tray and manage them easily.",
        long_description="A system tray application to manage AI models, providing a simple chat interface.",
        author="Gregor Skrt",
        author_email="gregor.skrt@gmail.com",
        py_modules=["tray_chat_ai"],
        install_requires=[
            "PyQt5",
            "docker",
            "markdown",
            "openai"
        ],
        entry_points={
            "console_scripts": [
                "tray-chat-ai=tray_chat_ai:main",
            ],
        },
        data_files=[
            ("share/tray-chat-ai/images", [
                "images/tray_chat_ai_default.png",
                "images/tray_chat_ai_cpu_running.png",
                "images/tray_chat_ai_gpu_running.png",
                "images/tray_chat_ai_not_running.png",
                "images/tray_chat_ai_web_running.png",
                "images/tray_chat_ai_window_icon.png",
                "images/tray_chat_ai_window_icon_simple.png",
                "images/connection_manager.svg"
            ]),
            ("share/pixmaps", ["images/tray_chat_ai_default.png"]),
            ("share/applications", ["tray-chat-ai.desktop"]),
            ("share/doc/tray-chat-ai", ["LICENSE.txt"]),
        ],
        zip_safe=False,
    )