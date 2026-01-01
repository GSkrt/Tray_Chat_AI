from setuptools import setup

setup(
    name="llm-tray-manager",
    version="1.0",
    description="LLM Tray Manager - Manage LLM models from the system tray",
    long_description="A system tray application to manage LLM models , providing an simple LLM chat interface.",
    author="Gregor Skrt",
    author_email="gregor.skrt@gmail.com",
    py_modules=["llm_tray_manager"],
    install_requires=[
        "PyQt5",
        "docker",
    ],
    entry_points={
        "console_scripts": [
            "llm-tray-manager=llm_tray_manager:main",
        ],
    },
    data_files=[
        ("share/llm-tray-manager/images", ["images/llm_tray_default.png", "images/llm_tray_gpu.png", "images/llm_tray_cpu_running.png", "images/llm_tray_gpu_running.png", "images/llm_tray_not_running.png", "images/llm_tray_error.png"]),
        ("share/applications", ["llm-tray-manager.desktop"]), # Assuming this file will be renamed
        ("share/doc/llm-tray-manager", ["LICENSE.txt"]),
    ],
)