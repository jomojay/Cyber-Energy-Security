FROM python:3.11-slim
RUN pip install --no-cache-dir pymodbus==3.6.9
COPY rogue_scanner.py /app/rogue_scanner.py
WORKDIR /app
CMD ["python3", "rogue_scanner.py"]
