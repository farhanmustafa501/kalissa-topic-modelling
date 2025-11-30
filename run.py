import os
from dotenv import load_dotenv
from app import create_app

load_dotenv()

app = create_app()

if __name__ == "__main__":
	# Default to 8000; override with PORT env var if needed
	port = int(os.getenv("PORT", "8000"))
	app.run(host="127.0.0.1", port=port, debug=True)


