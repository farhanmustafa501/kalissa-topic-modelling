# Kalissa Topic Modelling

A Flask-based application for topic discovery, document analysis, and Q&A with citations using AI. This application uses K-means clustering, embeddings, and GPT-4o to automatically discover and label topics from document collections.

## Features

- 📄 **Document Upload & Parsing**: Support for PDF, DOCX, TXT, and MD files
- 🔍 **Automatic Topic Discovery**: K-means clustering on document embeddings
- 🤖 **AI-Powered Analysis**: GPT-4o-mini for topic labeling and insights generation
- 📊 **Interactive Visualization**: Topic graph with relationships
- 💬 **Q&A with Citations**: Topic-scoped question answering with inline citations
- 🔗 **Topic Relationships**: Automatic mapping of related topics
- ⚡ **Background Processing**: Celery-based async task processing
- 🐳 **Docker Support**: Complete containerized setup

## Architecture

- **Backend**: Flask (Python 3.12+)
- **Database**: PostgreSQL with pgvector extension
- **Task Queue**: Celery with Redis broker
- **AI**: OpenAI GPT-4o-mini and text-embedding-3-small
- **ML**: scikit-learn for K-means clustering

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16+ with pgvector extension
- Redis 7+ (for Celery task queue)
- OpenAI API key (for AI features)

### Installation

1. **Clone the repository:**
```bash
git clone <repository-url>
cd kalissa-topic-modelling
```

2. **Create and activate a virtual environment:**
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install dependencies:**
```bash
make install-dev
# Or manually:
pip install -r requirements.txt -r requirements-dev.txt
```

4. **Set up environment variables:**
```bash
cp env.example .env
# Edit .env and set:
# - DATABASE_URL (e.g., postgresql+psycopg2://user:pass@localhost:5432/kalisa)
# - OPENAI_API_KEY (your OpenAI API key)
# - CELERY_BROKER_URL (default: redis://localhost:6379/0)
# - CELERY_RESULT_BACKEND (default: redis://localhost:6379/0)
```

5. **Set up PostgreSQL with pgvector:**
```bash
# Install pgvector extension in your PostgreSQL database
# See docker/postgres/initdb/01_pgvector.sql for reference
```

6. **Run database migrations:**
```bash
alembic upgrade head
```

7. **Start Redis:**
```bash
# Using Docker:
docker run -d -p 6379:6379 redis:7-alpine

# Or using docker-compose:
docker-compose up -d redis
```

8. **Start the Celery worker** (in a separate terminal):
```bash
celery -A app.celery_app worker --loglevel=info
```

9. **Start the application:**
```bash
python run.py
# Or with gunicorn:
gunicorn wsgi:app
```

The application will be available at `http://localhost:8000`

### 🐳 Quick Start with Docker (Recommended)

**For the easiest setup, use Docker Compose:**

```bash
# 1. Set up environment variables
cp env.example .env
# Edit .env with your settings (especially OPENAI_API_KEY)

# 2. Start everything with one command
make docker-start

# 3. Access the application
# Open http://localhost:8000 in your browser
```

That's it! All services (web, worker, database, Redis) will start automatically.

## Docker Setup (Recommended)

The Docker Compose setup includes all required services:

- **Web**: Flask application (port 8000)
- **Worker**: Celery worker for background tasks
- **PostgreSQL**: Database with pgvector extension (port 5432)
- **Redis**: Celery broker and result backend (port 6379)

### Quick Start with Docker

**Start the project:**
```bash
make docker-start
```

This will:
- Build all Docker images
- Start all services in detached mode
- Make the application available at `http://localhost:8000`

**View logs:**
```bash
make docker-logs
# Or view specific service:
docker-compose logs -f web
docker-compose logs -f worker
docker-compose logs -f redis
docker-compose logs -f db
```

**Stop the project:**
```bash
make docker-down
```

**Restart services:**
```bash
make docker-restart
```

**Check running containers:**
```bash
make docker-ps
```

### Alternative Docker Commands

```bash
# Start in foreground (see logs directly)
make docker-up
# Or: docker-compose up --build

# Start in detached mode
make docker-start
# Or: docker-compose up --build -d

# Stop services
make docker-down
# Or: docker-compose down
```

### Environment Variables for Docker

Ensure your `.env` file has:
```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/kalisa
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
```

## Development

### Code Quality Tools

