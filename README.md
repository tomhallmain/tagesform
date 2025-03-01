# Tagesform - Intelligent Task & Schedule Management

Tagesform is a modern web application that helps you manage your tasks, schedules, and daily activities with intelligent prioritization powered by LLM technology.

## Features

- Task management with smart priority inference
- Schedule management with recurring events support
- Real-time entity availability tracking (e.g., restaurant hours)
- User profiles and authentication
- LLM-powered task prioritization

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
Create a `.env` file in the project root with:
```
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your-secret-key-here
OPENAI_API_KEY=your-openai-api-key
```

4. Initialize the database:
```bash
flask db init
flask db migrate
flask db upgrade
```

5. Run the application:
```bash
flask run
```

The application will be available at `http://localhost:5000`

## Project Structure

```
tagesform/
├── app.py              # Main application file
├── requirements.txt    # Python dependencies
├── .env               # Environment variables (create this)
├── instance/          # SQLite database location
└── templates/         # HTML templates
    └── index.html     # Main application template
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

# Tagesform

Calendar and timer application. Keep track of a multitude of varied recurring schedules and non-recurring tasks or events.

Helpful to answer questions like:
- Is that restaurant open today?
- What am I forgetting to do today?
- When should I start preparing for a holiday?
- Will I be able to complete this task by the deadline, or is an extension required?

## Installation

- Clone the repository to your local machine
- Navigate into the project folder and install dependencies by running `npm install` in the terminal

## Usage


