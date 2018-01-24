# Basic docker image for ShuckleTools
# Usage:
#   docker build -t shuckletools .
#   docker run -d -P shuckletools -a ptc -u YOURUSERNAME -p YOURPASSWORD -l "Seattle, WA" -st 10 --gmaps-key CHECKTHEWIKI

FROM python:3.6

# Default port the webserver runs on
EXPOSE 6767

# Working directory for the application
WORKDIR /usr/src/app

# Set Entrypoint with hard-coded options
ENTRYPOINT ["dumb-init", "-r", "15:2", "python3", "./lureparty.py", "--host", "0.0.0.0"]

# Set default options when container is run without any command line arguments
CMD ["-h"]

COPY requirements.txt /usr/src/app/

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
 && pip3 install --no-cache-dir dumb-init \
 && pip3 install --no-cache-dir -r requirements.txt \
 && apt-get purge -y --auto-remove build-essential \
 && rm -rf /var/lib/apt/lists/*

# Copy everything to the working directory (Python files, templates, config) in one go.
COPY . /usr/src/app/