This project uses several tools to maintain code quality:

- **Ruff**: Fast Python linter and formatter (replaces flake8, isort, and more)
- **Black**: Code formatter
- **MyPy**: Static type checker
- **Pytest**: Testing framework with coverage

### Available Commands

#### Installation
```bash
make install       # Install production dependencies
make install-dev   # Install all dependencies (including dev)
```

#### Testing
```bash
make test          # Run all tests
make test-cov      # Run tests with coverage report
make test-tasks    # Run Celery task tests only

# Run specific tests
pytest tests/test_api_routes.py
pytest -m api      # Only API tests
pytest -m service  # Only service tests
pytest -m task     # Only Celery task tests
```

#### Linting and Formatting
```bash
make lint          # Run linting checks (Ruff)
make lint-flake8   # Run linting checks (Flake8)
make lint-fix      # Auto-fix linting issues
make lint-show     # Show detailed linting errors

make format        # Format code with black and ruff
make format-check  # Check formatting without making changes
```

#### Type Checking
```bash
make type-check    # Run type checking (mypy)
```

#### Complete Check
```bash
make check         # Run all checks (lint, format-check, type-check, test)
```

#### Docker
```bash
make docker-up     # Build and start Docker Compose stack
make docker-down    # Stop Docker Compose stack
make docker-logs   # Tail Docker Compose logs
```

#### Cleanup
```bash
make clean         # Clean up generated files
```

#### Help
```bash
make help          # Show all available commands
```

### Pre-commit Workflow

Before committing code, run:

```bash
make check
```

This will:
1. Check code formatting (`format-check`)
2. Run linting (`lint`)
3. Run type checking (`type-check`)
4. Run tests (`test`)

### Configuration Files

- **`ruff.toml`**: Ruff linter and formatter configuration
- **`pyproject.toml`**: Black, isort, and mypy configuration
- **`pytest.ini`**: Pytest configuration
- **`.coveragerc`**: Coverage configuration
- **`.flake8`**: Flake8 configuration (for compatibility)

## Project Structure

```
kalissa-topic-modelling/
├── app/
│   ├── api/              # API routes (Flask blueprints)
│   │   └── routes.py     # All API and UI routes
│   ├── services/         # Business logic
│   │   ├── ai.py        # OpenAI integration (topic naming, insights, Q&A)
│   │   ├── chunking.py  # Text chunking service
│   │   ├── discovery.py  # Topic discovery pipeline
│   │   ├── embeddings.py # Embedding generation
│   │   └── parser.py    # Document parsing (PDF, DOCX, etc.)
│   ├── static/          # Static files (CSS, JS)
│   ├── templates/       # Jinja2 templates
│   ├── celery_app.py    # Celery application configuration
│   ├── tasks.py         # Celery background tasks
│   ├── models.py        # SQLAlchemy database models
│   ├── db.py            # Database configuration
│   └── config.py        # Application configuration
├── tests/               # Test suite
│   ├── test_api_routes.py
│   ├── test_services_*.py
│   ├── test_tasks.py    # Celery task tests
│   └── conftest.py      # Pytest fixtures
├── migrations/          # Alembic database migrations
├── docker/             # Docker configuration
│   └── postgres/       # PostgreSQL initialization scripts
├── requirements.txt    # Production dependencies
├── requirements-dev.txt # Development dependencies
├── docker-compose.yml  # Docker Compose configuration
├── Makefile           # Development commands
└── README.md          # This file
```

## API Endpoints

### Collections
- `GET /api/collections` - List all collections
- `POST /api/collections` - Create a collection
- `GET /api/collections/<id>` - Get collection details
- `DELETE /api/collections/<id>` - Delete a collection

### Documents
- `GET /api/collections/<id>/documents` - List documents in collection
- `POST /api/collections/<id>/documents` - Add documents (JSON)
- `POST /api/collections/<id>/documents/upload_files` - Upload files (multipart/form-data)

### Discovery
- `POST /api/collections/<id>/discover` - Start topic discovery job
- `GET /api/collections/<id>/discover/status` - Get discovery job status
- `DELETE /api/collections/<id>/discover/last_job` - Delete discovery job

### Topics
- `GET /api/collections/<id>/topics/graph` - Get topic graph (nodes and edges)
- `GET /api/topics/<id>` - Get topic details
- `POST /api/topics/<id>/qa` - Ask question about topic (returns HTML with citations)

