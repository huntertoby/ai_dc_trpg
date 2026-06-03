# AI DC TRPG Project

This project is an AI-powered Discord Tabletop Role-Playing Game (TRPG) system. It allows players to create characters using natural language descriptions, which are then processed by a local LLM to generate stats, backgrounds, and traits.

## Project Overview

- **Purpose:** Provide an interactive TRPG experience on Discord using AI for character generation and game management.
- **Core Technologies:**
    - **Language:** Python 3.x
    - **Discord API:** `discord.py` (using Slash Commands)
    - **LLM Integration:** `openai` SDK (configured for LM Studio as a local backend)
    - **Data Models:** `pydantic` for robust character data validation and serialization.
    - **Storage:** Local JSON files (flat-file database) in `characters_db/` and `area_db/`.

## Architecture (Modular Refactoring)

The project follows a modular architecture for better separation of concerns:

1.  **Bot Interface (`main.py`)**: The main entry point that initializes the Discord bot, registers slash commands, and handles interactions. It uses `ui/embeds.py` for rendering.
2.  **LLM Client (`llm.py`)**: A wrapper for the OpenAI API that connects to a local LM Studio instance.
3.  **Data Models (`core/models.py`)**: Defines all Pydantic schemas (e.g., `CharacterSchema`, `Item`, `StatusEffect`) for data validation and serialization.
4.  **Character Logic (`core/character.py`)**: Handles core business logic such as stat calculations, equipment management, and state updates.
5.  **Data Storage (`db/storage.py`)**: Implements the `CharacterRepository` for reading and writing character data to the local file system.
6.  **Discord UI (`ui/embeds.py`)**: Contains functions to build complex Discord Embeds (e.g., character sheets) with ANSI formatting.
7.  **Creation Workflow (`logic/workflows/character_creation.py`)**: Manages the AI-assisted multi-step character creation process.

## Key Files and Directories

- `main.py`: Discord bot entry point.
- `services/llm_service.py`: LM Studio API client.
- `core/`: Core business logic and data models.
- `db/`: Data persistence layer.
- `ui/`: Discord user interface components (Embeds).
- `logic/workflows/`: Complex game flows and business logic.
- `characters_db/`: Directory for saved player character JSON files.
- `area_db/`: Directory for game area data.
- `.env`: Environment variables.

## Getting Started

### Prerequisites

1.  **Python 3.x**
2.  **LM Studio**: Run local server at `http://localhost:1234`.
3.  **Discord Bot Token**: Configured in `.env`.

### Installation

```bash
pip install discord.py openai pydantic python-dotenv
```

### Running the Project

```bash
python main.py
```

## Development Conventions

- **Modular Imports**: Always import models from `core.models`, logic from `core.character`, and UI helpers from `ui.embeds`.
- **Data Integrity**: Use Pydantic models for all structured data.
- **UI/Logic Separation**: Keep Discord-specific code (Embeds, Colors, ANSI) in `ui/` and core game logic in `core/`.
