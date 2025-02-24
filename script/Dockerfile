FROM python:3.10-slim

# Set working directory inside the container
WORKDIR /app

# Copy all necessary files
COPY requirements.txt main.py /app/

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Start the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