### UI Routes
- `GET /` - Home page (list collections)
- `GET /collections` - Collections list
- `GET /collections/<id>` - Collection detail page
- `GET /collections/<id>/graph` - Topic graph visualization
- `GET /topics/<id>` - Topic detail page

## Background Tasks

Topic discovery jobs run as Celery background tasks. This allows:

- Non-blocking API responses
- Task persistence and retry
- Scalable worker deployment
- Task monitoring and status tracking

### Running Celery Worker

**Local Development:**
```bash
celery -A app.celery_app worker --loglevel=info
```

**Docker:**
The Celery worker runs automatically in the `worker` service.

### Task Status

Discovery jobs have the following statuses:
- `PENDING`: Job created, waiting to start
- `RUNNING`: Job is currently processing
- `SUCCEEDED`: Job completed successfully
- `FAILED`: Job failed (error message available)

## Testing

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test categories
pytest -m api      # API tests
pytest -m service  # Service tests
pytest -m task     # Celery task tests
pytest -m unit     # Unit tests

# Run specific test file
pytest tests/test_tasks.py

# Run with verbose output
pytest -v
```

### Test Coverage

Coverage reports are generated in HTML format:
```bash
make test-cov
# Open htmlcov/index.html in your browser
```

See [TESTING_GUIDE.md](TESTING_GUIDE.md) for detailed testing documentation.

## Linting

### Ruff (Primary Linter)

```bash
make lint          # Check for issues
make lint-fix      # Auto-fix issues
make lint-show     # Show detailed errors
```

### Flake8 (Alternative)

```bash
make lint-flake8   # Run Flake8 checks
```

See [TESTING_GUIDE.md](TESTING_GUIDE.md) for detailed linting documentation.

## Topic Discovery Pipeline

The topic discovery process includes:

1. **Document Chunking**: Split documents into 800-1200 token chunks with overlap
2. **Embedding Generation**: Generate embeddings using text-embedding-3-small
3. **Clustering**: K-means clustering (k = sqrt(N_chunks / 2))
4. **Topic Labeling**: GPT-4o-mini generates topic names from representative chunks
5. **Insights Generation**: GPT-4o-mini generates topic insights
6. **Relationship Building**: Calculate topic similarities and create relationships
7. **Document Ranking**: Rank documents per topic by relevance score

## Troubleshooting

### Celery Worker Not Starting

1. Ensure Redis is running:
```bash
docker-compose up -d redis
# Or: docker run -d -p 6379:6379 redis:7-alpine
```

2. Check Celery broker URL in `.env`:
```env
CELERY_BROKER_URL=redis://localhost:6379/0
```

3. Verify Redis connection:
```bash
redis-cli ping  # Should return "PONG"
```

### Database Connection Issues

1. Verify PostgreSQL is running and accessible
2. Check `DATABASE_URL` in `.env`
3. Ensure pgvector extension is installed:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Discovery Jobs Failing

1. Check Celery worker logs:
```bash
docker-compose logs -f worker
# Or: Check terminal where worker is running
```

2. Verify OpenAI API key is set:
```env
OPENAI_API_KEY=sk-your-key-here
```

3. Check job status via API:
```bash
curl http://localhost:8000/api/collections/<id>/discover/status
```

### Import Errors

1. Ensure virtual environment is activated
2. Install dependencies: `make install-dev`
3. Verify you're in the project root directory

### Linting Errors

1. Auto-fix issues: `make lint-fix`
2. Format code: `make format`
3. Check configuration in `ruff.toml`

## Contributing

1. Create a feature branch
2. Make your changes
3. Run `make check` to ensure all checks pass
4. Write tests for new features
5. Update documentation as needed
6. Submit a pull request

## Dependencies

### Production
- Flask 3.0.3
- SQLAlchemy 2.0.36
- Celery 5.4.0
- Redis 5.0.1
- OpenAI 1.51.0
- scikit-learn 1.3.0+
- pgvector 0.3.3

See `requirements.txt` for complete list.

### Development
- pytest 8.3.2
- ruff 0.6.3
- black 24.8.0
- mypy 1.11.2
- flake8 7.0.0

See `requirements-dev.txt` for complete list.

## License

[Your License Here]

## Support

For issues, questions, or contributions, please open an issue on the repository.
